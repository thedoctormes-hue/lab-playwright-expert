---
description: "lab-playwright-expert — README"
type: readme
last_reviewed: 2026-06-21
last_code_change: 2026-06-21
status: active
---

# 🥷 Lab Playwright Kit

> **Владелец:** DoctorM&Ai | **Статус:** active | **Версия:** 2.1.0

## Описание

Продвинутый фреймворк для автоматизации браузера на базе Playwright. 376 тестов, поддержка Python 3.10+ и Playwright 1.50+. Лаборатория DoctorM&Ai.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/playwright-1.50%2B-green)](https://playwright.dev/)
[![Tests](https://img.shields.io/badge/tests-376%20passed-brightgreen)](tests/)
[![License](https://img.shields.io/badge/license-CC%20BY--NC--SA%204.0-lightgrey)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.1.0-orange)](CHANGELOG.md)

**Лаборатория DoctorM&Ai** | ЗавЛаб Безуми́й Доктор

---

## 📋 Содержание

- [Обзор](#-обзор)
- [Возможности](#-возможности)
- [Установка](#-установка)
- [Быстрый старт](#-быстрый-старт)
- [Архитектура](#-архитектура)
- [Модули](#-модули)
- [Скрипты](#-скрипты)
- [Документация](#-документация)
- [Дорожная карта](#-дорожная-карта)
- [Лицензия](#-лицензия)

---

## 🔭 Обзор

**Lab Playwright Kit** — это набор инструментов для автоматизации браузера с акцентом на:

- **Антидетект** — 16+ stealth-скриптов, фейковые отпечатки, обход бот-защиты
- **Человечное поведение** — кривые Безье для мыши, переменная скорость набора, реалистичный скролл
- **Масштабируемость** — оркестратор задач, ротация прокси, распределённый краулинг
- **LLM-интеграция** — автономные браузерные агенты, self-healing локаторы
- **Мониторинг** — скриншоты как сервис, мониторинг сайтов, алерты в Telegram

Kit используется во всех проектах лаборатории: **СнабЛаб**, **Hype Pilot**, **Котолизатор VPN**, **Myrmex Control**, **Ворон**.

---

## ✨ Возможности

### Ядро (v1.0)
| Возможность | Описание |
|---|---|
| 🖥 **BrowserManager** | Управление браузером с авто-перезапуском и пулом страниц |
| 📸 **ScreenshotMaker** | Скриншоты viewport/full-page/элемента, PDF, визуальное сравнение |
| 🔍 **PageParser** | Извлечение контента, ссылок, заголовков, мета-данных |
| 🌐 **NetworkInterceptor** | Перехват и анализ сетевых запросов |
| 🎬 **ScreencastRecorder** | Запись видео с аннотациями |
| 🌳 **ARIASnapshot** | Accessibility tree snapshot и diff |
| ⏰ **ClockController** | Манипуляция временем в браузере |

### Антидетект (v1.0+)
| Возможность | Описание |
|---|---|
| 🥷 **StealthConfig** | 4 уровня: minimal → standard → advanced → full |
| 🔒 **WebRTC Protection** | Блокировка утечки реального IP |
| 🔊 **Audio Spoofing** | Подмена AudioContext FFT спектра |
| 📱 **Client Hints** | Согласованные Sec-CH-UA заголовки |

### v2.0 — Новые модули
| Возможность | Описание |
|---|---|
| 👆 **FingerprintManager** | Генерация детерминированных уникальных отпечатков |
| 🧠 **HumanBehaviorEngine** | 4 профиля поведения (casual_reader, power_user, researcher, social_media) |
| 🔐 **AccountManager** | Жизненный цикл аккаунтов с SQLite + Fernet шифрование |
| ⚡ **ActionEngine** | Цепочки действий (like, comment, follow, repost) с человечным поведением |
| 📋 **TaskOrchestrator** | Приоритетная очередь задач с rate limiting и воркерами |
| 🤖 **LLM Browser Agent** | Автономный агент: Perception → Planning → Action → Memory |
| 🕷 **Distributed Crawler** | Масштабируемый краулинг с stealth, прокси, robots.txt |
| 👻 **Ghost Protocol** | Комплексный стресс-тест всех модулей |
| 📊 **Stealth Benchmark** | Систематическое тестирование антидетекта с отчётами |
| 🔬 **Anti-Detection Lab** | Исследование 6 векторов обнаружения ботов |
| 🤖 **TG Admin Bot** | Telegram-бот для удалённого управления |

---

## 📦 Установка

### Требования
- Python 3.10+
- Playwright 1.50+
- Linux/macOS

### Быстрая установка

```bash
# Клонирование
git clone <repo-url> /root/LabDoctorM/projects/lab-playwright-expert
cd /root/LabDoctorM/projects/lab-playwright-expert

# Виртуальное окружение
python3 -m venv .venv
source .venv/bin/activate

# Зависимости
pip install -e ".[dev]"

# Playwright браузеры
playwright install chromium
playwright install-deps chromium
```

### Docker

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

## 🚀 Быстрый старт

### 1. Скриншот страницы

```python
import asyncio
from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.screenshot import ScreenshotMaker

async def main():
    async with BrowserManager() as browser:
        maker = ScreenshotMaker("/tmp/screenshots")
        page = await browser.new_page()
        await page.goto("https://example.com")
        path = await maker.full_page(page, prefix="example")
        print(f"Screenshot saved: {path}")

asyncio.run(main())
```

### 2. Stealth-браузер

```python
import asyncio
from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.stealth import StealthConfig, apply_stealth

async def main():
    async with BrowserManager(headless=True) as browser:
        page = await browser.new_page()
        config = StealthConfig.advanced()
        await apply_stealth(page, config)
        await page.goto("https://bot.sannysoft.com")
        # Делаем скриншот для проверки
        await page.screenshot(path="/tmp/stealth_test.png")

asyncio.run(main())
```

### 3. Парсинг страницы

```python
import asyncio
from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.parser import PageParser

async def main():
    async with BrowserManager() as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        parser = PageParser(page)
        content = await parser.parse()
        print(f"Title: {content.title}")
        print(f"Headings: {content.headings}")
        print(f"Links: {len(content.links)} found")

asyncio.run(main())
```

### 4. LLM Browser Agent

```python
import asyncio
from scripts.llm_browser_agent import BrowserAgent

async def main():
    agent = BrowserAgent(
        goal="Find the latest AI news and extract titles",
        start_url="https://news.ycombinator.com",
        max_steps=10,
        mock=True,  # Используем mock без API-ключа
    )
    result = await agent.run()
    print(result)

asyncio.run(main())
```

### 5. Запуск Screenshot Service

```bash
export SCREENSHOT_SERVICE_TOKEN="your-secret-token"
uvicorn scripts.screenshot_service:app --host 0.0.0.0 --port 8190
```

```bash
curl -X POST http://localhost:8190/screenshot \
  -H "Authorization: Bearer $SCREENSHOT_SERVICE_TOKEN" \
  -d '{"url": "https://example.com", "full_page": true}'
```

---

## 🏗 Архитектура

```
lab-playwright-expert/
├── src/lab_playwright_kit/     # 📚 Основная библиотека
│   ├── __init__.py             # Публичный API
│   ├── browser.py              # BrowserManager
│   ├── stealth.py              # StealthConfig, apply_stealth
│   ├── stealth_webrtc.py       # WebRTC leak protection
│   ├── stealth_audio.py        # AudioContext spoofing
│   ├── stealth_client_hints.py # Client Hints spoofing
│   ├── fingerprint.py          # FingerprintManager, BrowserFingerprint [v2.0]
│   ├── human_behavior.py       # HumanBehaviorEngine [v2.0]
│   ├── account.py              # AccountManager [v2.0]
│   ├── action_engine.py        # ActionEngine, ActionStep [v2.0]
│   ├── orchestrator.py         # TaskOrchestrator, Task, RateLimit [v2.0]
│   ├── screenshot.py           # ScreenshotMaker
│   ├── parser.py               # PageParser
│   ├── network.py              # NetworkInterceptor
│   ├── screencast.py           # ScreencastRecorder
│   ├── aria_snapshot.py        # ARIASnapshot
│   ├── clock.py                # ClockController
│   ├── llm_parse.py            # LLMParser, LLMConfig
│   ├── proxy_rotation.py       # ProxyRotator
│   ├── session_manager.py      # SessionManager
│   ├── har_recorder.py         # HARRecorder
│   └── metrics.py              # Метрики
├── scripts/                    # 🔧 Исполняемые скрипты
│   ├── screenshot_service.py   # Screenshot-as-a-Service (FastAPI)
│   ├── site_monitor.py         # Мониторинг сайтов
│   ├── crosspost_secure.py     # Безопасный кросспостинг
│   ├── secret_manager.py       # Управление секретами
│   ├── security_audit.py       # Аудит безопасности
│   ├── monitor_daemon.py       # Демон мониторинга
│   ├── telegram_dashboard.py   # Telegram дашборд
│   ├── ghost_protocol_v2.py    # Ghost Protocol v2.0 [v2.0]
│   ├── stealth_benchmark_suite.py # Stealth Benchmark [v2.0]
│   ├── antidetection_lab.py    # Anti-Detection Research Lab [v2.0]
│   ├── distributed_crawler.py  # Distributed Crawler [v2.0]
│   ├── llm_browser_agent.py    # LLM Browser Agent [v2.0]
│   └── tg_admin_bot.py         # Telegram Admin Bot [v2.0]
├── tests/                      # 🧪 Тесты (300+)
├── docs/                       # 📖 Документация
│   ├── API.md                  # API Reference
│   ├── ARCHITECTURE.md         # Архитектура
│   ├── SCRIPTS.md              # Документация скриптов
│   ├── GUIDES.md               # Руководства
│   ├── GETTING_STARTED.md      # Быстрый старт
│   └── DEPLOY.md               # Деплой
├── config/                     # ⚙️ Конфигурации
├── stealth_scripts/            # 🥷 JS-скрипты антидетекта
├── pyproject.toml              # 📦 Метаданные пакета
├── CHANGELOG.md                # 📝 История изменений
└── SPECS.md                    # 📋 Спецификации развития
```

---

## 📚 Модули

### Ядро

| Модуль | Класс | Назначение |
|---|---|---|
| `browser` | `BrowserManager` | Управление жизненным циклом браузера |
| `stealth` | `StealthConfig` | Конфигурация антидетекта (4 уровня) |
| `screenshot` | `ScreenshotMaker` | Скриншоты и визуальное сравнение |
| `parser` | `PageParser` | Парсинг контента страницы |
| `network` | `NetworkInterceptor` | Перехват сетевых запросов |
| `screencast` | `ScreencastRecorder` | Запись видео с аннотациями |
| `aria_snapshot` | `ARIASnapshot` | Accessibility tree snapshot |
| `clock` | `ClockController` | Манипуляция временем |

### Антидетект

| Модуль | Класс | Назначение |
|---|---|---|
| `stealth_webrtc` | `WebRTCConfig`, `WebRTCProtector` | Защита от WebRTC leak |
| `stealth_audio` | `AudioConfig`, `AudioSpoofer` | Подмена AudioContext |
| `stealth_client_hints` | `ClientHintsConfig`, `ClientHintsSpoofer` | Подмена Client Hints |

### v2.0

| Модуль | Класс | Назначение |
|---|---|---|
| `fingerprint` | `FingerprintManager`, `BrowserFingerprint` | Генерация отпечатков |
| `human_behavior` | `HumanBehaviorEngine`, `BehaviorProfile` | Человечное поведение |
| `account` | `AccountManager`, `AccountStatus` | Управление аккаунтами |
| `action_engine` | `ActionEngine`, `ActionStep`, `ActionType` | Цепочки действий |
| `orchestrator` | `TaskOrchestrator`, `Task`, `TaskPriority` | Оркестрация задач |
| `llm_parse` | `LLMParser`, `LLMConfig` | LLM-парсинг |
| `proxy_rotation` | `ProxyRotator` | Ротация прокси |
| `session_manager` | `SessionManager` | Управление сессиями |
| `har_recorder` | `HARRecorder` | HAR-запись |
| `metrics` | — | Метрики |

### v2.1 (Evolution Layer)

| Модуль | Класс | Назначение |
|---|---|---|
| `workflow_runner` | `WorkflowRunner`, `WorkItem`, `WorkflowResult` | Мост task_template ↔ task_orchestrator |
| `stealth_audit` | `StealthAudit`, `StealthAuditReport` | Единый аудит скрытности (score + benchmark + pipeline) |
| `cloudflare_bypass` | `CloudflareBypass`, `FlareSolverrClient`, `BypassResult` | Обход Cloudflare challenge через FlareSolverr |

---

## 🔧 Скрипты

| Скрипт | Назначение | Запуск |
|---|---|---|
| `screenshot_service.py` | Screenshot-as-a-Service (FastAPI) | `uvicorn scripts.screenshot_service:app` |
| `site_monitor.py` | Мониторинг доступности сайтов | `python3 scripts/site_monitor.py` |
| `crosspost_secure.py` | Безопасный кросспостинг | `python3 scripts/crosspost_secure.py` |
| `secret_manager.py` | Управление секретами | `python3 scripts/secret_manager.py` |
| `security_audit.py` | Аудит безопасности | `python3 scripts/security_audit.py` |
| `monitor_daemon.py` | Демон мониторинга | `python3 scripts/monitor_daemon.py --daemon` |
| `telegram_dashboard.py` | Telegram дашборд | `python3 scripts/telegram_dashboard.py --send` |
| `ghost_protocol_v2.py` | Ghost Protocol v2.0 (стресс-тест) | `PYTHONPATH=src python3 scripts/ghost_protocol_v2.py` |
| `stealth_benchmark_suite.py` | Stealth Benchmark | `python3 scripts/stealth_benchmark_suite.py` |
| `antidetection_lab.py` | Anti-Detection Research Lab | `PYTHONPATH=src python3 scripts/antidetection_lab.py` |
| `distributed_crawler.py` | Distributed Crawler | `PYTHONPATH=src python3 scripts/distributed_crawler.py` |
| `llm_browser_agent.py` | LLM Browser Agent | `PYTHONPATH=src python3 scripts/llm_browser_agent.py` |
| `tg_admin_bot.py` | Telegram Admin Bot | `python3 scripts/tg_admin_bot.py` |

Подробная документация каждого скрипта — в [docs/SCRIPTS.md](docs/SCRIPTS.md).

---

## 📖 Документация

| Документ | Описание |
|---|---|
| [docs/API.md](docs/API.md) | Полный API reference всех модулей |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Архитектура, диаграммы, ADR |
| [docs/SCRIPTS.md](docs/SCRIPTS.md) | Документация каждого скрипта |
| [docs/GUIDES.md](docs/GUIDES.md) | Руководства по использованию |
| [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) | Установка, туториал, troubleshooting |
| [docs/DEPLOY.md](docs/DEPLOY.md) | Деплой в production |
| [CHANGELOG.md](CHANGELOG.md) | История изменений |
| [SPECS.md](SPECS.md) | Спецификации развития |

---

## 🗺 Дорожная карта

### ✅ v1.0 (2026-05-17) — Полный релиз
- 16 stealth-скриптов, 4 уровня защиты
- WebRTC, AudioContext, Client Hints
- 300 тестов
- CI/CD pipeline
- Полная документация

### ✅ v2.0 (2026-05-18) — Advanced Automation
- FingerprintManager — детерминированные отпечатки
- HumanBehaviorEngine — 4 профиля поведения
- AccountManager — SQLite + шифрование
- ActionEngine — цепочки действий
- TaskOrchestrator — оркестрация задач
- LLM Browser Agent — автономный агент
- Distributed Crawler — масштабируемый краулинг
- Ghost Protocol v2 — комплексный стресс-тест
- Stealth Benchmark Suite — систематическое тестирование
- Anti-Detection Lab — исследование векторов
- TG Admin Bot — Telegram-управление

### 🔮 v3.0 (Планируется)
- Kubernetes-масштабирование
- Playwright Test Agents (Planner/Generator/Healer)
- Residential proxy интеграция
- Self-healing локаторы через LLM
- Visual regression testing
- Интеграция со всеми проектами лаборатории

---

## 🔒 Безопасность

- **SSRF Protection** — блокировка внутренних адресов
- **Rate Limiting** — 100 req/min на IP
- **Bearer Token** — аутентификация через заголовок
- **Fernet Encryption** — шифрование cookies и секретов
- **Security Audit** — ежедневная автоматическая проверка
- **Docker Hardening** — no-new-privileges, seccomp, read-only FS

---

## 📝 Лицензия

CC BY-NC-SA 4.0 — Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International.

---

**Лаборатория DoctorM&Ai** | ЗавЛаб Безуми́й Доктор | 2026
