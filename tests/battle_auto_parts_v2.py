#!/usr/bin/env python3
"""Перебойный тест запуска Playwright через scrapy-playwright напрямую."""

import json
from datetime import datetime
from pathlib import Path

from loguru import logger
from scrapy.crawler import CrawlerRunner
from twisted.internet import reactor

from lab_playwright_kit.scrapy_engine.settings import get_settings
from lab_playwright_kit.scrapy_engine.spiders.auto_parts.part_spider import PlaywrightPartSpider


class CollectorPipeline:
    def __init__(self):
        self.items = []

    def process_item(self, item, spider):
        self.items.append(dict(item))
        spider.logger.info(
            f"[COLLECTOR] {item.get('shop_name')}: {item.get('name','?')[:40]} — {item.get('price',0)} ₽"
        )
        return item


def run(article: str, shops: str = ""):
    items_collected = []

    def _collect(item, response, spider):
        items_collected.append(dict(item))

    settings = get_settings()
    settings.update(
        {
            "LOG_LEVEL": "DEBUG",
            "ITEM_PIPELINES": {
                "__main__.CollectorPipeline": 100,
            },
            "FEEDS": {},
        }
    )

    runner = CrawlerRunner(settings=settings)

    shop_list = [s.strip() for s in shops.split(",") if s.strip()] if shops else []
    kwargs = {"article": article}
    if shop_list:
        kwargs["shops"] = shops

    logger.info(f"Запуск: article={article}, shops={shop_list or 'all'}")

    d = runner.crawl(PlaywrightPartSpider, **kwargs)

    def on_finished(_):
        logger.info(f"Готово. Items: {len(items_collected)}")
        for item in items_collected[:5]:
            logger.info(
                f"  • {item.get('shop_name')}: {item.get('name','?')[:40]} — {item.get('price',0)} ₽"
            )

        # Сохранить
        output_dir = Path("./crawl_output")
        output_dir.mkdir(exist_ok=True)
        report_path = (
            output_dir / f"battle_{article}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        report_path.write_text(
            json.dumps(
                {
                    "article": article,
                    "total": len(items_collected),
                    "items": items_collected,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        logger.info(f"Отчёт: {report_path}")
        reactor.stop()

    def on_error(failure):
        logger.error(f"Ошибка: {failure}")
        reactor.stop()

    d.addCallback(on_finished)
    d.addErrback(on_error)

    reactor.run()


if __name__ == "__main__":
    import sys

    article = sys.argv[1] if len(sys.argv) > 1 else "OC244"
    shops = sys.argv[2] if len(sys.argv) > 2 else "exist"
    run(article, shops)
