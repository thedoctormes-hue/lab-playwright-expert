"""
Scrapy Engine — промышленный веб-краулинг на базе Scrapy.

Интеграция Scrapy + Playwright:
- Scrapy: обход сайтов, пагинация, дедупликация, экспорт
- Playwright (через scrapy-playwright): JS-рендеринг, антидетект
- Pipelines: валидация, дедупликация, экспорт в JSON/CSV/SQLite

Использование:
    # Запуск паука из CLI:
    scrapy crawl generic -a url="https://example.com" -a max_pages=50

    # Запуск из Python:
    from scrapy.crawler import CrawlerProcess
    from lab_playwright_kit.scrapy_engine.spiders import GenericSpider
    from lab_playwright_kit.scrapy_engine.settings import get_settings

    process = CrawlerProcess(settings=get_settings())
    process.crawl(GenericSpider, url="https://example.com")
    process.start()

Автозапчасти:
    scrapy crawl auto_parts -a article="OC244" -a shops="exist,emex,fobil"

    # Или через CLI:
    python -m lab_playwright_kit.scrapy_engine.scripts.run_spider auto_parts \\
        --article OC244 --shops exist,emex,fobil
"""

from .items import (
    ScrapedArticle,
    ScrapedAuto,
    ScrapedContract,
    ScrapedJob,
    ScrapedPage,
    ScrapedPart,
    ScrapedProduct,
    ScrapedRealty,
)
from .middlewares import (
    PlaywrightMiddleware,
    ProxyMiddleware,
    StealthMiddleware,
)
from .pipelines import (
    DedupPipeline,
    ExportPipeline,
    ValidationPipeline,
)
from .settings import get_settings
from .spiders import (
    AvitoDealerSpider,
    GenericSpider,
    PlaywrightPartSpider,
    ZakupkiSpider,
)


__all__ = [
    # Items
    "ScrapedPage",
    "ScrapedProduct",
    "ScrapedArticle",
    "ScrapedJob",
    "ScrapedRealty",
    "ScrapedAuto",
    "ScrapedPart",
    "ScrapedContract",
    # Middlewares
    "StealthMiddleware",
    "PlaywrightMiddleware",
    "ProxyMiddleware",
    # Pipelines
    "ValidationPipeline",
    "ExportPipeline",
    "DedupPipeline",
    # Spiders
    "GenericSpider",
    "ZakupkiSpider",
    "PlaywrightPartSpider",
    # Settings
    "get_settings",
]
