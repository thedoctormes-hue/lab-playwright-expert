# 📖 Руководства по использованию

## Содержание

- [Screenshot Service](#screenshot-service)
- [Кросспостинг](#кросспостинг)
- [Мониторинг сайтов](#мониторинг-сайтов)
- [Stealth Research](#stealth-research)
- [Secret Manager](#secret-manager)
- [Security Audit](#security-audit)
- [Monitor Daemon](#monitor-daemon)
- [Telegram Dashboard](#telegram-dashboard)

## Screenshot Service

### Запуск

```bash
# Локальный запуск
export SCREENSHOT_SERVICE_TOKEN="your-token"
uvicorn scripts.screenshot_service:app --host 127.0.0.1 --port 8190

# Docker
docker compose up -d screenshot-service

# systemd
sudo systemctl start screenshot-service
```

### Создание скриншота

```bash
# Базовый скриншот
curl -X POST http://localhost:8190/screenshot \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# Полная страница
curl -X POST http://localhost:8190/screenshot \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"url": "https://example.com", "full_page": true}'

# PDF
curl -X POST http://localhost:8190/screenshot \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"url": "https://example.com", "format": "pdf"}'

# Кастомный viewport
curl -X POST http://localhost:8190/screenshot \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"url": "https://example.com", "width": 375, "height": 812}'

# Ожидание элемента
curl -X POST http://localhost:8190/screenshot \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"url": "https://example.com", "wait_for": "#content", "wait_ms": 2000}'
```

### Скачивание

```bash
# Из ответа POST
curl -s -X POST http://localhost:8190/screenshot \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"url": "https://example.com"}' | jq -r '.screenshot_url'

# Скачать файл
curl -s "http://localhost:8190/screenshot/download/HASH" \
  -H "Authorization: Bearer $TOKEN" \
  -o screenshot.png
```

### Управление кэшем

```bash
# Очистить кэш
curl -X DELETE http://localhost:8190/cache \
  -H "Authorization: Bearer $TOKEN"

# Проверить hit rate
curl -s http://localhost:8190/health | jq '.cache_hit_rate'
```

## Кросспостинг

### Настройка

```bash
# 1. Мигрировать cookies в зашифрованный vault
python3 scripts/crosspost_secure.py --migrate

# 2. Или сохранить вручную
python3 -c "
import asyncio, json
from scripts.crosspost_secure import CrossPosterSecure, PLATFORMS

async def save():
    poster = CrossPosterSecure()
    await poster.save_cookies(PLATFORMS['habr'])

asyncio.run(save())
"
```

### Публикация

```python
import asyncio
from scripts.crosspost_secure import CrossPosterSecure, PLATFORMS
from scripts.crosspost import PostContent

async def publish():
    poster = CrossPosterSecure(headless=True)
    
    content = PostContent(
        title="Заголовок статьи",
        body="Текст статьи...",
        tags=["python", "automation"],
    )
    
    # Сохранить как черновик
    result = await poster.post(PLATFORMS["habr"], content, as_draft=True)
    print(result)
    
    # Опубликовать
    result = await poster.post(PLATFORMS["habr"], content, as_draft=False)
    print(result)

asyncio.run(publish())
```

### CLI

```bash
# Миграция cookies
python3 scripts/crosspost_secure.py --migrate
```

## Мониторинг сайтов

### Конфигурация

Редактировать `config/monitor.yaml`:

```yaml
SERVICE_MONITOR:
  services:
    - name: snablab
      url: https://snablab.shtab-ai.ru
      expected_status: 200
      expected_title: "СнабЛаб"
      expected_text: "Управление закупками"
      selectors: ["#app"]
      critical: true
    - name: blog
      url: https://articles.shtab-ai.ru
      expected_status: 200
      critical: false
```

### Запуск

```bash
# Однократная проверка
python3 scripts/site_monitor.py

# С JSON-отчётом
python3 scripts/site_monitor.py --report

# Инициализация эталонов
python3 scripts/site_monitor.py --init-baselines
```

### Результаты

```json
{
  "name": "snablab",
  "url": "https://snablab.shtab-ai.ru",
  "status": "ok",
  "status_code": 200,
  "load_time_ms": 1234,
  "title": "СнабЛаб",
  "screenshot_path": "/tmp/playwright_monitor/monitor_snablab.png",
  "visual_match": true,
  "visual_diff_ratio": 0.02
}
```

**Статусы:**
- `ok` — всё в порядке
- `degraded` — деградация (title mismatch, selector missing, visual diff)
- `error` — ошибка (HTTP 4xx/5xx, timeout, connection refused)

## Stealth Research

### Запуск тестов

```bash
# Все тесты
python3 scripts/stealth_research.py

# Конкретный тест
python3 scripts/stealth_research.py --test webdriver_js

# Сравнение уровней
python3 scripts/stealth_research.py --compare

# С видимым браузером (отладка)
python3 scripts/stealth_research.py --no-headless
```

### Отслеживание трендов

```bash
# Замер и сохранение
python3 scripts/stealth_tracker.py --run

# Тренд
python3 scripts/stealth_tracker.py --trend

# История за 7 дней
python3 scripts/stealth_tracker.py --history 7d

# Прогноз деградации
python3 scripts/stealth_tracker.py --forecast

# Сравнение последних двух замеров
python3 scripts/stealth_tracker.py --compare
```

### Интерпретация результатов

| Score | Статус | Действие |
|-------|--------|----------|
| 80–100% | 🟢 OK | Всё в порядке |
| 60–80% | 🟡 Warning | Проверить конкретные тесты |
| < 60% | 🔴 Critical | Обновить stealth-скрипты |

## Secret Manager

### Инициализация

```python
from scripts.secret_manager import SecretManager

sm = SecretManager()
# Master key создаётся автоматически в /root/LabDoctorM/.secrets/.master_key
# Или задать через env: SECRETS_MASTER_KEY="your-key"
```

### Управление секретами

```python
# Сохранить
sm.set("my_key", "my_value")

# Получить
value = sm.get("my_key")

# Удалить
sm.delete("my_key")

# Список ключей
keys = sm.list_keys()
```

### Cookies

```python
# Сохранить cookies
sm.store_cookies("habr", cookies_list)

# Загрузить
cookies = sm.load_cookies("habr")
```

### API Keys

```python
sm.store_api_key("openrouter", "sk-...")
key = sm.load_api_key("openrouter")
```

### Ротация мастер-ключа

```python
new_key = sm.rotate_master_key()
# Обновить SECRETS_MASTER_KEY env!
```

### CLI

```bash
# Сохранить
python3 scripts/secret_manager.py set my_key my_value

# Получить
python3 scripts/secret_manager.py get my_key

# Список
python3 scripts/secret_manager.py list

# Удалить
python3 scripts/secret_manager.py delete my_key

# Ротация
python3 scripts/secret_manager.py rotate

# Миграция cookies
python3 scripts/secret_manager.py migrate-cookies habr config/habr_cookies.json
```

## Security Audit

### Запуск

```bash
# Полный аудит
python3 scripts/security_audit.py

# Быстрый (только критическое)
python3 scripts/security_audit.py --quick

# JSON-отчёт
python3 scripts/security_audit.py --json
```

### Проверки

1. **File Permissions** — права на критические директории
2. **Exposed Secrets** — API keys, passwords, tokens в коде
3. **Legacy Cookies** — cookies в открытых файлах
4. **Systemd Config** — параметры безопасности unit-файла
5. **Service Exposure** — сетевая доступность, firewall
6. **Dependencies** — уязвимости в pip-пакетах
7. **URL Validation** — тесты SSRF protection
8. **Rate Limiting** — работа rate limiter
9. **Suspicious Logs** — подозрительная активность
10. **SSL/TLS** — конфигурация (если nginx)

### Автоматический аудит

```bash
# Через systemd timer (ежедневно)
sudo systemctl enable --now security-audit.timer

# Или через cron
0 6 * * * cd /root/LabDoctorM/projects/lab-playwright-expert && \
  .venv/bin/python3 scripts/security_audit.py --json > /var/log/security-audit.json
```

## Monitor Daemon

### Запуск

```bash
# Однократный цикл
python3 scripts/monitor_daemon.py

# Демон
python3 scripts/monitor_daemon.py --daemon --interval 300

# Отправить дашборд
python3 scripts/monitor_daemon.py --send-dashboard
```

### Переменные окружения

```bash
export SCREENSHOT_SERVICE_URL="http://localhost:8190"
export MONITOR_BOT_TOKEN="your-bot-token"
export MONITOR_CHAT_ID="your-chat-id"
export MONITOR_INTERVAL="300"
```

### Цикл мониторинга

Каждые N секунд:
1. Сбор метрик из `/metrics`
2. Запуск `site_monitor.py --report`
3. Оценка 22 правил алертов
4. Отправка алертов в Telegram
5. Сохранение снимка состояния

Каждые 12 циклов (~1 час):
6. Отправка дашборда в Telegram

## Telegram Dashboard

### Формирование

```bash
# Полный дашборд
python3 scripts/telegram_dashboard.py

# Компактный
python3 scripts/telegram_dashboard.py --compact

# По компоненту
python3 scripts/telegram_dashboard.py --component stealth
```

### Отправка

```bash
python3 scripts/telegram_dashboard.py \
  --send \
  --bot-token "your-token" \
  --chat-id "your-chat-id"
```

### Формат дашборда

```
📊 Playwright Dashboard — 2026-05-17 12:00

📸 Screenshot Service
  Запросы: 1523 | Активных браузеров: 2
  Кэш: 🟢 65.3% (995/1523)
  Ошибки: 12
  Latency avg: 2.3s

🌐 Site Monitor
  Uptime: 🟢 99.5% (199/200 OK)
  ✅ snablab: 1234ms
  ✅ blog: 567ms

🔒 Stealth
  Score: 🟢 80% (4/5 passed)
  ✅ webdriver_js
  ✅ fingerprint
  ✅ headers
  ✅ cloudflare
  ❌ webgl

📤 CrossPost
  Публикаций: 45 | Успех: 🟢 91.1%

💓 Health Monitor
  Проверок: 288 | Uptime: 🟢 99.8%
  Последняя: ✅ ok (234ms)
```

## Библиотека (Python API)

### BrowserManager

```python
from lab_playwright_kit.browser import BrowserManager

async with BrowserManager(
    headless=True,
    timeout=30000,
    viewport={"width": 1920, "height": 1080},
    user_agent="Mozilla/5.0...",
) as browser:
    page = await browser.goto("https://example.com")
    title = await page.title()
```

### StealthConfig

```python
from lab_playwright_kit.stealth import StealthConfig, apply_stealth

# 4 уровня
config = StealthConfig.minimal()   # 1 скрипт
config = StealthConfig.standard()  # 6 скриптов
config = StealthConfig.advanced()  # 16 скриптов
config = StealthConfig.full()      # 16 + random UA

await apply_stealth(page, config)
```

### ScreenshotMaker

```python
from lab_playwright_kit.screenshot import ScreenshotMaker

maker = ScreenshotMaker("/tmp/screenshots")

# Типы скриншотов
path = await maker.viewport(page, prefix="example")
path = await maker.full_page(page, prefix="example")
path = await maker.element(page, "h1", prefix="example")
path = await maker.pdf(page, prefix="example")

# Визуальное сравнение
match, diff_ratio, diff_path = await maker.compare(
    page, "baseline.png", threshold=0.15
)
```

### PageParser

```python
from lab_playwright_kit.parser import PageParser

parser = PageParser(page)
content = await parser.parse()

print(content.title)
print(content.text)
print(content.links)
print(content.headings)
print(content.images)

# По селектору
headings = await parser.extract_by_selector("h1, h2, h3")

# Прокрутка
scrolls = await parser.scroll_to_bottom()
```

### NetworkInterceptor

```python
from lab_playwright_kit.network import NetworkInterceptor

interceptor = NetworkInterceptor(page)
interceptor.attach()

await page.goto("https://example.com")

interceptor.detach()

# Анализ
api_calls = interceptor.log.get_api_calls()
errors = interceptor.log.filter_by_status(500)
css = interceptor.log.filter_by_type("stylesheet")
domain = interceptor.log.filter_by_domain("api.example.com")
```

### ScreencastRecorder

```python
from lab_playwright_kit.screencast import ScreencastRecorder

async with ScreencastRecorder(page, "/tmp/cast.webm") as rec:
    await page.click("button")
    await rec.annotate(rec.frame_count, "Clicked button")
    await page.fill("#input", "text")
    await rec.annotate(rec.frame_count, "Filled input")
```

### ARIASnapshot

```python
from lab_playwright_kit.aria_snapshot import ARIASnapshot

# Получить snapshot
snapshot = await ARIASnapshot.capture(page)
snapshot = await ARIASnapshot.capture(page, "#main")

# Сравнить
diff = ARIASnapshot.compare(before, after)
print(diff.has_changes)
print(diff.added)
print(diff.removed)
print(diff.changed)
print(diff.summary)
```

### ClockController

```python
from lab_playwright_kit.clock import ClockController

ctrl = ClockController()

# Заморозить
await ctrl.freeze(page, 1704067200000)

# Продвинуть
await ctrl.advance(page, 5000)

# Быстрая перемотка
await ctrl.fast_forward(page, 10000)

# Фиксированное время
await ctrl.set_fixed(page, 1704067200000)

# Сброс
await ctrl.reset(page)
```
