"""Scrapy Spiders — пауки для конкретных задач парсинга."""

from .auto_parts.part_spider import PlaywrightPartSpider
from .avito_dealer_spider import AvitoDealerSpider
from .generic_spider import GenericSpider
from .zakupki_spider import ZakupkiSpider


__all__ = [
    "GenericSpider",
    "ZakupkiSpider",
    "AvitoDealerSpider",
    "PlaywrightPartSpider",
]
