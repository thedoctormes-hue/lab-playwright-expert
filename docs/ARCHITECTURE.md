# 🏗 Архитектура — Lab Playwright Kit

Архитектурные решения, диаграммы и ADR.

---

## Содержание

- [Обзор архитектуры](#обзор-архитектуры)
- [Слои системы](#слои-системы)
- [Поток данных](#поток-данных)
- [Модульная структура](#модульная-структура)
- [Архитектурные решения (ADR)](#архитектурные-решения-adr)
  - [ADR-001: Модульная архитектура](#adr-001-модульная-архитектура)
  - [ADR-002: Stealth как уровни](#adr-002-stealth-как-уровни)
  - [ADR-003: Fingerprint консистентность](#adr-003-fingerprint-консистентность)
  - [ADR-004: Human Behavior профили](#adr-004-human-behavior-профили)
  - [ADR-005: Account lifecycle](#adr-005-account-lifecycle)
  - [ADR-006: Task Orchestration](#adr-006-task-orchestration)
  - [ADR-007: LLM Agent Loop](#adr-007-llm-agent-loop)
- [Сравнение версий](#сравнение-версий)
- [Ограничения](#ограничения)

---

## Обзор архитектуры

```
┌─────────────────────────────────────────────────────────────────┐
│                        SCRIPTS LAYER                            │
│  screenshot_service │ site_monitor │ ghost_protocol │ tg_bot    │
├─────────────────────────────────────────────────────────────────┤
│                     APPLICATION LAYER                           │
│  LLM Agent │ Distributed Crawler │ Anti-Detection Lab          │
├─────────────────────────────────────────────────────────────────┤
│                       DOMAIN LAYER                              │
│  ActionEngine │ TaskOrchestrator │ AccountManager              │
│  FingerprintManager │ HumanBehaviorEngine │ CaptchaSolver      │
├─────────────────────────────────────────────────────────────────┤
│                      CORE LAYER                                 │
│  BrowserManager │ StealthConfig │ ScreenshotMaker │ PageParser  │
│  NetworkInterceptor │ ScreencastRecorder │ ARIASnapshot        │
├─────────────────────────────────────────────────────────────────┤
│                    INFRASTRUCTURE                               │
│  Playwright │ SQLite │ Fernet │ FastAPI │ aiogram │ loguru     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Слои системы

### 1. Infrastructure (инфраструктура)
Базовые зависимости, не содержат бизнес-логики:
- **Playwright** — автоматизация браузера
- **SQLite** — хранение данных
- **Fernet** — шифрование
- **FastAPI** — HTTP API
- **aiogram** — Telegram Bot
- **loguru** — логирование

### 2. Core (ядро)
Базовые операции с браузером:
- **BrowserManager** — жизненный цикл браузера
- **StealthConfig** — конфигурация антидетекта
- **ScreenshotMaker** — скриншоты
- **PageParser** — парсинг
- **NetworkInterceptor** — перехват запросов
- **ScreencastRecorder** — запись видео
- **ARIASnapshot** — accessibility tree
- **ClockController** — манипуляция временем

### 3. Domain (домен)
Бизнес-логика автоматизации:
- **ActionEngine** — цепочки действий
- **TaskOrchestrator** — оркестрация задач
- **AccountManager** — управление аккаунтами
- **FingerprintManager** — генерация отпечатков
- **HumanBehaviorEngine** — человечное поведение
- **CaptchaSolver** — решение капчи

### 4. Application (приложение)
Сложные сценарии:
- **LLM Browser Agent** — автономный агент
- **Distributed Crawler** — масштабируемый краулинг
- **Anti-Detection Lab** — исследование векторов

### 5. Scripts (скрипты)
Исполняемые инструменты:
- **screenshot_service** — HTTP API
- **site_monitor** — мониторинг
- **ghost_protocol** — стресс-тест
- **tg_admin_bot** — Telegram-управление

---

## Поток данных

### Stealth-пайплайн

```
User Request
    │
    ▼
┌──────────────┐
│ StealthConfig │ ← Уровень (minimal/standard/advanced/full)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ apply_stealth │ ← Инъекция JS-скриптов через add_init_script
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Fingerprint   │ ← Генерация консистентного отпечатка
│ Manager       │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Fingerprint   │ ← Применение к странице (WebGL, Canvas, Audio,
│ apply()       │   Screen, Hardware, Timezone, Fonts)
└──────┬───────┘
       │
       ▼
   Browser Page (защищённый)
```

### Agent Loop

```
┌─────────────┐
│  Perception  │ ← ARIA Snapshot + Page Title
└──────┬──────┘
       │
       ▼
┌──────────────┐
│   Planning    │ ← LLM (Perception → Decision)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│    Action     │ ← navigate/click/type/scroll/extract/screenshot/wait/done
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Memory      │ ← AgentMemory (goal, visited_urls, actions, extracted_data)
└──────┬───────┘
       │
       └──→ Perception (next step)
```

### Task Orchestration

```
Task Queue (priority)
    │
    ▼
┌──────────────┐
│ Orchestrator  │ ← workers=3, rate limiting
└──────┬───────┘
       │
       ├──→ Worker 1 → ActionEngine → Browser
       ├──→ Worker 2 → ActionEngine → Browser
       └──→ Worker 3 → ActionEngine → Browser
```

---

## Модульная структура

```
src/lab_playwright_kit/
├── __init__.py              # Публичный API (все экспорты)
├── browser.py               # BrowserManager
├── stealth.py               # StealthConfig, apply_stealth
├── stealth_webrtc.py        # WebRTC leak protection
├── stealth_audio.py         # AudioContext spoofing
├── stealth_client_hints.py  # Client Hints spoofing
├── stealth_benchmark.py     # Автоматический бенчмарк
├── fingerprint.py           # FingerprintManager, BrowserFingerprint
├── human_behavior.py        # HumanBehaviorEngine, BehaviorProfile
├── account_manager.py       # AccountManager, AccountStatus
├── action_engine.py         # ActionEngine, ActionStep, ActionType
├── task_orchestrator.py     # TaskOrchestrator, Task, TaskPriority
├── captcha_solver.py        # CaptchaSolver
├── screenshot.py            # ScreenshotMaker
├── parser.py                # PageParser, PageContent
├── network.py               # NetworkInterceptor
├── screencast.py            # ScreencastRecorder
├── aria_snapshot.py         # ARIASnapshot, ARIADiff
├── clock.py                 # ClockController
├── llm_parse.py             # LLMParser, LLMConfig
├── proxy_rotation.py        # ProxyRotator
├── session_manager.py       # SessionManager
├── har_recorder.py          # HARRecorder
├── metrics.py               # Метрики
└── vpn_proxy.py             # VPN Proxy
```

**Принципы:**
- Каждый модуль = 1 файл = 1 ответственность
- Нет циклических зависимостей
- Все публичные классы экспортируются через `__init__.py`
- Внутренняя реализация скрыта (приватные методы `_`)

---

## Архитектурные решения (ADR)

### ADR-001: Модульная архитектура

**Статус:** Принято

**Контекст:** Нужна гибкая архитектура, позволяющая добавлять новые модули без изменения существующих.

**Решение:** Модульная архитектура с чистым разделением слоёв:
- Core не зависит от Domain
- Domain не зависит от Application
- Scripts зависят от всех слоёв

**Последствия:**
- ✅ Легко добавлять новые модули
- ✅ Тестируемость каждого модуля отдельно
- ✅ Возможность использовать только нужные модули
- ⚠️ Больше файлов для навигации

---

### ADR-002: Stealth как уровни

**Статус:** Принято

**Контекст:** Разные задачи требуют разного уровня защиты. Для простого скриншота не нужен полный антидетект.

**Решение:** 4 уровня stealth-защиты:
- `minimal` — 1 скрипт (webdriver detection)
- `standard` — 6 скриптов (+ chrome runtime, permissions, plugins)
- `advanced` — 16 скриптов (+ canvas, webgl, audio, screen, hardware)
- `full` — 16 + случайный User-Agent

**Последствия:**
- ✅ Гибкость: выбирать уровень под задачу
- ✅ Производительность: меньше скриптов = быстрее
- ⚠️ Нужно документировать что входит в каждый уровень

---

### ADR-003: Fingerprint консистентность

**Статус:** Принято

**Контекст:** Несогласованные отпечатки (например, UA говорит "Chrome Windows", а WebGL показывает "SwiftShader") — красный флаг для антибот-систем.

**Решение:** `FingerprintManager.generate()` создаёт консистентный набор:
- UA соответствует GPU (Chrome → ANGLE, Firefox → WebGL)
- GPU соответствует экрану (высокое разрешение → мощная видеокарта)
- Экран соответствует железу (4K → 32GB RAM)
- Все параметры детерминированы от `profile_name` (seed)

**Последствия:**
- ✅ Реалистичные отпечатки
- ✅ Детерминизм: тот же profile_name = тот же отпечаток
- ⚠️ База данных отпечатков требует обновления

---

### ADR-004: Human Behavior профили

**Статус:** Принято

**Контекст:** Разные сценарии требуют разного стиля поведения. Соцсети — быстрые движения, исследование — медленные.

**Решение:** 4 профиля поведения:
- `casual_reader` — медленный (800-2000ms мышь, 120 WPM)
- `power_user` — быстрый (300-800ms, 200 WPM)
- `researcher` — средний (500-1500ms, 150 WPM)
- `social_media` — активный (400-1200ms, 180 WPM)

**Последствия:**
- ✅ Реалистичное поведение под задачу
- ✅ Кривые Безье для мыши, переменная скорость набора
- ⚠️ Профили требуют калибровки под конкретные сайты

---

### ADR-005: Account lifecycle

**Статус:** Принято

**Контекст:** Управление множеством аккаунтов требует структурированного подхода: создание, разогрев, активность, кулдаун, бан.

**Решение:** `AccountManager` с SQLite + Fernet:
- 6 статусов: CREATED → WARMUP → ACTIVE → COOLDOWN → BANNED → DEAD
- Шифрование паролей (Fernet)
- История действий
- Статистика по платформам

**Последствия:**
- ✅ Безопасное хранение паролей
- ✅ Полный жизненный цикл
- ✅ Масштабируемость через SQLite
- ⚠️ Требует управления ключами шифрования

---

### ADR-006: Task Orchestration

**Статус:** Принято

**Контекст:** Множество задач с разными приоритетами и rate limits требуют оркестрации.

**Решение:** `TaskOrchestrator`:
- 5 уровней приоритета: CRITICAL → HIGH → NORMAL → LOW → BACKGROUND
- Rate limiting по платформам
- Параллельные воркеры
- Статистика выполнения

**Последствия:**
- ✅ Контроль нагрузки на площадки
- ✅ Приоритизация критических задач
- ✅ Масштабируемость через воркеры
- ⚠️ Сложность отладки при множестве воркеров

---

### ADR-007: LLM Agent Loop

**Статус:** Принято

**Контекст:** Автономная навигация по сайтам требует адаптивного поведения, а не жёстких скриптов.

**Решение:** Agent Loop: Perception → Planning → Action → Memory:
- **Perception:** ARIA Snapshot + Page Title
- **Planning:** LLM принимает решение на основе состояния
- **Action:** Выполнение (navigate/click/type/scroll/extract/screenshot/wait/done)
- **Memory:** AgentMemory хранит контекст

**Последствия:**
- ✅ Адаптивность к изменениям DOM
- ✅ Автономная работа без жёстких скриптов
- ✅ Mock-режим для тестирования без API-ключа
- ⚠️ Зависимость от LLM API
- ⚠️ Необходимость валидации действий агента

---

## Сравнение версий

| Аспект | v1.0 | v2.0 |
|---|---|---|
| **Модули** | 12 | 25 |
| **Скрипты** | 7 | 13 |
| **Тесты** | 300 | 300+ |
| **Stealth** | 16 скриптов | 16 + fingerprint + behavior |
| **Fingerprint** | Нет | FingerprintManager |
| **Behavior** | Нет | 4 профиля |
| **Accounts** | Нет | AccountManager |
| **Actions** | Нет | ActionEngine |
| **Orchestration** | Нет | TaskOrchestrator |
| **LLM** | Только парсинг | Полноценный агент |
| **Crawling** | Нет | Distributed Crawler |
| **Research** | Нет | Anti-Detection Lab |
| **Management** | Нет | TG Admin Bot |

---

## Ограничения

### Известные ограничения

1. **Headless Chrome** — некоторые сайты обнаруживают headless режим. Решение: `StealthConfig.advanced()` или `full()`.

2. **WebGL SwiftShader** — headless Chrome использует SwiftShader вместо реального GPU. Решение: `FingerprintManager.apply()` подменяет renderer.

3. **Canvas одинаковый** — headless Chrome выдаёт одинаковый canvas. Решение: canvas noise через `FingerprintManager`.

4. **WebRTC leak** — реальный IP может утечь через WebRTC. Решение: `WebRTCProtector`.

5. **LLM зависимость** — LLM Browser Agent требует API-ключ. Решение: Mock-режим для тестирования.

6. **Rate limiting** — агрессивный краулинг может привести к блокировке. Решение: `TaskOrchestrator` с rate limiting.

### Планы по улучшению

- Kubernetes-масштабирование
- Residential proxy интеграция
- Self-healing локаторы через LLM
- Visual regression testing
- Playwright Test Agents

---

*Документация актуальна для v2.0. Последнее обновление: 2026-05-18*
