"""
StealthMiddleware — Scrapy middleware для антидетекта на уровне HTTP.

Добавляет к каждому запросу:
- Реалистичные заголовки (User-Agent, Accept, Accept-Language, Client Hints)
- Случайный порядок заголовков
- Cookie management
- Referer из предыдущего запроса

Не путать с PlaywrightMiddleware — тот работает на уровне DOM (JS-инъекции).
"""

from __future__ import annotations

import random

from scrapy import Request


# ─── Realistic User Agents ───────────────────────────────────────────────────

WINDOWS_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]

LINUX_UAS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
]

ALL_UAS = WINDOWS_UAS + LINUX_UAS

ACCEPT_LANGUAGES = [
    "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "ru-RU,ru;q=0.9,en;q=0.8",
    "en-US,en;q=0.9,ru;q=0.8",
    "en-US,en;q=0.9",
]


class StealthMiddleware:
    """Scrapy middleware: HTTP-level stealth (заголовки, cookies, referer)."""

    def __init__(self):
        self._ua = random.choice(ALL_UAS)

    @classmethod
    def from_crawler(cls, crawler):
        middleware = cls()
        return middleware

    def process_request(self, request: Request) -> None:
        """Подменить заголовки перед отправкой."""

        # User-Agent: случайный из пула (фиксируется при инициализации)
        request.headers.setdefault("User-Agent", self._ua)

        # Accept
        request.headers.setdefault(
            "Accept",
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        )

        # Accept-Language
        request.headers.setdefault("Accept-Language", random.choice(ACCEPT_LANGUAGES))

        # Accept-Encoding
        request.headers.setdefault("Accept-Encoding", "gzip, deflate, br")

        # DNT
        request.headers.setdefault("DNT", "1")

        # Connection
        request.headers.setdefault("Connection", "keep-alive")

        # Upgrade-Insecure-Requests
        request.headers.setdefault("Upgrade-Insecure-Requests", "1")

        # Sec-Fetch-* (Chrome-специфичные)
        if "Chrome" in self._ua:
            request.headers.setdefault("Sec-Fetch-Dest", "document")
            request.headers.setdefault("Sec-Fetch-Mode", "navigate")
            request.headers.setdefault("Sec-Fetch-Site", "none")
            request.headers.setdefault("Sec-Fetch-User", "?1")

            # Client Hints (если Chrome)
            chrome_ver = (
                self._ua.split("Chrome/")[1].split(".")[0] if "Chrome/" in self._ua else "131"
            )
            request.headers.setdefault(
                "Sec-CH-UA",
                f'"Not_A Brand";v="8", "Chromium";v="{chrome_ver}", "Google Chrome";v="{chrome_ver}"',
            )
            request.headers.setdefault("Sec-CH-UA-Mobile", "?0")
            request.headers.setdefault("Sec-CH-UA-Platform", '"Linux"')

        # Cache-Control
        request.headers.setdefault("Cache-Control", "max-age=0")

        # Referer: если есть в метаданных запроса
        referer = request.meta.get("referer")
        if referer:
            request.headers.setdefault("Referer", referer)

    def process_response(self, request: Request, response):
        """Обработать ответ: проверить на блокировку."""
        import logging

        log = logging.getLogger(__name__)

        if response.status == 403:
            log.warning(f"403 Forbidden: {request.url}")
        elif response.status == 429:
            log.warning(f"429 Rate limited: {request.url}")
        elif response.status == 503:
            if (
                b"cloudflare" in response.body[:500].lower()
                or b"cf-browser-verification" in response.body[:500].lower()
            ):
                log.warning(f"Cloudflare challenge detected: {request.url}")

        return response
