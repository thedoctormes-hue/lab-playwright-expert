# 🚀 Быстрый старт — Lab Playwright Kit

Установка, первые шаги, туториалы и решение проблем.

---

## Содержание

- [Требования](#требования)
- [Установка](#установка)
- [Первые шаги](#первые-шаги)
- [Туториалы](#туториалы)
  - [Скриншот страницы](#1-скриншот-страницы)
  - [Stealth-браузер](#2-stealth-браузер)
  - [Парсинг контента](#3-парсинг-контента)
  - [Мониторинг сайта](#4-мониторинг-сайта)
  - [LLM Browser Agent](#5-llm-browser-agent)
  - [Distributed Crawler](#6-distributed-crawler)
- [Конфигурация](#конфигурация)
- [Тестирование](#тестирование)
- [Troubleshooting](#troubleshooting)
- [Следующие шаги](#следующие-шаги)

---

## Требования

- **Python** 3.10+
- **Playwright** 1.50+
- **ОС:** Linux (рекомендуется), macOS
- **RAM:** минимум 2GB (4GB рекомендуется)
- **Диск:** 500MB для браузеров + место для скриншотов

---

## Установка

### 1. Клонирование

```bash
git clone <repo-url> /root/LabDoctorM/projects/lab-playwright-expert
cd /root/LabDoctorM/projects/lab-playwright-expert
```

### 2. Виртуальное окружение

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Зависимости

```bash
# Базовая установка
pip install -e .

# С dev-зависимостями (тесты, линтеры)
pip install -e ".[dev]"

# С полными зависимостями (LLM, мониторинг)
pip install -e ".[full]"
```

### 4. Playwright браузеры

```bash
# Установить Chromium
playwright install chromium

# Установить системные зависимости (Linux)
playwright install-deps chromium

# Для stealth-тестов рекомендуется Firefox тоже
playwright install firefox
```

### 5. Проверка установки

```bash
python3 -c "from lab_playwright_kit import BrowserManager; print('OK')"
```

### Docker (альтернатива)

```bash
docker build -t lab-playwright-kit .
docker run -d \
  --name playwright-kit \
  --init \
  --ipc=host \
  --security-opt no-new-privileges:true \
  -p 8190:8190 \
  -e SCREENSHOT_SERVICE_TOKEN="your-token" \
  lab-playwright-kit
```

---

## Первые шаги

### Минимальный пример

```python
import asyncio
from lab_playwright_kit.browser import BrowserManager

async def main():
    async with BrowserManager() as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        title = await page.title()
        print(f"Title: {title}")

asyncio.run(main())
```

Запуск:

```bash
python3 -c "
import asyncio
from lab_playwright_kit.browser import BrowserManager

async def main():
    async with BrowserManager() as browser:
        page = await browser.new_page()
        await page.goto('https://example.com')
        print(f'Title: {await page.title()}')

asyncio.run(main())
"
```

Ожидаемый выход:

```
Title: Example Domain
```

---

## Туториалы

### 1. Скриншот страницы

```python
import asyncio
from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.screenshot import ScreenshotMaker

async def main():
    maker = ScreenshotMaker("/tmp/screenshots")

    async with BrowserManager() as browser:
        page = await browser.new_page()

        # Viewport скриншот
        await page.goto("https://example.com")
        path = await maker.viewport(page, prefix="example")
        print(f"Viewport: {path}")

        # Полная страница
        path = await maker.full_page(page, prefix="example_full")
        print(f"Full page: {path}")

        # Элемент
        path = await maker.element(page, "h1", prefix="example_h1")
        print(f"Element: {path}")

asyncio.run(main())
```

### 2. Stealth-браузер

```python
import asyncio
from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.stealth import StealthConfig, apply_stealth
from lab_playwright_kit.fingerprint import FingerprintManager

async def main():
    # Генерация отпечатка
    fp = FingerprintManager.generate(
        profile_name="my_chrome_win",
        os="windows",
        browser="chrome",
    )
    print(fp.summary)

    async with BrowserManager(
        headless=True,
        user_agent=fp.user_agent,
    ) as browser:
        page = await browser.new_page()

        # Применение stealth
        config = StealthConfig.advanced()
        await apply_stealth(page, config)

        # Применение fingerprint
        await FingerprintManager.apply(page, fp)

        # Тест на bot.sannysoft.com
        await page.goto("https://bot.sannysoft.com")
        await page.screenshot(path="/tmp/stealth_test.png")
        print("Stealth test screenshot saved")

asyncio.run(main())
```

### 3. Парсинг контента

```python
import asyncio
from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.parser import PageParser

async def main():
    async with BrowserManager() as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")

        parser = PageParser(page)

        # Полный парсинг
        content = await parser.parse()
        print(f"Title: {content.title}")
        print(f"Text length: {len(content.text)}")
        print(f"Links: {len(content.links)}")
        print(f"Headings: {len(content.headings)}")

        # По селектору
        headings = await parser.extract_by_selector("h1, h2, h3")
        print(f"Headings: {headings}")

        # Структурированное извлечение
        data = await parser.extract_structured({
            "title": "page title",
            "description": "meta[name='description']@content",
            "links": "list:a[href]",
        })
        print(f"Structured: {data}")

asyncio.run(main())
```

### 4. Мониторинг сайта

```bash
# Однократная проверка
python3 scripts/site_monitor.py

# С JSON-отчётом
python3 scripts/site_monitor.py --report

# Инициализация эталонов
python3 scripts/site_monitor.py --init-baselines
```

Конфигурация (`config/monitor.yaml`):

```yaml
SERVICE_MONITOR:
  services:
    - name: example
      url: https://example.com
      expected_status: 200
      expected_title: "Example Domain"
      critical: true
```

### 5. LLM Browser Agent

```bash
# Mock-режим (без API-ключа)
PYTHONPATH=src python3 scripts/llm_browser_agent.py \
  --goal "Extract all headings from the page" \
  --start-url https://example.com \
  --max-steps 5 \
  --mock

# С LLM (нужен API-ключ)
PYTHONPATH=src python3 scripts/llm_browser_agent.py \
  --goal "Find the latest AI news and extract titles" \
  --start-url https://news.ycombinator.com \
  --max-steps 10 \
  --api-key "sk-..." \
  --output /tmp/agent_result.json
```

Python API:

```python
import asyncio
from scripts.llm_browser_agent import BrowserAgent

async def main():
    agent = BrowserAgent(
        goal="Extract page title and headings",
        start_url="https://example.com",
        max_steps=5,
        mock=True,
    )
    result = await agent.run()
    print(result["extracted_data"])

asyncio.run(main())
```

### 6. Distributed Crawler

```bash
# Простой запуск
PYTHONPATH=src python3 scripts/distributed_crawler.py \
  --seed https://example.com \
  --depth 2 \
  --output ./crawl_output \
  --workers 3

# С stealth
PYTHONPATH=src python3 scripts/distributed_crawler.py \
  --seed https://example.com \
  --depth 2 \
  --stealth \
  --output ./crawl_output

# Из YAML-конфига
PYTHONPATH=src python3 scripts/distributed_crawler.py \
  --config config/crawler.yaml
```

---

## Конфигурация

### Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `SCREENSHOT_SERVICE_TOKEN` | `""` | Токен для Screenshot Service |
| `TG_BOT_TOKEN` | `""` | Токен Telegram бота |
| `TG_ADMIN_IDS` | `""` | ID администраторов (через запятую) |
| `MONITOR_BOT_TOKEN` | `""` | Токен бота мониторинга |
| `MONITOR_CHAT_ID` | `""` | Chat ID для алертов |
| `MONITOR_INTERVAL` | `"300"` | Интервал мониторинга (сек) |
| `SECRETS_MASTER_KEY` | `""` | Мастер-ключ для Secret Manager |
| `OPENROUTER_API_KEY` | `""` | API-ключ OpenRouter |

### YAML-конфигурации

| Файл | Назначение |
|---|---|
| `config/monitor.yaml` | Мониторинг сайтов |
| `config/crawler.yaml` | Distributed Crawler |
| `config/stealth.yaml` | Stealth профили |

---

## Тестирование

```bash
# Все тесты
pytest tests/ -v

# Конкретный модуль
pytest tests/test_browser.py -v

# С покрытием
pytest tests/ --cov=lab_playwright_kit --cov-report=html

# Только быстрые (без браузера)
pytest tests/ -m "not browser" -v

# Stealth benchmark
python3 scripts/stealth_benchmark_suite.py --tests all

# Ghost Protocol (полный стресс-тест)
PYTHONPATH=src python3 scripts/ghost_protocol_v2.py --mode full
```

---

## Troubleshooting

### Ошибка: `Executable doesn't exist`

```
Executable doesn't exist at /root/.cache/ms-playwright/chromium-XXXX/chrome-linux/chrome
```

**Решение:**

```bash
playwright install chromium
playwright install-deps chromium
```

### Ошибка: `TimeoutError`

```
playwright._impl._api_types.TimeoutError: Timeout 30000ms exceeded
```

**Решение:** Увеличьте timeout:

```python
async with BrowserManager(timeout=60000) as browser:  # 60 секунд
    ...
```

### Ошибка: `WebGL not available`

WebGL недоступен в headless-режиме без GPU.

**Решение:** Используйте `FingerprintManager.apply()` для подмены WebGL:

```python
fp = FingerprintManager.generate("test", os="windows", browser="chrome")
await FingerprintManager.apply(page, fp)
```

### Ошибка: `bot.sannysoft.com показывает красные маркеры`

Не все stealth-скрипты применены.

**Решение:** Используйте уровень `full`:

```python
config = StealthConfig.full()
await apply_stealth(page, config)
```

### Ошибка: `LLM API error`

LLM не настроена или неверный API-ключ.

**Решение:** Используйте mock-режим для тестирования:

```python
agent = BrowserAgent(goal="...", mock=True)
```

Или проверьте API-ключ:

```bash
echo $OPENROUTER_API_KEY
```

### Ошибка: `Permission denied` на Linux

```
PermissionError: [Errno 13] Permission denied: '/root/.cache/ms-playwright'
```

**Решение:**

```bash
sudo chown -R $USER:$USER /root/.cache/ms-playwright
```

### Ошибка: `SSRF protection blocked`

Screenshot Service блокирует внутренние адреса.

**Решение:** Это нормальное поведение. Используйте только публичные URL.

### Ошибка: `Rate limit exceeded`

Слишком много запросов.

**Решение:** Увеличьте задержку или используйте `TaskOrchestrator` с rate limiting:

```python
from lab_playwright_kit.task_orchestrator import RateLimit

limit = RateLimit(
    platform="example",
    max_per_minute=10,
    cooldown_seconds=6.0,
)
```

---

## Следующие шаги

- 📖 [API Reference](API.md) — полный справочник всех модулей
- 🔧 [Scripts Documentation](SCRIPTS.md) — документация каждого скрипта
- 🏗 [Architecture](ARCHITECTURE.md) — архитектурные решения
- 📝 [Changelog](../CHANGELOG.md) — история изменений
- 📋 [Specs](../SPECS.md) — спецификации развития

---

*Документация актуальна для v2.0. Последнее обновление: 2026-05-18*
