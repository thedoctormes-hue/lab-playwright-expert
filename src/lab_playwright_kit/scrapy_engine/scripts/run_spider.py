#!/usr/bin/env python3
"""
CLI для запуска Scrapy пауков.

Использование:
    # Универсальный паук:
    python -m lab_playwright_kit.scrapy_engine.scripts.run_spider generic \\
        --url https://example.com --max-pages 10 --output ./output

    # Авто с Авито:
    python -m lab_playwright_kit.scrapy_engine.scripts.run_spider avito_dealer \\
        --url "https://www.avito.ru/moskva/avtomobili" --max-pages 5

    # Госзакупки:
    python -m lab_playwright_kit.scrapy_engine.scripts.run_spider zakupki \\
        --query "строительство" --max-pages 10

    # Автозапчасти (все магазины):
    python -m lab_playwright_kit.scrapy_engine.scripts.run_spider auto_parts \\
        --article OC244

    # Автозапчасти (конкретные магазины):
    python -m lab_playwright_kit.scrapy_engine.scripts.run_spider auto_parts \\
        --article OC244 --shops exist,emex,fobil

    # Список пауков:
    python -m lab_playwright_kit.scrapy_engine.scripts.run_spider --list
"""

from __future__ import annotations

# CRITICAL: install asyncio reactor BEFORE any Twisted/scrapy import
from twisted.internet import asyncioreactor


asyncioreactor.install()

import argparse
import sys

from scrapy.crawler import CrawlerProcess

from lab_playwright_kit.scrapy_engine.settings import get_settings


# Регистрация пауков
SPIDERS = {
    "generic": {
        "class": "lab_playwright_kit.scrapy_engine.spiders.generic_spider:GenericSpider",
        "args": ["url", "schema", "max_pages", "max_depth"],
        "defaults": {"schema": "generic", "max_pages": 50, "max_depth": 3},
        "description": "Универсальный паук (CSS/XPath схемы)",
    },
    "avito_dealer": {
        "class": "lab_playwright_kit.scrapy_engine.spiders.avito_dealer_spider:AvitoDealerSpider",
        "args": ["url", "brand", "max_pages"],
        "defaults": {"max_pages": 10},
        "description": "Парсинг дилерских авто с Avito",
    },
    "zakupki": {
        "class": "lab_playwright_kit.scrapy_engine.spiders.zakupki_spider:ZakupkiSpider",
        "args": ["query", "max_pages", "price_from", "price_to"],
        "defaults": {"max_pages": 10},
        "description": "Парсировка госзакупок (44-ФЗ, 223-ФЗ)",
    },
    "auto_parts": {
        "class": "lab_playwright_kit.scrapy_engine.spiders.auto_parts.part_spider:PlaywrightPartSpider",
        "args": ["article", "shops"],
        "defaults": {},
        "description": "Цены на автозапчасти (emex, exist, apex, fobil, autoeuro, mymajor, autodoc)",
    },
}


def import_class(path: str):
    """Динамический импорт класса по строке 'module.path:ClassName'."""
    module_path, class_name = path.rsplit(":", 1)
    import importlib

    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


def run_spider(spider_name: str, spider_args: dict, output_dir: str = "./crawl_output"):
    """Запустить паука с аргументами."""
    if spider_name not in SPIDERS:
        print(f"❌ Неизвестный паук: {spider_name}")
        print(f"   Доступные: {', '.join(SPIDERS)}")
        sys.exit(1)

    config = SPIDERS[spider_name]
    spider_cls = import_class(config["class"])

    # Настройки Scrapy
    settings = get_settings()
    settings["FEEDS"] = {
        f"{output_dir}/{spider_name}_%(time)s.json": {
            "format": "json",
            "encoding": "utf-8",
            "ensure_ascii": False,
        }
    }
    settings["LOG_LEVEL"] = "INFO"

    # Дефолтные аргументы
    args = dict(config["defaults"])
    args.update(spider_args)

    # Запуск
    process = CrawlerProcess(settings=settings)
    process.crawl(spider_cls, **args)

    print(f"🕷️ Запуск паука: {spider_name}")
    print(f"   Аргументы: {args}")
    print(f"   Выход: {output_dir}/")
    print("─" * 50)

    try:
        process.start()
    except SystemExit:
        pass

    print("─" * 50)
    print(f"✅ Паук {spider_name} завершил работу")


def list_spiders():
    """Вывести список доступных пауков."""
    print("🕷️ Доступные пауки:")
    print()
    for name, config in SPIDERS.items():
        print(f"  {name:20s} — {config['description']}")
        print(f"  {'':20s}   Аргументы: {', '.join(config['args'])}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="CLI для Scrapy пауков Lab Playwright Kit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "spider",
        nargs="?",
        help="Имя паука (generic, avito_dealer, zakupki, auto_parts)",
    )
    parser.add_argument("--list", action="store_true", help="Список пауков")
    parser.add_argument("--output", default="./crawl_output", help="Директория выхода")
    parser.add_argument("--url", help="URL для парсинга")
    parser.add_argument("--query", help="Поисковый запрос")
    parser.add_argument("--article", help="Артикул запчасти (для auto_parts)")
    parser.add_argument("--shops", help="Магазины через запятую (для auto_parts)")
    parser.add_argument("--schema", default="generic", help="Схема для GenericSpider")
    parser.add_argument("--brand", help="Бренд авто")
    parser.add_argument("--max-pages", type=int, help="Макс. страниц")
    parser.add_argument("--max-depth", type=int, help="Макс. глубина")
    parser.add_argument("--price-from", help="Мин. цена")
    parser.add_argument("--price-to", help="Макс. цена")

    args = parser.parse_args()

    if args.list or not args.spider:
        list_spiders()
        return

    # Собрать аргументы для паука
    spider_args = {}
    for key in ["url", "query", "article", "shops", "schema", "brand"]:
        val = getattr(args, key)
        if val:
            spider_args[key] = val
    if args.max_pages:
        spider_args["max_pages"] = args.max_pages
    if args.max_depth:
        spider_args["max_depth"] = args.max_depth
    if args.price_from:
        spider_args["price_from"] = args.price_from
    if args.price_to:
        spider_args["price_to"] = args.price_to

    run_spider(args.spider, spider_args, args.output)


if __name__ == "__main__":
    main()
