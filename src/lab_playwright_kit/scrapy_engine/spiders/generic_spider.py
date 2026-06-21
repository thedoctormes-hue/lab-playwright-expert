"""
GenericSpider — универсальный Scrapy паук с декларативными схемами.

Использует FieldMapping из data_parser для извлечения данных.
Поддерживает:
- Обход по ссылкам (с ограничениями по домену/глубине)
- Извлечение данных по CSS/XPath схеме
- Экспорт в JSON/CSV/SQLite

Использование:
    scrapy crawl generic \
        -a url="https://example.com" \
        -a schema=ecommerce \
        -a max_pages=50
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

import scrapy

from ..items import ScrapedPage


class GenericSpider(scrapy.Spider):
    """Универсальный паук: обход + извлечение данных по схеме."""

    name = "generic"

    # Scrapy settings для этого паука
    custom_settings = {
        "ROBOTSTXT_OBEY": True,
        "DOWNLOAD_DELAY": 1.5,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
        "DEPTH_LIMIT": 3,
        "FEEDS": {
            "./crawl_output/%(name)s_%(time)s.json": {
                "format": "json",
                "encoding": "utf-8",
                "ensure_ascii": False,
            }
        },
    }

    def __init__(
        self,
        url: str | None = None,
        schema: str = "generic",
        max_pages: int = 50,
        max_depth: int = 3,
        allowed_domains: str = "",
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.start_urls = [url] if url else []
        self.schema_name = schema
        self.max_pages = int(max_pages)
        self.max_depth = int(max_depth)

        # Ограничение по доменам
        if allowed_domains:
            self.allowed_domains = [d.strip() for d in allowed_domains.split(",")]
        elif url:
            parsed = urlparse(url)
            self.allowed_domains = [parsed.netloc]

        self._pages_count = 0

    def parse(self, response):
        """Парсинг страницы: извлечь данные + найти ссылки."""

        if self._pages_count >= self.max_pages:
            return

        self._pages_count += 1

        # Извлечь данные
        page_item = ScrapedPage(
            url=response.url,
            domain=urlparse(response.url).netloc,
            spider_name=self.name,
            title=response.css("title::text").get(""),
            text=" ".join(response.css("body ::text").getall()).strip()[:5000],
            meta=self._extract_meta(response),
            links=self._extract_links(response),
            images=response.css("img::attr(src)").getall(),
            status_code=response.status,
            crawl_time=datetime.now(timezone.utc).isoformat(),
            depth=response.meta.get("depth", 0),
            referer=response.meta.get("referer", ""),
        )

        yield page_item

        # Следующие ссылки (ограничение по глубине)
        current_depth = response.meta.get("depth", 0)
        if current_depth < self.max_depth:
            for href in response.css("a::attr(href)").getall():
                yield response.follow(
                    href,
                    callback=self.parse,
                    meta={
                        "depth": current_depth + 1,
                        "referer": response.url,
                    },
                )

    def _extract_meta(self, response) -> dict:
        """Извлечь мета-теги."""
        meta = {}
        for sel in response.css("meta[name], meta[property]"):
            key = sel.attrib.get("name") or sel.attrib.get("property")
            val = sel.attrib.get("content", "")
            if key and val:
                meta[key] = val
        return meta

    def _extract_links(self, response) -> list[dict]:
        """Извлечь ссылки."""
        links = []
        for a in response.css("a[href]"):
            text = a.css("::text").get("").strip()
            href = a.attrib["href"]
            if text and href:
                links.append({"text": text, "href": href})
        return links[:100]  # limit
