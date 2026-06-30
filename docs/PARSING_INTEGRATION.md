# 📡 PARSING_INTEGRATION — Интеграция парсинга с агентами лаборатории

**Статус:** ✅ Активна  
**Версия:** 1.0  
**Дата:** 2026-06-30  
**Автор:** Мангуст (mangust) — Этап 4 (ЕБШ)

---

## Обзор

Единая система парсинга данных для 5 агентов лаборатории DoctorM&Ai.  
Оркестратор: `src/lab_playwright_kit/parsing_orchestrator.py`  
Скрипт запуска: `scripts/parsing_cron.sh`  
Конфиги агентов: `config/agents/*.yaml`

## Архитектура

```
┌─────────────────────────────────────────────────────────┐
│                  parsing_orchestrator.py                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │  SOURCE   │  │  Parser  │  │  Stealth │              │
│  │ REGISTRY  │  │  Router  │  │  Levels  │              │
│  └──────────┘  └──────────┘  └──────────┘              │
│        │              │              │                   │
│  ┌─────▼──────────────▼──────────────▼─────┐            │
│  │           ParseTask → ParseResult        │            │
│  └─────────────────────────────────────────┘            │
│        │              │              │                   │
│  ┌─────▼────┐  ┌─────▼────┐  ┌─────▼────┐              │
│  │  Cache   │  │  Metrics │  │  Rate    │              │
│  │  (TTL)   │  │(Promethe)│  │  Limiter │              │
│  └──────────┘  └──────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────┘
         │         │         │         │         │
    ┌────▼───┐┌───▼──┐┌───▼──┐┌───▼──┐┌───▼────┐
    │Бестия  ││Ворон ││Кото- ││ Сова ││Стрейк-│
    │СнабЛаб ││Монит.││лизат.││Авто  ││брехер │
    └────────┘└──────┘└──────┘└──────┘└────────┘
```

## Агенты и их интеграции

### 1. 🐾 Бестия (СнабЛаб) — Госзакупки

| Параметр | Значение |
|---|---|
| **Источник** | zakupki.gov.ru (44-ФЗ, 223-ФЗ) |
| **Парсер** | ZakupkiSpider |
| **Частота** | Ежедневно 06:00 UTC |
| **Stealth** | Advanced (Cloudflare bypass) |
| **Proxy** | Требуется (FlareSolverr) |
| **Конфиг** | `config/agents/bestia.yaml` |

**Ключевые слова:** стройка, оборудование, медицина, строительство, ремонт

**Запуск:**
```bash
./scripts/parsing_cron.sh bestia
```

**Cron:**
```
0 6 * * * cd /root/LabDoctorM/projects/lab-playwright-expert && bash scripts/parsing_cron.sh bestia >> /root/LabDoctorM/logs/parsing/bestia.log 2>&1
```

---

### 2. 🐦 Ворон (lab-monitoring) — AI Changelog

| Параметр | Значение |
|---|---|
| **Источники** | OpenAI Blog, Google AI Blog, Anthropic News, HuggingFace |
| **Парсер** | LLMParser (fallback: DataParser) |
| **Частота** | Еженедельно (Пн 10:00 UTC) |
| **Stealth** | Standard |
| **Конфиг** | `config/agents/voron.yaml` |

**Анализ:** Автоматический анализ изменений с severity levels:
- **CRITICAL:** breaking changes, deprecations, price increases
- **WARNING:** new features, updates, beta releases
- **INFO:** blog posts, announcements

**Запуск:**
```bash
./scripts/parsing_cron.sh voron
```

**Cron:**
```
0 10 * * 1 cd /root/LabDoctorM/projects/lab-playwright-expert && bash scripts/parsing_cron.sh voron >> /root/LabDoctorM/logs/parsing/voron.log 2>&1
```

---

### 3. 🐱 Котолизатор (VPN) — VPN Panel Monitor

| Параметр | Значение |
|---|---|
| **Источники** | localhost VPN panels, ipify.org, dnsleaktest.com |
| **Парсер** | DataParser (profile=generic) |
| **Частота** | Каждые 6 часов |
| **Stealth** | None (internal) |
| **Конфиг** | `config/agents/kotolizator.yaml` |

**Проверки:**
- VPN tunnel status (HTTP 200)
- IP change detection (ipify)
- DNS leak detection
- Internet connectivity

**Алерты:** При падении VPN, IP leak, DNS leak, высокой latency (>200ms)

**Запуск:**
```bash
./scripts/parsing_cron.sh kotolizator
```

**Cron:**
```
0 */6 * * * cd /root/LabDoctorM/projects/lab-playwright-expert && bash scripts/parsing_cron.sh kotolizator >> /root/LabDoctorM/logs/parsing/kotolizator.log 2>&1
```

---

### 4. 🦉 Сова (autoexpert) — Автозапчасти

| Параметр | Значение |
|---|---|
| **Источники** | exist.ru, autodoc.ru, emex.ru |
| **Парсер** | PlaywrightPartSpider |
| **Частота** | По запросу (API) |
| **Stealth** | Standard |
| **Конфиг** | `config/agents/sova.yaml` |

**API Endpoint:** `GET /api/v1/sova/search?q=<запрос>&source=<источник>&limit=<N>`

**Примеры запросов:**
- `BMW X5` — поиск по марке/модели
- `VAG 071121160BT` — поиск по артикулу
- `Toyota Camry 2020` — поиск по марке и году

**Запуск:**
```bash
./scripts/parsing_cron.sh sova
./scripts/parsing_cron.sh sova --query "Toyota Camry"
```

---

### 5. ⚡ Стрейкбрехер (fullstack) — E2E Test Data

| Параметр | Значение |
|---|---|
| **Источники** | the-internet.herokuapp.com, demoqa.com, saucedemo.com |
| **Парсер** | DataParser |
| **Частота** | При CI/CD trigger |
| **Stealth** | None (test environments) |
| **Конфиг** | `config/agents/streikbrecher.yaml` |

**Интеграция:** Myrmex Control (http://localhost:9090)

**Типы данных:**
- CSS/XPath селекторы
- Form data (labels, inputs, validation)
- Expected values для assertions
- Page Objects для E2E тестов

**Запуск:**
```bash
./scripts/parsing_cron.sh streikbrecher
```

---

## Быстрый старт

### Тест импортов (без реального парсинга):
```bash
./scripts/parsing_cron.sh test
```

### Запуск одного агента (dry run):
```bash
./scripts/parsing_cron.sh bestia --dry-run
```

### Запуск всех агентов:
```bash
./scripts/parsing_cron.sh all
```

### Просмотр метрик:
```bash
./scripts/parsing_cron.sh metrics
```

---

## Добавление нового агента

1. Создайте конфиг `config/agents/<agent_name>.yaml`
2. Добавьте функцию `run_<agent_name>()` в `scripts/parsing_cron.sh`
3. Добавьте case в `main()` функцию скрипта
4. Обновите этот документ
5. Запустите `test` для проверки импортов

---

## Мониторинг и метрики

### Prometheus метрики:
```
parse_requests_total{status="success|failed|cached"}
parse_items_total
parse_duration_seconds
parse_success_rate
parse_requests_by_domain{domain="..."}
```

### Логи:
- `/root/LabDoctorM/logs/parsing/<agent>_<timestamp>.log`

### Кэширование:
- TTL: 3600s (настраивается в orchestrator)
- Ключ: `md5(url:schema:parser_type:max_pages)`
- In-memory (не персистентный)

---

## Безопасность

- **ZakupkiSpider** требует FlareSolverr для Cloudflare bypass
- **Прокси** настраиваются в `config/vpn_proxies.yaml`
- **Rate limiting** автоматический через оркестратор
- **Stealth levels** от NONE до FULL в зависимости от источника

---

## Roadmap

- [ ] Persistent cache (Redis/SQLite вместо in-memory)
- [ ] Residential proxy интеграция
- [ ] Self-healing для всех парсеров
- [ ] Web UI для мониторинга
- [ ] Тесты для всех spider
- [ ] Алерты через единую систему алертов лаборатории

---

_Последнее обновление: 2026-06-30 | Автор: Мангуст (mangust)_
