# 🔍 Code Review — lab-playwright-expert v2.0

**Дата:** 2026-05-16
**Ревьюер:** OWL (Senior Code Reviewer)
**Объём:** 50+ файлов, ~12,000+ строк кода
**Статус:** Масштабная v2.0 переработка — новые модули ядра, Ghost Protocol v2, stealth benchmark suite, distributed crawler, LLM browser agent, Docker/CI/CD инфраструктура

---

## Review Summary

**Verdict:** APPROVE WITH CHANGES

**Overview:** Lab Playwright Kit v2.0 — это амбициозное расширение фреймворка автоматизации браузера с добавлением антидетект-модулей (fingerprint management, stealth scripts, human behavior emulation, WebRTC/client hints spoofing), распределённого краулера, LLM-управляемого браузерного агента и production-ready скриншот-сервиса с SSRF-защитой. Архитектура в целом грамотная, модульная, с чётким разделением ответственности. Однако обнаружены критические безопасности и надёжности, которые требуют исправления до деплоя в production.

---

## Critical Issues

### 1. 🔴 SSRF: DNS Rebinding обход валидации URL (БЕЗОПАСНОСТЬ)

**Файл:** `scripts/screenshot_service.py:215-280`
**Severity:** CRITICAL

Валидация URL (`validate_url`) проверяет IP-адрес хоста **при запросе**, но не при **загрузке страницы** в Playwright. Это создаёт уязвимость DNS Rebinding:

```
1. Клент отправляет URL http://attacker.com (резолвоится в публичный IP → валидация OK)
2. Между валидацией и page.goto() DNS TTL истекает
3. DNS теперь указывает на 169.254.169.254 (cloud metadata)
4. Playwright загружает внутренний ресурс
```

**Рекомендуемое исправление:** Резолвить DNS и проверить IP **перед** `page.goto()`, использовать резолвенный IP для HTTP-запроса через `aiohttp`/`httpx` вместо навигации Playwright, либо настроить DNS-кэширование в контейнере.

```python
# Добавить перед page.goto():
import socket
resolved_ips = socket.getaddrinfo(parsed.hostname, port)
for family, type_, proto, canonname, sockaddr in resolved_ips:
    addr = ip_address(sockaddr[0])
    for network in _BLOCKED_NETWORKS:
        if addr in network:
            raise HTTPException(403, "URL resolves to blocked IP")
```

### 2. 🔴 hardcoded токен может попасть в git history (БЕЗОПАСНОСТЬ)

**Файл:** `docker-compose.yml:49`

```yaml
environment:
  - SCREENSHOT_SERVICE_TOKEN=${SCREENSHOT_SERVICE_TOKEN:-change-me-in-production}
```

Дефолтный fallback token `change-me-in-production` `.env` файл не в git, но если кто-то закоммитит `.env` файл или скопирует docker-compose без изменения — сервис запустится с предсказуемым токеном.

**Рекомендуемое исправление:**
- Убрать fallback из docker-compose — пусть контейнер не стартует без токена
- Добавить `docker-compose.override.yml.example` с инструкцией
- В Dockerfile добавить warning при сборке без build-args токена

### 3. 🔴 Screenshot Service: необработанный exception в finally block (НАДЁЖНОСТЬ)

**Файл:** `scripts/screenshot_service.py:610`

```python
finally:
    SS_ACTIVE_BROWSERS.dec()
```

Если `page.goto()` или `browser.new_page()` бросит исключение до того как браузер был инициализирован, метрика `SS_ACTIVE_BROWSERS` будет декрементирована, хотя никогда не инкрементировалась. Это приводит к отрицательному счётчику.

**Исправление:**
```python
_browser_started = False
try:
    async with BrowserManager(...) as browser:
        _browser_started = True
        SS_ACTIVE_BROWSERS.inc()
        ...
finally:
    if _browser_started:
        SS_ACTIVE_BROWSERS.dec()
```

---

## Important Issues

### 4. 🟠 Ленивое обнаружение: существует зависимость от browser.stop() vs browser.close()

**Файлы:** `src/lab_playwright_kit/browser_manager.py`, множество скриптов

Внутри `stealth_benchmark_suite.py`, `antidetection_lab.py`, `distributed_crawler.py` и `llm_browser_agent.py` вызывается `browser.stop()` — но `BrowserManager.stop()` вызывается внутри `async with` блока, а затем повторно в `finally`. Это может звон `runtime error: cannot stop an already stopped browser`.

**Рекомендуция:** Добавить guard в `BrowserManager.stop()`:
```python
async def stop(self):
    if self._closed:
        return
    self._closed = True
    # ... cleanup ...
```

### 5. 🟠 Отсутствие rate limiter для /health и /metrics endpoints

**Файл:** `scripts/screenshot_service.py:510-530`

Endpoints `/health` и `/metrics` публичные и без rate limiting. При высокой частоте polling-а (Prometheus обычно делает scrapeкаждые 15-30 секунд) это нормально, но отсутствие хоть какого-либо ограничения делает возможной атака типа amplification если сервис за NAT и один клиент генерирует тысячи rps.

**Рекомендуция:** Добавить отдельный, мягкий rate limit для данных endpoints (например, 1000 req/min без аутентификации).

### 6. 🟠 ну и от blood bot

**Файл:** `scripts/distributed_crawler.py:120-130`

Функция `main()` возвращает `None` если `print_help()` вместо `sys.exit(1)`:
```python
if not args.config and not args.seed:
    parser.print_help()
    logger.error("Необходимо указать --config или --seed")
    sys.exit(1)
```

Это корректно, но в `main()` функция `asyncio.run(main())` вызывается без `try/except`. Unhandled exception'ы в асинхронном коде могут привести к "тихому" падению краулера без логирования.

**Рекомендуция:** Обернуть `asyncio.run(main())` в try/except с логированием traceback.

### 7. 🟠 `playwright install chromium` — нет проверки успешности

**Файл:** `Dockerfile:52-54`

```dockerfile
RUN pip install --no-cache-dir playwright>=1.59.0 \
    && playwright install chromium \
    && rm -rf /root/.cache/pip
```

Если `playwright install chromium` частично пройдёт (скачает, но не установит зависимости), образ соберётся "успешно", но при запуске браузер не будет. Нет верификации.

**Рекомендация:** Добавить проверку в конце сборки:
```dockerfile
RUN python -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"
```

---

## Suggestions

### 💡 8. html: "report" → "Report" (типография)

**Файл:** `scripts/ghost_protocol_v2.py:710` (строка с `report_path.write_text(html, encoding="utf-8")`)

Путь к отчёту на диске `battle_report_v2_20260516_120000.html` — это нормальная конвенция. Сам файл генерируется корректно.

**Рекомендуция:** Хэш-суммы для верификации целостности — использовать HTML формат, то не MD, что может привести к несовместимости в некоторых CI системах.

### 💡 9. фingerprint: данные в фingerprint_test

**Файл:** `src/lab_playwright_kit/fingerprint.py`

`BrowserFingerprint.generate()` использует `random.Random()` без seed, что означает, что фингерпринт меняется при каждом вызове с одним profile_id.

**Рекомендация:** Понять как идентификатор для BrowserFingerprint:

```python
# Добавить profile_id seed
self._rng = random.Random(profile_id)
```

**Важно:** Текущая логака `profile_id` = identity (user_id профиля), а seed для рандома = profile_id. Без этого **один и тот же** profile_id генерирует каждый раз разный fingerprint, что ломает идентичность сессии.

### 💡 10. Screenshot Service: Нет timeout на саму операцию скриншота

**Файл:** `scripts/screenshot_service.py:615`

`page.wait_for_timeout(request.wait_ms)` — пользовательский параметр `wait_ms` ограничен `MAX_WAIT_MS = 30000`, но суммарный timeout на весь endpoint не ограничен. Если сайт долго грузится (не отвечает, но и не таймаутит), запрос может висеть очень долго.

**Рекомендация:** Добавить общий timeout на endpoint через FastAPI middleware или `asyncio.wait_for()`:
```python
async def create_screenshot(...):
    try:
        result = await asyncio.wait_for(_create_screenshot_impl(...), timeout=60)
    except asyncio.TimeoutError:
        raise HTTPException(504, "Screenshot timed out")
```

### 💡 11. Тесты: Нет единого Makefile команды `make test-all` которая запускает все файлы

Тесты разбиты на файлы (`test_v2_modules.py`, `test_stealth_advanced.py`, `test_security.py`, `test_v2_e2e.py`, `test_new_capabilities.py`, `test_session_manager.py`, `test_proxy_rotation.py`, `test_har_recorder.py`, `test_kit.py`), но `make test-all` запускает только `pytest tests/ -v --tb=short` — что нормально, но нет разделения на unit/integration/e2e.

**Рекомендация:** Добавить pytest markers (`@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.e2e`) и отдельные команды в Makefile.

### 💡 12. Docker: Нет .dockerignore

**Файл:** отсутствует `.dockerignore`

Без `.dockerignore` в контекст сборки попадают `.venv/`, `__pycache__/`, `tests/`, `.git/` — это увеличивает время сборки и размер контекста.

**Рекомендация:** Создать `.dockerignore`:
```
.venv/
__pycache__/
.git/
tests/
*.egg-info/
.pytest_cache/
.mypy_cache/
```

---

## What's Done Well

### ✅ Архитектура модулей ядра

Разделение на `browser_manager`, `fingerprint`, `stealth`, `behavior`, `screenshot`, `proxy`, `session`, `har`, `metrics` — чистое, с чёткими границами. Каждый модуль имеет одну ответственность. Отличная работа.

### ✅ SSRF Protection в Screenshot Service

Многоуровневая валидация URL (схема, хост, IP, regex, path traversal, CRLF) — это действительно грамотная реализация. За исключением DNS Rebinding (Critical #1), защита продумана хорошо.

### ✅ Docker Multi-stage Build

Builder → Browser Installer → Runtime — правильная стратегия для минимизации размера образа. Non-root user, dropped capabilities, no-new-privileges, read-only tmpfs — всё на месте.

### ✅ CI/CD Pipeline

Полный pipeline: lint → type-check → test (matrix 3.10/3.11/3.12) → build → docker-build → security-scan (Trivy + Bandit). Параллельные jobs, кэширование, concurrency groups — профессиональный уровень.

### ✅ Stealth Module Design

Stealth модули (webdriver, plugins, languages, permissions, chrome runtime, canvas, webgl, audio, webrtc, client hints) с 4 уровнями конфигурации (minimal → full) — гибко и масштабируемо. Определение через dataclass + генерация JS скриптов — удобно для тестирования.

### ✅ Ghost Protocol v2 Battle Report

HTML-отчёт с CSS-стилизацией, агрегацией метрик по 7 модулям — отличная визуализация результатов тестирования. Это делает фреймворк удобным для отладки и демонстрации.

---

## Verification Story

- **Tests reviewed:** Да — 9 тестовых файлов в `tests/`, покрывающих модули ядра, stealth, security (SSRF), E2E, proxy, HAR, session manager. Тесты используют pytest с маркерами `slow`, `not browser`. Тесты SSRF покрывают 15+ векторов атак.
- **Build verified:** Частично — CI pipeline определён в `.github/workflows/ci.yml` и `security.yml`. Локальная сборка не проверялась.
- **Security checked:** Да — подробный анализ SSRF, аутентификации, rate limiting, Docker security. Обнаружена 1 критическая уязвимость (DNS Rebinding) и 1 важная (hardcoded fallback token).

---

## Резюме

| Категория | Количество |
|-----------|------------|
| Critical | 3 |
| Important | 4 |
| Suggestions | 5 |

**Общая оценка:** Код написан на высоком уровне. Архитектура продумана, безопасность в основном грамотная, CI/CD профессиональный. Критические проблемы связаны с edge-cases (DNS Rebinding, race conditions в метриках) и конфигурацией по умолчанию — типичные для проектов такого масштаба. После исправления Critical #1 и #2 проект готов к production deployment.
