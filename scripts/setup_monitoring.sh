#!/usr/bin/env bash
# ============================================================
# setup-monitoring.sh — установка мониторинга screenshot-service
# ============================================================
# Запуск: bash setup-monitoring.sh
# ============================================================

set -euo pipefail

PROJECT_DIR="/root/LabDoctorM/projects/lab-playwright-expert"
VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python3"

echo "=== Setting up Screenshot Service Monitoring ==="

# 1. Установить health monitor как systemd service
echo "[1/4] Installing health check service..."
cp "${PROJECT_DIR}/config/screenshot-healthcheck.service" /etc/systemd/system/
cp "${PROJECT_DIR}/config/screenshot-healthcheck.timer" /etc/systemd/system/

# 2. Включить и запустить таймер
echo "[2/4] Enabling health check timer..."
systemctl daemon-reload
systemctl enable --now screenshot-healthcheck.timer

# 3. Проверить статус
echo "[3/4] Checking status..."
systemctl status screenshot-healthcheck.timer --no-pager || true
systemctl list-timers screenshot-healthcheck.timer --no-pager || true

# 4. Тестовый запуск
echo "[4/4] Running test health check..."
"${VENV_PYTHON}" "${PROJECT_DIR}/scripts/health_monitor.py" --url http://localhost:8190

echo ""
echo "=== Monitoring setup complete ==="
echo "Health checks run every 2 minutes via systemd timer"
echo "Logs: journalctl -u screenshot-healthcheck.service -f"
echo "Timer: systemctl status screenshot-healthcheck.timer"
