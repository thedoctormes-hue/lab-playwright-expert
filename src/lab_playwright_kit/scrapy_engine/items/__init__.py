"""Scrapy Items — универсальные модели данных для парсинга."""

from .scrapy_items import (
    ScrapedArticle,
    ScrapedAuto,
    ScrapedContract,
    ScrapedJob,
    ScrapedPage,
    ScrapedPart,
    ScrapedProduct,
    ScrapedRealty,
)


__all__ = [
    "ScrapedPage",
    "ScrapedProduct",
    "ScrapedArticle",
    "ScrapedJob",
    "ScrapedRealty",
    "ScrapedAuto",
    "ScrapedPart",
    "ScrapedContract",
]
