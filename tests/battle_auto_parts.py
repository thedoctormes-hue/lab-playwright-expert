#!/usr/bin/env python3
"""Боевой прогон PlaywrightPartSpider через CrawlerRunner."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import scrapy
from loguru import logger
from scrapy.crawler import CrawlerRunner

from lab_playwright_kit.scrapy_engine.settings import get_settings
from lab_playwright_kit.scrapy_engine.spiders.auto_parts.part_spider import PlaywrightPartSpider


class CollectorPipeline:
    def __init__(self):
        self.items: list[dict] = []

    def process_item(self, item, spider):
        d = dict(item)
        self.items.append(d)
        spider.logger.info(
            f"[COLLECTOR] {d.get('shop_name','?')}: "
            f"{d.get('name','?')[:50]} "
            f"— {d.get('price',0)} ₽"
        )
        return item


def run(article: str, shops: str = ""):
    settings = get_settings()
    settings.update(
        {
            "LOG_LEVEL": "INFO",
            "ITEM_PIPELINES": {
                "__main__.CollectorPipeline": 100,
            },
            "FEEDS": {},
            "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        }
    )

    runner = CrawlerRunner(settings)

    kwargs: dict = {"article": article}
    if shops:
        kwargs["shops"] = shops

    logger.info(f"=== BATTLE: article={article}, shops={shops or 'all'} ===")

    collector = CollectorPipeline()
    crawler = None

    def _on_item(item, response, spider):
        collector.items.append(dict(item))

    def _on_spider_opened(spider):
        nonlocal crawler
        crawler = spider.crawler
        crawler.signals.connect(_on_item, signal=scrapy.signals.item_scraped)

    from twisted.internet import reactor

    d = runner.crawl(PlaywrightPartSpider, **kwargs)
    d.addCallback(lambda _: _on_spider_opened(runner.spider))

    def _done(_):
        reactor.callLater(0, reactor.stop)

    d.addBoth(_done)
    reactor.run()

    # Report
    print(f"\n{'='*60}")
    print(f"Дата:    {datetime.now().isoformat()}")
    print(f"Артикул: {article}")
    print(f"Магазины: {shops or 'all'}")
    print(f"Items:   {len(collector.items)}")

    by_shop: dict[str, list] = {}
    for item in collector.items:
        shop = item.get("shop_name", "?")
        by_shop.setdefault(shop, []).append(item)

    for shop, items in sorted(by_shop.items()):
        prices = [i["price"] for i in items if i.get("price", 0) > 0]
        stats = ""
        if prices:
            prices_s = sorted(prices)
            mid = prices_s[len(prices_s) // 2]
            stats = f" | {min(prices):.0f}-{max(prices):.0f} ₽ (mid:{mid:.0f})"
        print(f"\n  📍 {shop}: {len(items)} items{stats}")
        for item in items[:5]:
            print(
                f"     • [{item.get('brand',''):12s}] "
                f"{item.get('name','')[:45]:45s} "
                f"{item.get('price',0):>7.0f} ₽"
            )

    # Save
    output_dir = Path("./crawl_output")
    output_dir.mkdir(exist_ok=True)
    report_path = output_dir / f"battle_{article}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.write_text(
        json.dumps(
            {
                "article": article,
                "shops": shops or "all",
                "total": len(collector.items),
                "by_shop": {k: len(v) for k, v in by_shop.items()},
                "items": collector.items,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    print(f"\n💾 {report_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    article = sys.argv[1] if len(sys.argv) > 1 else "OC244"
    shops = sys.argv[2] if len(sys.argv) > 2 else ""
    run(article, shops)
