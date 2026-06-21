"""
ZakupkiSpider — паук для парсинга госзакупок.

Источники:
- zakupki.gov.ru (44-ФЗ, 223-ФЗ)
- clearing.gov.ru

Использование:
    scrapy crawl zakupki \
        -a query="строительство" \
        -a max_pages=10

Требует FlareSolverr для обхода Cloudflare на zakupki.gov.ru.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode

import scrapy

from ..items import ScrapedContract


class ZakupkiSpider(scrapy.Spider):
    """Парсер госзакупок (44-ФЗ / 223-ФЗ)."""

    name = "zakupki"

    BASE_URL = "https://zakupki.gov.ru/epz/order/extendedsearch/search.html"

    custom_settings = {
        "ROBOTSTXT_OBEY": True,
        "DOWNLOAD_DELAY": 3.0,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "DEPTH_LIMIT": 5,
        "COOKIES_ENABLED": True,
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
        query: str = "",
        max_pages: int = 10,
        price_from: str = "",
        price_to: str = "",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.query = query
        self.max_pages = int(max_pages)
        self.price_from = price_from
        self.price_to = price_to
        self._current_page = 0

    def start_requests(self):
        """Сформировать начальный запрос."""
        params = {"morphology": "on", "searchString": self.query, "pageNumber": "1"}
        if self.price_from:
            params["priceFromGeneral"] = self.price_from
        if self.price_to:
            params["priceToGeneral"] = self.price_to

        url = f"{self.BASE_URL}?{urlencode(params)}"
        yield scrapy.Request(url, callback=self.parse_listing)

    def parse_listing(self, response):
        """Парсинг списка закупок."""
        self._current_page += 1
        if self._current_page > self.max_pages:
            return

        # Извлечь карточки закупок
        for card in response.css(".registerBox .registerBoxBank"):
            item = ScrapedContract(
                url=response.urljoin(card.css("a::attr(href)").get("")),
                domain="zakupki.gov.ru",
                spider_name=self.name,
                title=card.css(".textBox .title::text").get("").strip(),
                text=" ".join(card.css(".textBox ::text").getall()).strip(),
                meta={
                    "reg_number": card.css(".number::text").get(""),
                    "price": card.css(".price::text").get(""),
                    "customer": card.css(".customer::text").get(""),
                    "status": card.css(".status::text").get(""),
                },
                links=[],
                images=[],
                status_code=response.status,
                crawl_time=datetime.now(timezone.utc).isoformat(),
                depth=response.meta.get("depth", 0),
                referer=response.meta.get("referer", ""),
            )
            yield item

        # Пагинация
        next_page = response.css("a.nextPage::attr(href)").get()
        if next_page and self._current_page < self.max_pages:
            yield response.follow(next_page, callback=self.parse_listing)
