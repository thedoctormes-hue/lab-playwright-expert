"""Battle test — полный PlaywrightPartSpider на autodoc.ru."""

import logging
import sys

from twisted.internet import asyncioreactor


asyncioreactor.install()

from scrapy.crawler import CrawlerProcess

from lab_playwright_kit.scrapy_engine.spiders.auto_parts.part_spider import PlaywrightPartSpider


logging.basicConfig(format="%(message)s", stream=sys.stderr, level=logging.INFO)

process = CrawlerProcess(
    dict(
        LOG_LEVEL="WARNING",
        PLAYWRIGHT_BROWSER_TYPE="chromium",
        PLAYWRIGHT_LAUNCH_OPTIONS=dict(headless=True, args=["--no-sandbox"]),
        PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT=15000,
    )
)

# autodoc — url_param магазин
process.crawl(PlaywrightPartSpider, article="OC471", shops="autodoc")
process.start()
print("FINISHED")
