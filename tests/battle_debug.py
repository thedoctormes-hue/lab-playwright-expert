#!/usr/bin/env python3
"""Боевой прогон — отладочная версия."""

from __future__ import annotations

import logging
import sys

from scrapy.crawler import CrawlerRunner

from lab_playwright_kit.scrapy_engine.settings import get_settings
from lab_playwright_kit.scrapy_engine.spiders.auto_parts.part_spider import PlaywrightPartSpider


# DEBUG для playwright
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("scrapy-playwright").setLevel(logging.DEBUG)
logging.getLogger("scrapy").setLevel(logging.INFO)

settings = get_settings()
settings.update(
    {
        "LOG_LEVEL": "DEBUG",
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    }
)

runner = CrawlerRunner(settings)

items = []


def on_item_scraped(item, response, spider):
    d = dict(item)
    items.append(d)
    print(f"  ✅ ITEM: {d.get('shop_name')}: {d.get('name','?')[:50]} — {d.get('price',0)} ₽")


def on_spider_opened(spider):
    spider.crawler.signals.connect(
        on_item_scraped, signal=__import__("scrapy").signals.item_scraped
    )
    # Подписка на все сигналы
    spider.crawler.signals.connect(
        lambda **kw: print("  SIGNAL: spider_closed"),
        signal=__import__("scrapy").signals.spider_closed,
    )


reactor = __import__("twisted.internet", fromlist=["reactor"]).reactor
d = runner.crawl(
    PlaywrightPartSpider,
    article=sys.argv[1] if len(sys.argv) > 1 else "OC244",
    shops=sys.argv[2] if len(sys.argv) > 2 else "exist",
)
d.addCallback(lambda _: on_spider_opened(runner.spider))
d.addBoth(lambda _: reactor.callLater(0, reactor.stop))
reactor.run()

print(f"\nItems: {len(items)}")
for item in items:
    print(f"  [{item.get('shop_name')}] {item.get('name','?')[:45]} — {item.get('price',0)} ₽")
