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
- **Stealth:** нет (базовый Scrapy)
- **Proxy:** нет
- **Rate limit:** DOWNLOAD_DELAY=1.5, CONCURRENT_REQUESTS_PER_DOMAIN=4
- **Владелец:** все агенты (универсальный)
- **Статус:** ⚠️ работает, но без stealth
- **Заметки:** использует FieldMapping из data_parser для структурирования

### 2. ZakupkiSpider (zakupki)
- **URL:** zakupki.gov.ru (44-ФЗ, 223-ФЗ)
- **Тип данных:** госзакупки (номер, цена, заказчик, статус)
- **Spider:** `src/lab_playwright_kit/scrapy_engine/spiders/zakupki_spider.py`
- **Item:** `ScrapedContract`
- **Stealth:** нет
- **Proxy:** требует FlareSolverr (Cloudflare)
- **Rate limit:** DOWNLOAD_DELAY=3.0, CONCURRENT_REQUESTS_PER_DOMAIN=2
- **Владелец:** Бестия (СнабЛаб)
- **Статус:** ⚠️ работает, требует FlareSolverr для Cloudflare
- **Заметки:** селекторы могут устареть при редизайне zakupki.gov.ru

### 3. AvitoDealerSpider (avito_dealer)
- **URL:** avito.ru/moskva/avtomobili
- **Тип данных:** дилерские объявления авто (марка, цена, пробег, параметры)
- **Spider:** `src/lab_playwright_kit/scrapy_engine/spiders/avito_dealer_spider.py`
- **Item:** dict (не Scrapy Item!) или ScrapedAuto
- **Stealth:** нет
- **Proxy:** нет
- **Rate limit:** нет (single-threaded)
- **Владелец:** не назначен
- **Статус:** ⚠️ работает как standalone-парсинг (BeautifulSoup), Scrapy-версия без stealth
- **Заметки:** два режима — parse_avito_listing (BS4) и Scrapy Spider

### 4. PlaywrightPartSpider (auto_parts)
- **URL:** emex.ru, exist.ru, apex.ru, fobil-auto.ru, autoeuro.ru, mymajor.ru, autodoc.ru
- **Тип данных:** автозапчасти (артикул, цена, наличие, доставка)
- **Spider:** `src/lab_playwright_kit/scrapy_engine/spiders/auto_parts/part_spider.py`
- **Item:** `ScrapedPart`
- **Stealth:** Playwright headless
- **Proxy:** нет
- **Rate limit:** DOWNLOAD_DELAY=2, CONCURRENT_REQUESTS=1
- **Владелец:** не назначен
- **Статус:** ✅ работает (7 магазинов, 3 метода поиска)
- **Заметки:** самый зрелый spider, поддерживает API-метод (autodoc)

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

### 7. LLMParser (llm_parse)
- **URL:** любой (через Playwright Page)
- **Тип данных:** любой (LLM извлекает по запросу)
- **Модуль:** `src/lab_playwright_kit/llm_parse.py`
- **Stealth:** через BrowserManager
- **Proxy:** через BrowserManager
- **Rate limit:** нет
- **Владелец:** все агенты
- **Статус:** ⚠️ работает, но нет self-healing, нет кэширования
- **Заметки:** лучший fallback для неструктурированных сайтов

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

- [ ] Единый оркестратор парсинга (parsing_orchestrator.py)
- [ ] Stealth для всех spider (сейчас только StealthMiddleware для Scrapy)
- [ ] Self-healing для LLMParser
- [ ] Персистентная дедупликация (Redis/SQLite вместо in-memory set)
- [ ] Мониторинг качества парсинга (метрики, алерты)
- [ ] Residential proxy интеграция
- [ ] Автоматизация для Ворона, Котолизатора, Совы
- [ ] Тесты для ZakupkiSpider (нет тестов)
- [ ] Тесты для AvitoDealerSpider (нет тестов)
- [ ] Документация по запуску spider (docs/RUN_SPIDERS.md)

---

_Последнее обновление: 2026-06-30 | Автор: Мангуст (mangust)_
