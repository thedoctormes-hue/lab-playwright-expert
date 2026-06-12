#!/bin/bash
# Мониторинг SaaS API — собирает метрики и сохраняет в JSON.
#
# Использование:
#   chmod +x scripts/monitor_saas.sh
#   ./scripts/monitor_saas.sh
#
# Cron: */5 * * * * /root/LabDoctorM/projects/lab-playwright-expert/scripts/monitor_saas.sh

set -euo pipefail

API_URL="http://localhost:8190"
TIMEOUT=10
METRICS_DIR="/var/log/saas-api"
METRICS_FILE="$METRICS_DIR/metrics.json"

mkdir -p "$METRICS_DIR"

TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
DATE=$(date '+%Y-%m-%d')

# 1. Health check
HEALTH_RESPONSE=$(curl -s --max-time "$TIMEOUT" "$API_URL/api/v1/health" 2>/dev/null || echo '{"status":"unreachable"}')
HEALTH_STATUS=$(echo "$HEALTH_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "error")

# 2. System status
STATUS_RESPONSE=$(curl -s --max-time "$TIMEOUT" "$API_URL/api/v1/status" 2>/dev/null || echo "{}")

# 3. System resources
SAAS_PID=$(systemctl show --property=MainPID --value saas-api.service 2>/dev/null || echo "0")
if [ "$SAAS_PID" != "0" ] && [ -d "/proc/$SAAS_PID" ]; then
    MEM_KB=$(grep VmRSS /proc/"$SAAS_PID"/status 2>/dev/null | awk '{print $2}' || echo "0")
    CPU_PCT=$(ps -p "$SAAS_PID" -o %cpu= 2>/dev/null | tr -d ' ' || echo "0")
else
    MEM_KB=0
    CPU_PCT=0
fi

# 4. Nginx stats (если есть)
NGINX_CONN=$(ss -tn state established '( dport = :443 or dport = :80 )' 2>/dev/null | wc -l || echo "0")

# 5. Собрать метрики
python3 -c "
import json, sys

metrics = {
    'timestamp': '$TIMESTAMP',
    'date': '$DATE',
    'health': '$HEALTH_STATUS',
    'pid': int('$SAAS_PID'),
    'memory_kb': int('$MEM_KB'),
    'cpu_pct': float('$CPU_PCT'),
    'nginx_connections': int('$NGINX_CONN'),
    'api_status': json.loads('''${STATUS_RESPONSE}''' if '''${STATUS_RESPONSE}''' else '{}'),
}

# Дописать в ежедневный файл
import os
daily_file = '$METRICS_DIR/metrics_${DATE}.jsonl'
with open(daily_file, 'a') as f:
    f.write(json.dumps(metrics, ensure_ascii=False) + '\n')

# Обновить текущий снимок
with open('$METRICS_FILE', 'w') as f:
    json.dump(metrics, f, indent=2, ensure_ascii=False)

print(f'Health: {metrics[\"health\"]}, MEM: {metrics[\"memory_kb\"]}KB, CPU: {metrics[\"cpu_pct\"]}%')
"

# 6. Ротация логов (хранить 30 дней)
find "$METRICS_DIR" -name "metrics_*.jsonl" -mtime +30 -delete 2>/dev/null || true
