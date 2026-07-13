---
description: "Реестр всех парсинг-источников лаборатории"
type: registry
last_reviewed: 2026-06-30
status: active
---

# 📋 PARSING_REGISTRY — Реестр источников парсинга

## Активные парсеры

### 1. GenericSpider (generic)
- **URL:** любой (параметр при запуске)
- **Тип данных:** универсальный (страницы, ссылки, мета-теги, текст)
- **Spider:** `src/lab_playwright_kit/scrapy_engine/spiders/generic_spider.py`
- **Item:** `ScrapedPage`
- **Stealth:** ✅ StealthMiddleware (HTTP-level)
- **Proxy:** нет
- **Rate limit:** DOWNLOAD_DELAY=1.5, CONCURRENT_REQUESTS_PER_DOMAIN=4
- **Pipelines:** ValidationPipeline + DedupPipeline
- **Retry:** RETRY_TIMES=3
- **Логирование:** loguru
- **Владелец:** все агенты (универсальный)
- **Статус:** ✅ active (production-ready: stealth + pipelines + tests)
- **Заметки:** использует FieldMapping из data_parser для структурирования
- **Тесты:** `tests/test_generic_spider.py` (11 tests)

### 2. ZakupkiSpider (zakupki)
- **URL:** zakupki.gov.ru (44-ФЗ, 223-ФЗ)
- **Тип данных:** госзакупки (номер, цена, заказчик, статус)
- **Spider:** `src/lab_playwright_kit/scrapy_engine/spiders/zakupki_spider.py`
- **Item:** `ScrapedContract`
- **Stealth:** ✅ StealthMiddleware (HTTP-level)
- **Proxy:** требует FlareSolverr (Cloudflare)
- **Rate limit:** DOWNLOAD_DELAY=3.0, CONCURRENT_REQUESTS_PER_DOMAIN=2
- **Pipelines:** ValidationPipeline + DedupPipeline
- **Retry:** RETRY_TIMES=3
- **Логирование:** loguru
- **Владелец:** Бестия (СнабЛаб)
- **Статус:** ✅ active (production-ready: stealth + pipelines + tests)
- **Заметки:** селекторы могут устареть при редизайне zakupki.gov.ru
- **Тесты:** `tests/test_zakupki_spider.py` (8 tests)

### 3. AvitoDealerSpider (avito_dealer)
- **URL:** avito.ru/moskva/avtomobili
- **Тип данных:** дилерские объявления авто (марка, цена, пробег, параметры)
- **Spider:** `src/lab_playwright_kit/scrapy_engine/spiders/avito_dealer_spider.py`
- **Item:** dict (не Scrapy Item!) или ScrapedAuto
- **Stealth:** ✅ StealthMiddleware (HTTP-level)
- **Proxy:** нет
- **Rate limit:** DOWNLOAD_DELAY=2.0, CONCURRENT_REQUESTS_PER_DOMAIN=2
- **Pipelines:** DedupPipeline
- **Retry:** RETRY_TIMES=3
- **Логирование:** loguru
- **Владелец:** не назначен
- **Статус:** ✅ active (production-ready: stealth + pipelines + tests)
- **Заметки:** два режима — parse_avito_listing (BS4) и Scrapy Spider
- **Тесты:** `tests/test_avito_dealer_spider.py` (17 tests)

### 4. PlaywrightPartSpider (auto_parts)
- **URL:** emex.ru, exist.ru, apex.ru, fobil-auto.ru, autoeuro.ru, mymajor.ru, autodoc.ru
- **Тип данных:** автозапчасти (артикул, цена, наличие, доставка)
- **Spider:** `src/lab_playwright_kit/scrapy_engine/spiders/auto_parts/part_spider.py`
- **Item:** `ScrapedPart`
- **Stealth:** ✅ StealthMiddleware (HTTP-level) + Playwright headless
- **Proxy:** нет
- **Rate limit:** DOWNLOAD_DELAY=2, CONCURRENT_REQUESTS=1
- **Pipelines:** ValidationPipeline + DedupPipeline
- **Retry:** RETRY_TIMES=3
- **Логирование:** loguru
- **Владелец:** не назначен
- **Статус:** ✅ active (production-ready: stealth + pipelines + tests)
- **Заметки:** самый зрелый spider, поддерживает API-метод (autodoc), 7 магазинов, 3 метода поиска
- **Тесты:** `tests/test_part_spider.py` (17 tests)

### 5. DataParser (data_parser)
- **URL:** любой (через BrowserManager)
- **Тип данных:** структурированный (11 ниш: ecommerce, news, realty, medtech, jobs, auto, habr, vcru, twitter, telegram, custom)
- **Модуль:** `src/lab_playwright_kit/data_parser.py`
- **Stealth:** через BrowserManager
- **Proxy:** через BrowserManager
- **Rate limit:** нет встроенного
- **Владелец:** все агенты
- **Статус:** ✅ работает
- **Заметки:** лучший вариант для структурированного парсинга

### 6. PriceParser (price_parser)
- **URL:** cmd.ru, invitro.ru, kdl.ru
- **Тип данных:** цены на услуги (медицинские анализы)
- **Модуль:** `src/lab_playwright_kit/price_parser.py`
- **Stealth:** нет
- **Proxy:** нет
- **Rate limit:** нет
- **Владелец:** не назначен
- **Статус:** ⚠️ частично (парсеры привязаны к конкретным сайтам)
- **Заметки:** специфичен для медицинских цен

### 7. LLMParser + SelfHealingParser (llm_parse)
- **URL:** любой (через Playwright Page)
- **Тип данных:** любой (LLM извлекает по запросу)
- **Модуль:** `src/lab_playwright_kit/llm_parse.py`
- **Stealth:** через BrowserManager
- **Proxy:** через BrowserManager
- **Rate limit:** нет
- **Владелец:** все агенты
- **Статус:** ✅ self-healing + кэширование (2026-06-30)
- **Заметки:** лучший fallback для неструктурированных сайтов. SelfHealingParser автоматически исправляет селекторы при изменениях сайта. ParseCache (TTL-based) кэширует результаты. Интегрирован в ParsingOrchestrator как fallback при 0 результатов от основного парсера.
- **Классы:** LLMParser (базовый), SelfHealingParser (автоисправление), ParseCache (TTL-кэш)
- **Интеграция:** ParsingOrchestrator._execute_parser → если spider вернул 0 items → fallback к SelfHealingParser

---

## Пайплайны

### ValidationPipeline
- **Файл:** `src/lab_playwright_kit/scrapy_engine/pipelines/validation_pipeline.py`
- **Что делает:** проверка обязательных полей, валидация цен
- **Item coverage:** все типы (ScrapedPage, ScrapedProduct, ScrapedArticle, ScrapedJob, ScrapedRealty, ScrapedAuto, ScrapedContract)

### DedupPipeline
- **Файл:** `src/lab_playwright_kit/scrapy_engine/pipelines/dedup_pipeline.py`
- **Что делает:** дедупликация по URL (in-memory set)
- **Ограничение:** не персистентный (сбрасывается при перезапуске)

### ExportPipeline
- **Файл:** `src/lab_playwright_kit/scrapy_engine/pipelines/export_pipeline.py`
- **Что делает:** экспорт в JSON/CSV

---

## Middlewares

### StealthMiddleware
- **Файл:** `src/lab_playwright_kit/scrapy_engine/middlewares/stealth_middleware.py`
- **Что делает:** HTTP-level stealth (заголовки, Client Hints, Sec-Fetch)
- **UA pool:** 6 вариантов (Chrome, Firefox, Edge на Windows и Linux)

### ProxyMiddleware
- **Файл:** `src/lab_playwright_kit/scrapy_engine/middlewares/proxy_middleware.py`
- **Что делает:** ротация прокси

### PlaywrightMiddleware
- **Файл:** `src/lab_playwright_kit/scrapy_engine/middlewares/playwright_middleware.py`
- **Что делает:** Playwright-рендеринг для Scrapy-запросов

---

## Интеграции с агентами

| Агент | Проект | Источник | Парсер | Частота | Статус |
|---|---|---|---|---|---|
| Бестия | СнабЛаб | zakupki.gov.ru | ZakupkiSpider | ежедневно | ⚠️ нужен FlareSolverr |
| Бестия | СнабЛаб | поставщики автозапчастей | PlaywrightPartSpider | по запросу | ✅ работает |
| Ворон | lab-monitoring | AI-инструменты, changelog | LLMParser + DataParser | еженедельно | ⚠️ нет автоматизации |
| Котолизатор | vpn-daemon | VPN-панели | DataParser | по запросу | ⚠️ нет автоматизации |
| Сова | autoexpert | справочники авто | DataParser | по запросу | ⚠️ нет автоматизации |

---

## Пробелы (что нужно сделать)

- [x] Единый оркестратор парсинга (parsing_orchestrator.py) — ✅ done
- [x] Stealth для всех spider (2026-06-30: StealthMiddleware для всех 4 spider)
- [x] Self-healing для LLMParser — ✅ done (SelfHealingParser + ParseCache)
- [ ] Персистентная дедупликация (Redis/SQLite вместо in-memory set)
- [ ] Мониторинг качества парсинга (метрики, алерты)
- [ ] Residential proxy интеграция
- [ ] Автоматизация для Ворона, Котолизатора, Совы
- [x] Тесты для ZakupkiSpider (2026-06-30: 8 tests)
- [x] Тесты для AvitoDealerSpider (2026-06-30: 17 tests)
- [ ] Документация по запуску spider (docs/RUN_SPIDERS.md)

---

_Последнее обновление: 2026-06-30 | Автор: Мангуст (mangust)_
