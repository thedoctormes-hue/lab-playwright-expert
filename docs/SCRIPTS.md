# 🔧 Документация скриптов

Полное описание каждого исполняемого скрипта: назначение, использование, параметры.

---

## Содержание

- [Screenshot Service](#screenshot-service)
- [Site Monitor](#site-monitor)
- [Crosspost Secure](#crosspost-secure)
- [Secret Manager](#secret-manager)
- [Security Audit](#security-audit)
- [Monitor Daemon](#monitor-daemon)
- [Telegram Dashboard](#telegram-dashboard)
- [Ghost Protocol v2](#ghost-protocol-v2)
- [Stealth Benchmark Suite](#stealth-benchmark-suite)
- [Anti-Detection Lab](#anti-detection-lab)
- [Distributed Crawler](#distributed-crawler)
- [LLM Browser Agent](#llm-browser-agent)
- [TG Admin Bot](#tg-admin-bot)

---

## Screenshot Service

**Файл:** `scripts/screenshot_service.py`
**Тип:** FastAPI приложение
**Порт:** 8190

Screenshot-as-a-Service — REST API для создания скриншотов.

### Запуск

```bash
# Локальный
export SCREENSHOT_SERVICE_TOKEN="your-token"
uvicorn scripts.screenshot_service:app --host 127.0.0.1 --port 8190

# systemd
sudo systemctl start screenshot-service

# Docker
docker compose up -d screenshot-service
```

### API Endpoints

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/screenshot` | Создать скриншот |
| `GET` | `/screenshot/download/{hash}` | Скачать скриншот |
| `DELETE` | `/cache` | Очистить кэш |
| `GET` | `/health` | Проверка здоровья |
| `GET` | `/metrics` | Метрики |

### Примеры запросов

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

# Кастомный viewport (мобильный)
curl -X POST http://localhost:8190/screenshot \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"url": "https://example.com", "width": 375, "height": 812}'

# Ожидание элемента
curl -X POST http://localhost:8190/screenshot \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"url": "https://example.com", "wait_for": "#content", "wait_ms": 2000}'

# Скачивание
curl -s "http://localhost:8190/screenshot/download/HASH" \
  -H "Authorization: Bearer $TOKEN" \
  -o screenshot.png

# Очистка кэша
curl -X DELETE http://localhost:8190/cache \
  -H "Authorization: Bearer $TOKEN"
```

### Параметры запроса

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `url` | `str` | **required** | URL для скриншота |
| `full_page` | `bool` | `false` | Скриншот всей страницы |
| `format` | `str` | `"png"` | Формат: png, jpeg, pdf |
| `width` | `int` | `1920` | Ширина viewport |
| `height` | `int` | `1080` | Высота viewport |
| `wait_for` | `str` | `""` | CSS-селектор для ожидания |
| `wait_ms` | `int` | `0` | Дополнительная пауза (мс) |

### Безопасность

- Bearer token аутентификация
- SSRF защита (блокировка внутренних адресов)
- Rate limiting: 100 req/min
- Только http/https протоколы

---

## Site Monitor

**Файл:** `scripts/site_monitor.py`
**Тип:** CLI скрипт

Мониторинг доступности сайтов с проверкой контента и визуальным сравнением.

### Запуск

```bash
# Однократная проверка
python3 scripts/site_monitor.py

# С JSON-отчётом
python3 scripts/site_monitor.py --report

# Инициализация эталонов
python3 scripts/site_monitor.py --init-baselines
```

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

---

## Crosspost Secure

**Файл:** `scripts/crosspost_secure.py`
**Тип:** CLI + Python API

Безопасный кросспостинг с зашифрованным хранением cookies.

### Использование

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
# Миграция cookies в зашифрованный vault
python3 scripts/crosspost_secure.py --migrate
```

---

## Secret Manager

**Файл:** `scripts/secret_manager.py`
**Тип:** CLI + Python API

Управление секретами с Fernet шифрованием.

### Python API

```python
from scripts.secret_manager import SecretManager

sm = SecretManager()
# Master key создаётся автоматически в /root/LabDoctorM/.secrets/.master_key
# Или задать через env: SECRETS_MASTER_KEY="your-key"

# Сохранить
sm.set("my_key", "my_value")

# Получить
value = sm.get("my_key")

# Удалить
sm.delete("my_key")

# Список ключей
keys = sm.list_keys()

# Cookies
sm.store_cookies("habr", cookies_list)
cookies = sm.load_cookies("habr")

# API Keys
sm.store_api_key("openrouter", "sk-...")
key = sm.load_api_key("openrouter")

# Ротация мастер-ключа
new_key = sm.rotate_master_key()
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

---

## Security Audit

**Файл:** `scripts/security_audit.py`
**Тип:** CLI скрипт

Аудит безопасности конфигурации.

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

| # | Проверка | Описание |
|---|---|---|
| 1 | File Permissions | Права на критические директории |
| 2 | Exposed Secrets | API keys, passwords, tokens в коде |
| 3 | Legacy Cookies | Cookies в открытых файлах |
| 4 | Systemd Config | Параметры безопасности unit-файла |
| 5 | Service Exposure | Сетевая доступность, firewall |
| 6 | Dependencies | Уязвимости в pip-пакетах |
| 7 | URL Validation | Тесты SSRF protection |
| 8 | Rate Limiting | Работа rate limiter |
| 9 | Suspicious Logs | Подозрительная активность |
| 10 | SSL/TLS | Конфигурация (если nginx) |

### Автоматический аудит

```bash
# Через systemd timer (ежедневно)
sudo systemctl enable --now security-audit.timer

# Или через cron
0 6 * * * cd /root/LabDoctorM/projects/lab-playwright-expert && \
  .venv/bin/python3 scripts/security_audit.py --json > /var/log/security-audit.json
```

---

## Monitor Daemon

**Файл:** `scripts/monitor_daemon.py`
**Тип:** Демон

Фоновый мониторинг с алертами в Telegram.

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

---

## Telegram Dashboard

**Файл:** `scripts/telegram_dashboard.py`
**Тип:** CLI скрипт

Формирование и отправка дашборда в Telegram.

### Запуск

```bash
# Полный дашборд
python3 scripts/telegram_dashboard.py

# Компактный
python3 scripts/telegram_dashboard.py --compact

# По компоненту
python3 scripts/telegram_dashboard.py --component stealth

# Отправка
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

---

## Ghost Protocol v2

**Файл:** `scripts/ghost_protocol_v2.py`
**Тип:** CLI скрипт (стресс-тест)

Комплексный стресс-тест всех v2.0 модулей в 7 фазах.

### Запуск

```bash
# Полный тест
PYTHONPATH=src python3 scripts/ghost_protocol_v2.py \
  --mode full \
  --sessions 3 \
  --duration 30 \
  --output /tmp/gp2_reports

# Только разведка
PYTHONPATH=src python3 scripts/ghost_protocol_v2.py --mode recon

# Анти-детект
PYTHONPATH=src python3 scripts/ghost_protocol_v2.py --mode anti

# Отчёт
PYTHONPATH=src python3 scripts/ghost_protocol_v2.py --mode report
```

### Параметры

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `mode` | `str` | `"full"` | Режим: recon/full/anti/report |
| `sessions` | `int` | `3` | Кол-во параллельных сессий |
| `duration` | `int` | `30` | Длительность (сек) |
| `output` | `str` | `/tmp/gp2_reports` | Директория отчётов |

### Фазы

| Фаза | Модули | Описание |
|---|---|---|
| 1 | FingerprintManager | Генерация и валидация отпечатков |
| 2 | HumanBehaviorEngine | Тест 4 профилей поведения |
| 3 | AccountManager | Жизненный цикл аккаунтов |
| 4 | ActionEngine | Цепочки действий |
| 5 | TaskOrchestrator | Приоритетная очередь |
| 6 | Stealth Modules | Все модули антидетекта |
| 7 | — | HTML-отчёт |

### Цели тестирования

- `bot.sannysoft.com` — проверка отпечатков
- `browserleaks.com` — Canvas, WebGL, WebRTC
- `creepjs.com` — комплексный анализ
- `coveryourtracks.eff.org` — EFF тест
- `deviceinfo.me` — устройство
- `cloudflare.com` — Cloudflare challenge
- `google.com`, `github.com`, `wikipedia.org` — реальные сайты

---

## Stealth Benchmark Suite

**Файл:** `scripts/stealth_benchmark_suite.py`
**Тип:** CLI скрипт

Систематическое тестирование всех модулей антидетекта.

### Запуск

```bash
# Все тесты
python3 scripts/stealth_benchmark_suite.py --tests all --output /tmp/reports

# Конкретные категории
python3 scripts/stealth_benchmark_suite.py --tests fingerprint,behavior --json

# Сравнение
python3 scripts/stealth_benchmark_suite.py --tests all --compare
```

### Категории тестов

| Категория | Вес | Тесты |
|---|---|---|
| `fingerprint` | 0.25 | Generation, Determinism, Uniqueness, Canvas, WebGL, Audio, Screen, Hardware |
| `behavior` | 0.25 | Mouse Movement, Scroll, Typing |
| `network` | 0.25 | WebRTC, Headers |
| `consistency` | 0.25 | Cross-module consistency |

### Результаты

```json
{
  "overall_score": 85.5,
  "duration_ms": 12345,
  "timestamp": "2026-05-18T12:00:00",
  "categories": [
    {
      "name": "fingerprint",
      "weight": 0.25,
      "score": 90.0,
      "tests_passed": 7,
      "tests_failed": 1,
      "tests_total": 8
    }
  ]
}
```

### Интерпретация

| Score | Статус | Действие |
|---|---|---|
| 80–100% | 🟢 OK | Всё в порядке |
| 60–80% | 🟡 Warning | Проверить конкретные тесты |
| < 60% | 🔴 Critical | Обновить stealth-скрипты |

---

## Anti-Detection Lab

**Файл:** `scripts/antidetection_lab.py`
**Тип:** CLI скрипт (исследование)

Систематическое исследование 6 векторов обнаружения ботов.

### Запуск

```bash
# Все векторы
PYTHONPATH=src python3 scripts/antidetection_lab.py \
  --research all --output /tmp/reports

# Конкретные векторы
PYTHONPATH=src python3 scripts/antidetection_lab.py \
  --research canvas,webgl --json

# Сравнение с предыдущим
PYTHONPATH=src python3 scripts/antidetection_lab.py \
  --research all --compare
```

### Векторы обнаружения

| # | Вектор | Описание |
|---|---|---|
| 1 | Canvas Fingerprinting | Анализ энтропии, паттернов, уникальности |
| 2 | WebGL Analysis | Renderer/vendor detection, headless indicators |
| 3 | Behavioral Biometrics | Mouse movements, keystroke dynamics, scrolling |
| 4 | Timing Analysis | Request intervals, mouse speed, typing speed |
| 5 | Header Analysis | HTTP header consistency, automation markers |
| 6 | JavaScript Detection | navigator.webdriver, chrome.runtime, permissions |

### Результаты

Для каждого вектора:
- `detected` — обнаружен ли бот
- `detection_rate` — вероятность обнаружения (0-100%)
- `countermeasure` — описание контрмеры
- `countermeasure_effectiveness` — эффективность (0-100%)
- `risk_level` — critical/high/medium/low

### SQLite Database

Результаты сохраняются в `data/antidetection_research.db`:
- `research_results` — результаты тестов
- `research_sessions` — сессии исследований

---

## Distributed Crawler

**Файл:** `scripts/distributed_crawler.py`
**Тип:** CLI скрипт

Масштабируемый веб-краулер с stealth, прокси, robots.txt.

### Запуск

```bash
# Из YAML-конфига
PYTHONPATH=src python3 scripts/distributed_crawler.py --config config.yaml

# Из CLI
PYTHONPATH=src python3 scripts/distributed_crawler.py \
  --seed https://example.com \
  --depth 2 \
  --output ./crawl_output \
  --workers 3 \
  --stealth
```

### Параметры

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `config` | `str` | `""` | Путь к YAML-конфигу |
| `seed` | `str` | `""` | Стартовый URL |
| `depth` | `int` | `2` | Макс. глубина |
| `output` | `str` | `./crawl_output` | Директория результатов |
| `workers` | `int` | `3` | Кол-во воркеров |
| `stealth` | `bool` | `False` | Включить stealth |
| `max_pages` | `int` | `50` | Макс. страниц |
| `proxy` | `str` | `""` | Файл с прокси |

### YAML-конфигурация

```yaml
seeds:
  - https://example.com
max_depth: 2
max_pages: 50
workers: 3

stealth:
  enabled: true
  level: standard  # minimal, standard, advanced, full

proxy:
  enabled: false
  file: proxies.txt
  strategy: round_robin

output:
  format: both  # json, sqlite, both
  directory: ./crawl_output
  screenshots: false
  html: false

rate_limit:
  requests_per_second: 1.0
  delay_range: [1.0, 3.0]
  respect_robots_txt: true
```

### Компоненты

| Компонент | Описание |
|---|---|
| `CrawlerConfig` | Конфигурация из YAML/CLI |
| `ResultStore` | Хранение (JSON + SQLite) |
| `ProxyManager` | Ротация прокси |
| `RateLimiter` | Rate limiting по доменам |
| `RobotsHandler` | Парсинг robots.txt и sitemap.xml |
| `PageFetcher` | Загрузка страниц со stealth |

---

## LLM Browser Agent

**Файл:** `scripts/llm_browser_agent.py`
**Тип:** CLI + Python API

Автономный браузерный агент: Perception → Planning → Action → Memory.

### Запуск

```bash
# С LLM
PYTHONPATH=src python3 scripts/llm_browser_agent.py \
  --goal "Find the latest news about AI and extract titles and dates" \
  --start-url https://news.ycombinator.com \
  --max-steps 10 \
  --output /tmp/agent_result.json

# Mock-режим (без API-ключа)
PYTHONPATH=src python3 scripts/llm_browser_agent.py \
  --goal "Extract page titles" \
  --start-url https://example.com \
  --mock
```

### Параметры

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `goal` | `str` | **required** | Цель агента |
| `start_url` | `str` | `""` | Стартовый URL |
| `max_steps` | `int` | `20` | Макс. шагов |
| `model` | `str` | `gemini-2.5-flash` | Модель LLM |
| `api_key` | `str` | `""` | API-ключ |
| `output` | `str` | `""` | Файл результата |
| `mock` | `bool` | `False` | Mock-режим |
| `stealth` | `bool` | `True` | Stealth-режим |
| `headless` | `bool` | `True` | Без GUI |

### Архитектура агента

```
┌─────────────┐
│  Perception  │ ← ARIA Snapshot + Page Title
└──────┬──────┘
       │
┌──────▼──────┐
│   Planning   │ ← LLM принимает решение
└──────┬──────┘
       │
┌──────▼──────┐
│    Action    │ ← Выполняет действие
└──────┬──────┘
       │
┌──────▼──────┐
│   Memory     │ ← Сохраняет контекст
└─────────────┘
```

### Доступные действия

| Действие | Параметры | Описание |
|---|---|---|
| `navigate` | `url` | Перейти на URL |
| `click` | `selector` | Кликнуть по элементу |
| `type` | `selector, text` | Ввести текст |
| `scroll` | `direction, amount` | Прокрутить |
| `extract` | `schema` | Извлечь данные |
| `screenshot` | `prefix` | Скриншот |
| `wait` | `selector` | Ожидать элемент |
| `done` | `result` | Завершить |

### Python API

```python
from scripts.llm_browser_agent import BrowserAgent

agent = BrowserAgent(
    goal="Find AI news",
    start_url="https://news.ycombinator.com",
    max_steps=10,
    mock=True,
)
result = await agent.run()

print(result["extracted_data"])
print(result["visited_urls"])
print(result["actions"])
```

---

## TG Admin Bot

**Файл:** `scripts/tg_admin_bot.py`
**Тип:** Telegram Bot (aiogram v3)

Удалённое управление всеми Playwright-операциями через Telegram.

### Запуск

```bash
export TG_BOT_TOKEN="your-bot-token"
export TG_ADMIN_IDS="123456789,987654321"
python3 scripts/tg_admin_bot.py
```

### Команды

| Команда | Описание |
|---|---|
| `/start` | Приветствие |
| `/help` | Список команд |
| `/status` | Статус всех сервисов |
| `/screenshot <url> [name]` | Скриншот URL |
| `/crawl <url> [depth]` | Обход сайта |
| `/stealth_test` | Stealth benchmark |
| `/ghost_protocol <mode>` | Ghost Protocol |
| `/metrics` | Системные метрики |
| `/logs <service> [lines]` | Логи сервиса |

### Режимы Ghost Protocol

| Режим | Описание |
|---|---|
| `recon` | Разведка |
| `full` | Полная атака |
| `anti` | Анти-детект |
| `report` | Отчёт |

### Безопасность

- Только администраторы (TG_ADMIN_IDS)
- Rate limiting: 10 команд/мин на пользователя
- Логирование всех команд

---

*Документация актуальна для v2.0. Последнее обновление: 2026-05-18*
