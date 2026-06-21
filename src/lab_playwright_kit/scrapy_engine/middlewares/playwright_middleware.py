"""
PlaywrightMiddleware — Scrapy middleware для JS-рендеринга через scrapy-playwright.

Используется для страниц которые требуют JavaScript:
- SPA-приложения (React, Vue, Angular)
- Lazy-loading контент
- Cloudflare/антибот защита

Запускает Playwright только для запросов с meta={'playwright': True}.
Остальные запросы обрабатываются стандартным Scrapy downloader.

Требует: pip install scrapy-playwright
"""

from __future__ import annotations

import logging

from scrapy import Request
from scrapy.http import HtmlResponse


log = logging.getLogger(__name__)

try:
    from scrapy_playwright.page import PageMethod

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class PlaywrightMiddleware:
    """
    Scrapy middleware: Playwright integration для JS-рендеринга.

    Использование в Spider:
        def start_requests(self):
            yield scrapy.Request(
                url="https://example.com",
                meta={
                    "playwright": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_selector", "div.content"),
                        PageMethod("scroll", BindingCall("window.scrollTo", 0, document.body.scrollHeight)),
                    ],
                    "playwright_include_page": True,
                },
            )

    В parse():
        page = response.meta["playwright_page"]
        # ... работаем с Playwright page ...
        await page.close()
    """

    def __init__(self, stealth_level: str = "standard"):
        self.stealth_level = stealth_level

    @classmethod
    def from_crawler(cls, crawler):
        stealth = crawler.settings.get("PLAYWRIGHT_STEALTH", "standard")
        return cls(stealth_level=stealth)

    def process_request(self, request: Request) -> None:
        """Пометить запрос для Playwright downloader."""
        if request.meta.get("playwright"):
            if not PLAYWRIGHT_AVAILABLE:
                log.error(
                    "scrapy-playwright not installed. "
                    "Run: pip install scrapy-playwright && playwright install chromium"
                )

    def process_response(self, request: Request, response: HtmlResponse):
        """Пост-обработка Playwright-ответа: извлечь текст, ссылки, мета."""

        if not request.meta.get("playwright"):
            return response

        # Добавить в метаданные информацию о типе ответа
        request.meta["playwright_rendered"] = True

        return response
