#!/bin/bash
# Health check для SaaS API сервиса.
# Проверяет что процесс жив И API отвечает на /api/v1/health.
# При проблемах — перезапуск + уведомление в syslog.
#
# Использование:
#   chmod +x scripts/health_check.sh
#   ./scripts/health_check.sh
#
# Cron: */5 * * * * /root/LabDoctorM/projects/lab-playwright-expert/scripts/health_check.sh

set -euo pipefail

SERVICE="saas-api.service"
HEALTH_URL="http://localhost:8190/api/v1/health"
TIMEOUT=10
LOG_TAG="saas-api-health"

log() {
    logger -t "$LOG_TAG" "$1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# 1. Проверить что systemd unit активен
if ! systemctl is-active --quiet "$SERVICE"; then
    log "ERROR: $SERVICE is not active! Restarting..."
    systemctl restart "$SERVICE"
    sleep 5
    if systemctl is-active --quiet "$SERVICE"; then
        log "OK: $SERVICE restarted successfully"
    else
        log "CRITICAL: $SERVICE failed to restart!"
        exit 1
    fi
    exit 0
fi

# 2. Проверить что API отвечает
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" "$HEALTH_URL" 2>/dev/null || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    # Проверить что ответ содержит "healthy"
    BODY=$(curl -s --max-time "$TIMEOUT" "$HEALTH_URL" 2>/dev/null || echo "")
    if echo "$BODY" | grep -q '"healthy"'; then
        # OK — не логируем каждый раз, только при проблемах
        exit 0
    fi
fi

# 3. API не отвечает — перезапуск
log "WARN: API health check failed (HTTP $HTTP_CODE). Restarting $SERVICE..."
systemctl restart "$SERVICE"
sleep 10

# 4. Проверить после рестарта
HTTP_CODE_AFTER=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" "$HEALTH_URL" 2>/dev/null || echo "000")
if [ "$HTTP_CODE_AFTER" = "200" ]; then
    log "OK: $SERVICE recovered after restart"
else
    log "CRITICAL: $SERVICE still not responding after restart (HTTP $HTTP_CODE_AFTER)"
    exit 1
fi
