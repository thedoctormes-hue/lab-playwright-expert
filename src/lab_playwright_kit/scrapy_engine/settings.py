# Scrapy Settings Module — активируется через SCRAPY_SETTINGS_MODULE
# scrapy_playwright использует entry points, settings должен быть реальным модулем

BOT_NAME = "lab_playwright_kit"
SPIDER_MODULES = ["lab_playwright_kit.scrapy_engine.spiders"]
NEWSPIDER_MODULE = "lab_playwright_kit.scrapy_engine.spiders"
ROBOTSTXT_OBEY = True
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Скорость
DOWNLOAD_DELAY = 1.5
RANDOMIZE_DOWNLOAD_DELAY = True
CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 4
DEPTH_LIMIT = 3

# НЕ указываем DOWNLOAD_HANDLERS явно — scrapy_playwright сам
# перехватывает запросы при наличии PLAYWRIGHT_BROWSER_TYPE.
# Явное указание ломает CrawlerRunner (известный баг scrapy-playwright 0.0.46).
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    "args": [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
    ],
}
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30_000

# Middlewares
DOWNLOADER_MIDDLEWARES = {
    "lab_playwright_kit.scrapy_engine.middlewares.StealthMiddleware": 400,
    "lab_playwright_kit.scrapy_engine.middlewares.ProxyMiddleware": 350,
}

# Pipelines
ITEM_PIPELINES = {
    "lab_playwright_kit.scrapy_engine.pipelines.ValidationPipeline": 100,
    "lab_playwright_kit.scrapy_engine.pipelines.DedupPipeline": 200,
    "lab_playwright_kit.scrapy_engine.pipelines.ExportPipeline": 300,
}

# Экспорт
FEEDS = {
    "./crawl_output/%(name)s_%(time)s.json": {
        "format": "json",
        "encoding": "utf-8",
        "ensure_ascii": False,
        "overwrite": False,
    }
}

LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]

HTTPCACHE_ENABLED = False
HTTPCACHE_EXPIRATION_SECS = 3600
HTTPCACHE_DIR = "./.scrapy_cache"


def get_settings(overrides: dict | None = None) -> dict:
    """Базовые настройки Scrapy с интеграцией Playwright."""
    import scrapy.settings

    settings = scrapy.settings.BaseSettings(globals(), priority="default")
    if overrides:
        settings.update(overrides, priority="cmdline")
    return settings
