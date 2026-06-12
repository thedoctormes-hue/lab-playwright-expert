# 📚 API Reference — Lab Playwright Kit v2.0

Полный справочник всех модулей, классов и методов.

---

## Содержание

- [Ядро](#ядро)
  - [BrowserManager](#browsermanager)
  - [StealthConfig](#stealthconfig)
  - [ScreenshotMaker](#screenshotmaker)
  - [PageParser](#pageparser)
  - [NetworkInterceptor](#networkinterceptor)
  - [ScreencastRecorder](#screencastrecorder)
  - [ARIASnapshot](#ariasnapshot)
  - [ClockController](#clockcontroller)
- [Антидетект](#антидетект)
  - [WebRTCProtector / WebRTCConfig](#webrtcprotector--webrtcconfig)
  - [AudioSpoofer / AudioConfig](#audiopoofer--audioconfig)
  - [ClientHintsSpoofer / ClientHintsConfig](#clienthintsspoofer--clienthintsconfig)
- [v2.0 Модули](#v20-модули)
  - [FingerprintManager / BrowserFingerprint](#fingerprintmanager--browserfingerprint)
  - [HumanBehaviorEngine / BehaviorProfile](#humanbehaviorengine--behaviorprofile)
  - [AccountManager](#accountmanager)
  - [ActionEngine / ActionStep / ActionType](#actionengine--actionstep--actiontype)
  - [TaskOrchestrator / Task / TaskPriority](#taskorchestrator--task--taskpriority)
  - [ProxyRotator](#proxyrotator)
  - [SessionManager](#sessionmanager)
  - [HARRecorder](#harrecorder)
  - [LLMParser / LLMConfig](#llmparser--llmconfig)
  - [CaptchaSolver](#captchasolver)
  - [StealthBenchmark](#stealthbenchmark)

---

## Ядро

### BrowserManager

```python
from lab_playwright_kit.browser import BrowserManager
```

Управление жизненным циклом браузера Playwright.

```python
# Контекстный менеджер (рекомендуется)
async with BrowserManager(
    headless=True,
    browser_type="chromium",
    timeout=30000,
    viewport={"width": 1920, "height": 1080},
    user_agent="Mozilla/5.0 ...",
    proxy={"server": "socks5://127.0.0.1:9050"},
) as browser:
    page = await browser.new_page()
    await page.goto("https://example.com")
```

**Параметры:**

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `headless` | `bool` | `True` | Режим без GUI |
| `browser_type` | `str` | `"chromium"` | Тип браузера |
| `timeout` | `int` | `30000` | Таймаут операций (мс) |
| `viewport` | `dict` | `{"width": 1920, "height": 1080}` | Размер viewport |
| `user_agent` | `str` | `""` | User-Agent |
| `proxy` | `dict` | `None` | Прокси в формате Playwright |

**Методы:**

| Метод | Возвращает | Описание |
|---|---|---|
| `start()` | `None` | Запустить браузер |
| `stop()` | `None` | Остановить браузер |
| `new_page()` | `Page` | Создать новую страницу |
| `close_page(page)` | `None` | Закрыть страницу |

---

### StealthConfig

```python
from lab_playwright_kit.stealth import StealthConfig, apply_stealth
```

Конфигурация антидетекта с 4 уровнями защиты.

```python
# 4 уровня
config = StealthConfig.minimal()    # 1 скрипт
config = StealthConfig.standard()   # 6 скриптов
config = StealthConfig.advanced()   # 16 скриптов
config = StealthConfig.full()       # 16 + random UA

# Применение
await apply_stealth(page, config)
```

**Уровни:**

| Уровень | Скрипты | Описание |
|---|---|---|
| `minimal` | 1 | Только webdriver detection |
| `standard` | 6 | + chrome runtime, permissions, plugins, webdriver |
| `advanced` | 16 | + canvas, webgl, audio, screen, hardware, client hints |
| `full` | 16+ | advanced + случайный User-Agent |

**Поля:**

| Поле | Тип | Описание |
|---|---|---|
| `enabled` | `bool` | Включён ли антидетект |
| `scripts` | `list[str]` | Список JS-скриптов для инъекции |
| `level` | `str` | Уровень: minimal/standard/advanced/full |

---

### ScreenshotMaker

```python
from lab_playwright_kit.screenshot import ScreenshotMaker
```

Создание скриншотов и визуальное сравнение.

```python
maker = ScreenshotMaker("/tmp/screenshots")

# Типы скриншотов
path = await maker.viewport(page, prefix="example")
path = await maker.full_page(page, prefix="example")
path = await maker.element(page, selector="h1", prefix="example")
path = await maker.pdf(page, prefix="example")

# Визуальное сравнение
match, diff_ratio, diff_path = await maker.compare(
    page, "baseline.png", threshold=0.15
)
```

**Методы:**

| Метод | Возвращает | Описание |
|---|---|---|
| `viewport(page, prefix="")` | `str` | Скриншот видимой области |
| `full_page(page, prefix="")` | `str` | Скриншот всей страницы |
| `element(page, selector, prefix="")` | `str` | Скриншот элемента |
| `pdf(page, prefix="")` | `str` | PDF страницы |
| `compare(page, baseline, threshold=0.15)` | `tuple[bool, float, str]` | Визуальное сравнение |

---

### PageParser

```python
from lab_playwright_kit.parser import PageParser
```

Парсинг контента страницы.

```python
parser = PageParser(page)
content = await parser.parse()

print(content.title)      # Заголовок
print(content.text)       # Текст
print(content.links)      # Ссылки
print(content.headings)   # Заголовки h1-h6
print(content.images)     # Изображения
print(content.meta)       # Мета-теги

# По селектору
headings = await parser.extract_by_selector("h1, h2, h3")

# Структурированное извлечение
data = await parser.extract_structured({
    "title": "page title",
    "headings": "list:h1, h2, h3",
    "links": "list:a[href]",
})

# Прокрутка до конца
scrolls = await parser.scroll_to_bottom()
```

**Методы:**

| Метод | Возвращает | Описание |
|---|---|---|
| `parse()` | `PageContent` | Полный парсинг страницы |
| `extract_by_selector(selector)` | `list[str]` | Извлечение по CSS-селектору |
| `extract_structured(schema)` | `dict` | Структурированное извлечение |
| `scroll_to_bottom()` | `int` | Прокрутка до конца, кол-во скроллов |

**PageContent:**

| Поле | Тип | Описание |
|---|---|---|
| `title` | `str` | Заголовок страницы |
| `text` | `str` | Текстовый контент |
| `links` | `list[dict]` | Ссылки с URL и текстом |
| `headings` | `list[dict]` | Заголовки с уровнем и текстом |
| `images` | `list[dict]` | Изображения с src и alt |
| `meta` | `dict` | Мета-теги |

---

### NetworkInterceptor

```python
from lab_playwright_kit.network import NetworkInterceptor
```

Перехват и анализ сетевых запросов.

```python
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

**Методы:**

| Метод | Описание |
|---|---|
| `attach()` | Начать перехват |
| `detach()` | Остановить перехват |
| `log.get_api_calls()` | Получить API-вызовы |
| `log.filter_by_status(code)` | Фильтр по статусу |
| `log.filter_by_type(type)` | Фильтр по типу ресурса |
| `log.filter_by_domain(domain)` | Фильтр по домену |

---

### ScreencastRecorder

```python
from lab_playwright_kit.screencast import ScreencastRecorder
```

Запись видео с аннотациями.

```python
async with ScreencastRecorder(page, "/tmp/cast.webm") as rec:
    await page.click("button")
    await rec.annotate(rec.frame_count, "Clicked button")
    await page.fill("#input", "text")
    await rec.annotate(rec.frame_count, "Filled input")
```

**Методы:**

| Метод | Описание |
|---|---|
| `annotate(frame, text)` | Добавить аннотацию к кадру |

---

### ARIASnapshot

```python
from lab_playwright_kit.aria_snapshot import ARIASnapshot
```

Accessibility tree snapshot и diff.

```python
# Получить snapshot
snapshot = await ARIASnapshot.capture(page)
snapshot = await ARIASnapshot.capture(page, selector="#main")

# Сравнить два snapshot
diff = ARIASnapshot.compare(before, after)
print(diff.has_changes)  # bool
print(diff.added)        # добавленные элементы
print(diff.removed)      # удалённые элементы
print(diff.changed)      # изменённые элементы
print(diff.summary)      # текстовая сводка
```

**Методы:**

| Метод | Возвращает | Описание |
|---|---|---|
| `capture(page, selector=None)` | `str` | ARIA snapshot страницы |
| `compare(before, after)` | `ARIADiff` | Сравнение двух snapshot |

---

### ClockController

```python
from lab_playwright_kit.clock import ClockController
```

Манипуляция временем в браузере.

```python
ctrl = ClockController()

# Заморозить время
await ctrl.freeze(page, 1704067200000)

# Продвинуть на 5 секунд
await ctrl.advance(page, 5000)

# Быстрая перемотка
await ctrl.fast_forward(page, 10000)

# Фиксированное время
await ctrl.set_fixed(page, 1704067200000)

# Сброс
await ctrl.reset(page)
```

**Методы:**

| Метод | Описание |
|---|---|
| `freeze(page, timestamp)` | Заморозить время |
| `advance(page, ms)` | Продвинуть время |
| `fast_forward(page, ms)` | Быстрая перемотка |
| `set_fixed(page, timestamp)` | Фиксированное время |
| `reset(page)` | Сбросить к реальному времени |

---

## Антидетект

### WebRTCProtector / WebRTCConfig

```python
from lab_playwright_kit.stealth_webrtc import WebRTCConfig, apply_webrtc_protection
```

Защита от утечки реального IP через WebRTC.

```python
config = WebRTCConfig(
    mode="block_all",  # block_all, filter_host, fake_ice
)
await apply_webrtc_protection(page, config)
```

**Режимы:**

| Режим | Описание |
|---|---|
| `block_all` | Полная блокировка WebRTC |
| `filter_host` | Фильтрация только host-кандидатов |
| `fake_ice` | Подмена ICE-кандидатов на фейковые |

---

### AudioSpoofer / AudioConfig

```python
from lab_playwright_kit.stealth_audio import AudioConfig, apply_audio_spoofing
```

Подмена AudioContext fingerprint.

```python
config = AudioConfig.full(noise_seed=42)
await apply_audio_spoofing(page, config)
```

**Параметры AudioConfig:**

| Параметр | Тип | Описание |
|---|---|---|
| `noise_seed` | `int` | Seed для генерации уникального шума |
| `enabled` | `bool` | Включён ли спуфинг |

---

### ClientHintsSpoofer / ClientHintsConfig

```python
from lab_playwright_kit.stealth_client_hints import ClientHintsConfig, apply_client_hints
```

Подмена User-Agent Client Hints (Sec-CH-UA-*).

```python
config = ClientHintsConfig(
    brand_version='"Chromium";v="131", "Google Chrome";v="131"',
    platform="Windows",
    platform_version="15.0.0",
)
await apply_client_hints(page, config)
```

**Параметры ClientHintsConfig:**

| Параметр | Тип | Описание |
|---|---|---|
| `brand_version` | `str` | Sec-CH-UA заголовок |
| `platform` | `str` | Sec-CH-UA-Platform |
| `platform_version` | `str` | Sec-CH-UA-Platform-Version |
| `mobile` | `bool` | Sec-CH-UA-Mobile |
| `architecture` | `str` | Sec-CH-UA-Arch |

---

## v2.0 Модули

### FingerprintManager / BrowserFingerprint

```python
from lab_playwright_kit.fingerprint import FingerprintManager, BrowserFingerprint
```

Генерация и применение детерминированных отпечатков браузера.

```python
# Генерация
fp = FingerprintManager.generate(
    profile_name="chrome_win_001",
    os="windows",
    browser="chrome",
)

# Применение к странице
await FingerprintManager.apply(page, fp)

# Сериализация
data = fp.to_dict()
fp_restored = BrowserFingerprint.from_dict(data)

# Информация
print(fp.summary)
print(fp.canvas_noise_hex)
print(fp.audio_noise_hex)
```

**FingerprintManager.generate():**

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `profile_name` | `str` | `""` | Имя профиля (seed) |
| `os` | `str` | `"windows"` | ОС: windows/macos/linux/android |
| `browser` | `str` | `"chrome"` | Браузер: chrome/firefox/edge/safari |
| `seed` | `int` | `None` | Явный seed |

**BrowserFingerprint поля:**

| Поле | Тип | Описание |
|---|---|---|
| `profile_id` | `str` | Идентификатор профиля |
| `user_agent` | `str` | User-Agent |
| `webgl_vendor` | `str` | WebGL vendor |
| `webgl_renderer` | `str` | WebGL renderer |
| `canvas_noise_seed` | `int` | Seed для canvas шума |
| `audio_noise_seed` | `int` | Seed для audio шума |
| `screen_width` | `int` | Ширина экрана |
| `screen_height` | `int` | Высота экрана |
| `hardware_cores` | `int` | Количество ядер |
| `hardware_memory` | `int` | Объём RAM (GB) |
| `hardware_platform` | `str` | Платформа |
| `fonts` | `list[str]` | Список шрифтов |
| `os` | `str` | ОС |
| `timezone` | `str` | Таймзона |
| `locale` | `str` | Локаль |
| `languages` | `list[str]` | Языки |

**Методы:**

| Метод | Возвращает | Описание |
|---|---|---|
| `to_dict()` | `dict` | Сериализация |
| `from_dict(data)` | `BrowserFingerprint` | Десериализация |
| `summary` | `str` | Краткое описание |
| `canvas_noise_hex` | `str` | Hex шума canvas |
| `audio_noise_hex` | `str` | Hex шума audio |

---

### HumanBehaviorEngine / BehaviorProfile

```python
from lab_playwright_kit.human_behavior import HumanBehaviorEngine, BehaviorProfile
```

Имитация человечного поведения: мышь, скролл, набор текста.

```python
# Создание с профилем
engine = HumanBehaviorEngine(page, profile="casual_reader", seed=42)

# Движение мыши (кривая Безье)
await engine.move_mouse_to(500, 300)

# Клик с человечным поведением
await engine.click(locator=page.locator("button"))

# Скролл
await engine.scroll_down(pages=2)
await engine.scroll_up(pages=0.5)

# Набор текста
await engine.type_like_human("Hello world", locator=page.locator("#input"))

# Прокрутка к элементу
await engine.scroll_to_element(locator=page.locator("#target"))

# Пауза между действиями
await engine.wait_between_actions()
```

**Профили поведения:**

| Профиль | Описание | Скорость мыши | Скорость набора |
|---|---|---|---|
| `casual_reader` | Медленный читатель | 800-2000ms | 120 WPM |
| `power_user` | Опытный пользователь | 300-800ms | 200 WPM |
| `researcher` | Исследователь | 500-1500ms | 150 WPM |
| `social_media` | Соцсети | 400-1200ms | 180 WPM |

**BehaviorProfile поля:**

| Поле | Тип | Описание |
|---|---|---|
| `name` | `str` | Имя профиля |
| `mouse_move_min_ms` | `int` | Мин. время движения мыши |
| `mouse_move_max_ms` | `int` | Макс. время движения мыши |
| `scroll_speed_px` | `tuple[int, int]` | Диапазон скорости скролла |
| `scroll_pause_chance` | `float` | Вероятность паузы при скролле |
| `typing_speed_wpm` | `int` | Скорость набора (слов/мин) |
| `typing_error_chance` | `float` | Вероятность ошибки при наборе |

---

### AccountManager

```python
from lab_playwright_kit.account_manager import AccountManager, AccountStatus
```

Управление жизненным циклом аккаунтов с SQLite + Fernet шифрование.

```python
am = AccountManager(
    db_path="/tmp/accounts.db",
    encryption_key="my-secret-key",
)

# Создание аккаунта
account = am.create_account(
    platform="twitter",
    username="tester_001",
    email="tester@test.lab",
    password="Secret123!",
    proxy_url="socks5://127.0.0.1:9050",
    profile_id="fp_twitter_001",
    daily_limit=50,
    tags="ghost_protocol,v2,test",
    metadata={"test_run": True},
)

# Получение пароля (дешифрация)
password = am.get_password(account)

# Обновление статуса
am.update_status(account.id, AccountStatus.ACTIVE)

# Запись действия
am.record_action(account.id, "like", "https://twitter.com/post/1")

# Установка кулдауна
am.set_cooldown(account.id, hours=2)

# Получение доступных аккаунтов
available = am.get_available_accounts(platform="twitter")

# Статистика
stats = am.get_stats(platform="twitter")

# История действий
history = am.get_action_history(account.id)

am.close()
```

**AccountStatus:**

| Статус | Описание |
|---|---|
| `CREATED` | Создан |
| `WARMUP` | Разогрев |
| `ACTIVE` | Активен |
| `COOLDOWN` | Кулдаун |
| `BANNED` | Забанен |
| `DEAD` | Мёртв |

**Методы AccountManager:**

| Метод | Возвращает | Описание |
|---|---|---|
| `create_account(...)` | `Account` | Создать аккаунт |
| `get_account(id)` | `Account` | Получить по ID |
| `update_status(id, status, reason="")` | `None` | Обновить статус |
| `get_password(account)` | `str` | Получить пароль |
| `record_action(id, action, target)` | `None` | Записать действие |
| `set_cooldown(id, hours)` | `None` | Установить кулдаун |
| `get_available_accounts(platform)` | `list[Account]` | Доступные аккаунты |
| `get_stats(platform)` | `dict` | Статистика |
| `get_action_history(id)` | `list[dict]` | История действий |
| `close()` | `None` | Закрыть соединение |

---

### ActionEngine / ActionStep / ActionType

```python
from lab_playwright_kit.action_engine import ActionEngine, ActionStep, ActionType, ActionResult
```

Цепочки действий с человечным поведением.

```python
engine = ActionEngine(page, profile="casual_reader")

# Определение цепочки
chain = [
    ActionStep(action_type=ActionType.NAVIGATE, params={"url": "https://example.com"}),
    ActionStep(action_type=ActionType.WAIT, params={"selector": "body"}),
    ActionStep(action_type=ActionType.LIKE, params={"selector": ".like-btn"}),
    ActionStep(action_type=ActionType.SCROLL, params={"pages": 2}),
    ActionStep(action_type=ActionType.COMMENT, params={
        "selector": ".comment-input",
        "text": "Great post!"
    }),
]

# Выполнение цепочки
results = await engine.execute_chain(chain)

# Статистика
print(engine.success_count)
print(engine.fail_count)
```

**ActionType:**

| Тип | Описание |
|---|---|
| `NAVIGATE` | Навигация на URL |
| `CLICK` | Клик по элементу |
| `TYPE` | Ввод текста |
| `SCROLL` | Прокрутка |
| `LIKE` | Лайк |
| `COMMENT` | Комментарий |
| `FOLLOW` | Подписка |
| `REPOST` | Репост |
| `WAIT` | Ожидание |
| `SCREENSHOT` | Скриншот |

**ActionStep поля:**

| Поле | Тип | Описание |
|---|---|---|
| `action_type` | `ActionType` | Тип действия |
| `params` | `dict` | Параметры |
| `on_fail` | `str` | Действие при ошибке: retry/skip/abort |
| `max_retries` | `int` | Макс. попытки |

---

### TaskOrchestrator / Task / TaskPriority

```python
from lab_playwright_kit.task_orchestrator import TaskOrchestrator, Task, TaskPriority, TaskStatus, RateLimit
```

Оркестрация задач с приоритетами и rate limiting.

```python
orch = TaskOrchestrator(workers=3)

# Добавление задач
orch.add_task(Task(
    id="task_1",
    platform="twitter",
    action="like",
    target="https://twitter.com/post/1",
    priority=TaskPriority.CRITICAL,
))

orch.add_task(Task(
    id="task_2",
    platform="telegram",
    action="comment",
    target="https://t.me/channel/1",
    priority=TaskPriority.NORMAL,
))

# Получение следующей задачи
task = orch.get_next()

# Обновление статуса
orch.update_status("task_1", TaskStatus.COMPLETED)

# Статистика
stats = orch.get_stats()
```

**TaskPriority:**

| Приоритет | Значение | Описание |
|---|---|---|
| `CRITICAL` | 0 | Критический |
| `HIGH` | 1 | Высокий |
| `NORMAL` | 2 | Нормальный |
| `LOW` | 3 | Низкий |
| `BACKGROUND` | 4 | Фоновый |

**TaskStatus:**

| Статус | Описание |
|---|---|
| `PENDING` | Ожидает |
| `RUNNING` | Выполняется |
| `COMPLETED` | Завершена |
| `FAILED` | Ошибка |
| `CANCELLED` | Отменена |

**RateLimit:**

```python
limit = RateLimit(
    platform="twitter",
    max_per_minute=30,
    cooldown_seconds=2.0,
)

if limit.can_execute():
    limit.record_action()
else:
    wait = limit.wait_time
```

---

### ProxyRotator

```python
from lab_playwright_kit.proxy_rotation import ProxyRotator
```

Ротация прокси.

```python
rotator = ProxyRotator(strategy="round_robin")  # round_robin, random, weighted

# Добавление прокси
rotator.add_proxy("socks5://user:pass@host:1080")
rotator.add_proxy("http://user:pass@host:8080")

# Получение следующего
proxy = rotator.get_next()

# Обратная связь
rotator.mark_success(proxy)
rotator.mark_failed(proxy)

# Статистика
stats = rotator.get_stats()
```

**Методы:**

| Метод | Возвращает | Описание |
|---|---|---|
| `add_proxy(url)` | `None` | Добавить прокси |
| `get_next()` | `Proxy` | Получить следующий |
| `mark_success(proxy)` | `None` | Пометить как успешный |
| `mark_failed(proxy)` | `None` | Пометить как неуспешный |
| `get_stats()` | `dict` | Статистика |

---

### SessionManager

```python
from lab_playwright_kit.session_manager import SessionManager
```

Управление сессиями с Fernet шифрованием.

```python
sm = SessionManager(encryption_key="my-key")

# Сохранение сессии
sm.save_session("twitter", session_data)

# Загрузка
session = sm.load_session("twitter")

# Проверка валидности
if sm.is_session_valid("twitter"):
    ...

sm.close()
```

---

### HARRecorder

```python
from lab_playwright_kit.har_recorder import HARRecorder
```

HAR-запись сетевого трафика.

```python
recorder = HARRecorder(page)
await recorder.start()

await page.goto("https://example.com")

await recorder.stop()
har_data = recorder.get_har()
```

---

### LLMParser / LLMConfig

```python
from lab_playwright_kit.llm_parse import LLMParser, LLMConfig
```

LLM-парсинг страниц.

```python
config = LLMConfig(
    api_key="sk-...",
    model="google/gemini-2.5-flash",
    api_url="https://openrouter.ai/api/v1/chat/completions",
    timeout=30,
)

parser = LLMParser(config)

# Извлечение данных
data = await parser.extract(
    page,
    query="Extract article title, author, and date",
    schema={
        "title": "article title",
        "author": "author name",
        "date": "publication date",
    },
)
```

**LLMConfig поля:**

| Поле | Тип | По умолчанию | Описание |
|---|---|---|---|
| `api_key` | `str` | `""` | API-ключ |
| `model` | `str` | `"google/gemini-2.5-flash"` | Модель |
| `api_url` | `str` | OpenRouter URL | URL API |
| `timeout` | `int` | `30` | Таймаут (сек) |

---

### CaptchaSolver

```python
from lab_playwright_kit.captcha_solver import CaptchaSolver
```

Обнаружение и решение капчи.

```python
solver = CaptchaSolver(
    api_key="2captcha-key",
    service="2captcha",  # 2captcha, anticaptcha
)

# Обнаружение
if await solver.detect(page):
    # Решение
    result = await solver.solve_recaptcha(
        page,
        site_key="6Ld...",
        url=page.url,
    )
```

---

### StealthBenchmark

```python
from lab_playwright_kit.stealth_benchmark import StealthBenchmark
```

Автоматический бенчмарк stealth-защиты.

```python
bench = StealthBenchmark()
report = await bench.run(page)

print(report.score)        # 0-100
print(report.tests_run)    # кол-во тестов
print(report.tests_passed) # пройдено
print(report.details)      # детали
```

---

*Документация актуальна для v2.0. Последнее обновление: 2026-05-18*
