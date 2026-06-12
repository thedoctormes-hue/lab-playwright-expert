# 🚀 Руководство по развёртыванию

## Содержание

- [Быстрый старт (Docker)](#быстрый-старт-docker)
- [Production (systemd)](#production-systemd)
- [Nginx + SSL](#nginx--ssl)
- [Мониторинг](#мониторинг)
- [Обновление](#обновление)
- [Откат](#откат)
- [Troubleshooting](#troubleshooting)

## Быстрый старт (Docker)

### Требования

- Docker 24+
- Docker Compose 2.20+

### Запуск

```bash
cd /root/LabDoctorM/projects/lab-playwright-expert

# Собрать и запустить
docker compose up -d

# Проверить статус
docker compose ps

# Логи
docker compose logs -f screenshot-service
```

### С мониторингом

```bash
# Prometheus + Grafana
docker compose --profile monitoring up -d

# Prometheus: http://localhost:9090
# Grafana: http://localhost:3001 (admin/admin)
```

### Переменные окружения

Создать `.env` файл:

```env
VERSION=latest
SCREENSHOT_PORT=8190
PROMETHEUS_PORT=9090
GRAFANA_PORT=3001
GRAFANA_PASSWORD=secure-password-here
```

## Production (systemd)

### Требования

- Python 3.10+
- Playwright Chromium
- systemd 250+

### Шаг 1: Подготовка

```bash
cd /root/LabDoctorM/projects/lab-playwright-expert

# Создать venv
python3 -m venv .venv
source .venv/bin/activate

# Установить зависимости
pip install -e .

# Установить Playwright Chromium
playwright install chromium
```

### Шаг 2: Создать пользователя

```bash
# Создать системного пользователя (НЕ root!)
sudo useradd -r -s /usr/bin/false screenshot-service

# Создать директории
sudo mkdir -p /tmp/screenshot_cache_secure
sudo mkdir -p /root/LabDoctorM/.secrets

# Права
sudo chown screenshot-service:screenshot-service /tmp/screenshot_cache_secure
sudo chmod 700 /tmp/screenshot_cache_secure
sudo chmod 700 /root/LabDoctorM/.secrets
```

### Шаг 3: Сгенерировать токен

```bash
# Сгенерировать токен
TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
echo "Token: $TOKEN"

# Сохранить в env-файл
echo "SCREENSHOT_SERVICE_TOKEN=$TOKEN" | sudo tee /root/LabDoctorM/.secrets/screenshot-service.env
sudo chmod 600 /root/LabDoctorM/.secrets/screenshot-service.env
sudo chown screenshot-service:screenshot-service /root/LabDoctorM/.secrets/screenshot-service.env
```

### Шаг 4: Установить systemd units

```bash
# Основной сервис
sudo cp config/screenshot-service.service /etc/systemd/system/

# Health check
sudo cp config/screenshot-healthcheck.service /etc/systemd/system/
sudo cp config/screenshot-healthcheck.timer /etc/systemd/system/

# Security audit
sudo cp config/security-audit.service /etc/systemd/system/
sudo cp config/security-audit.timer /etc/systemd/system/

# Перезагрузить systemd
sudo systemctl daemon-reload
```

### Шаг 5: Запустить

```bash
# Включить и запустить
sudo systemctl enable --now screenshot-service
sudo systemctl enable --now screenshot-healthcheck.timer
sudo systemctl enable --now security-audit.timer

# Проверить статус
sudo systemctl status screenshot-service

# Логи
journalctl -u screenshot-service -f
```

### Шаг 6: Проверить

```bash
# Health check
curl http://127.0.0.1:8190/health

# Тестовый скриншот
curl -X POST http://127.0.0.1:8190/screenshot \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

## Nginx + SSL

### Установка Nginx

```bash
sudo apt install nginx certbot python3-certbot-nginx
```

### Конфигурация

```bash
# Копировать конфиг
sudo cp config/nginx-ssl.conf /etc/nginx/sites-available/screenshot-service

# Активировать
sudo ln -s /etc/nginx/sites-available/screenshot-service /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### SSL сертификат

```bash
# Let's Encrypt
sudo certbot --nginx -d screenshot.shtab-ai.ru

# Или самоподписанный
sudo openssl req -x509 -nodes -days 365 \
  -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/screenshot.key \
  -out /etc/nginx/ssl/screenshot.crt
```

### Проверка

```bash
curl -k https://screenshot.shtab-ai.ru/health
```

## Мониторинг

### Prometheus

```bash
# Установить Prometheus
sudo apt install prometheus

# Копировать конфиг
sudo cp config/prometheus.yml /etc/prometheus/prometheus.yml
sudo cp config/alerts.yml /etc/prometheus/alerts.yml

# Перезапустить
sudo systemctl restart prometheus
```

### Grafana

```bash
# Установить Grafana
sudo apt install grafana

# Запустить
sudo systemctl enable --now grafana-server

# Добавить Prometheus data source
# URL: http://localhost:9090
```

### Telegram алерты

```bash
# Установить переменные
export MONITOR_BOT_TOKEN="your-bot-token"
export MONITOR_CHAT_ID="your-chat-id"

# Запустить демон
python3 scripts/monitor_daemon.py --daemon --interval 300
```

### Dashboard

```bash
# Отправить дашборд в Telegram
python3 scripts/telegram_dashboard.py \
  --send \
  --bot-token $MONITOR_BOT_TOKEN \
  --chat-id $MONITOR_CHAT_ID
```

## Обновление

### Docker

```bash
docker compose build --no-cache
docker compose up -d
```

### systemd

```bash
cd /root/LabDoctorM/projects/lab-playwright-expert

# Обновить код
git pull

# Обновить зависимости
source .venv/bin/activate
pip install -e .

# Перезапустить
sudo systemctl restart screenshot-service

# Проверить
sudo systemctl status screenshot-service
```

## Откат

### Docker

```bash
# Откат на предыдущую версию
docker compose down
docker compose build --build-arg VERSION=previous
docker compose up -d
```

### systemd

```bash
# Остановить
sudo systemctl stop screenshot-service

# Откат кода
cd /root/LabDoctorM/projects/lab-playwright-expert
git checkout <previous-commit>

# Переустановить
source .venv/bin/activate
pip install -e .

# Запустить
sudo systemctl start screenshot-service
```

## Troubleshooting

### Сервис не запускается

```bash
# Проверить статус
sudo systemctl status screenshot-service

# Логи
journalctl -u screenshot-service -n 50 --no-pager

# Проверить конфигурацию
sudo systemd-analyze verify /etc/systemd/system/screenshot-service.service
```

### Chromium не запускается

```bash
# Проверить зависимости
playwright install chromium --dry-run

# Переустановить
playwright install chromium --force

# Проверить вручную
python3 -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    print('OK')
    b.close()
"
```

### Высокое потребление памяти

```bash
# Проверить активные браузеры
curl -s http://127.0.0.1:8190/metrics | grep active_browsers

# Очистить кэш
curl -X DELETE http://127.0.0.1:8190/cache \
  -H "Authorization: Bearer $TOKEN"

# Перезапустить
sudo systemctl restart screenshot-service
```

### Rate limit exceeded

```bash
# Проверить текущие лимиты
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8190/health

# Увеличить лимиты (systemd)
sudo systemctl edit screenshot-service
# Добавить:
# [Service]
# Environment=RATE_LIMIT_REQUESTS=20
```

### SSL ошибки

```bash
# Проверить сертификат
sudo certbot certificates

# Обновить
sudo certbot renew --force-renewal

# Проверить nginx
sudo nginx -t
sudo systemctl reload nginx
```

### Мониторинг не работает

```bash
# Проверить Prometheus targets
curl -s http://localhost:9090/api/v1/targets | jq .

# Проверить алерты
curl -s http://localhost:9090/api/v1/alerts | jq .

# Проверить логи мониторинга
tail -f /var/log/screenshot-service-health.jsonl
```
