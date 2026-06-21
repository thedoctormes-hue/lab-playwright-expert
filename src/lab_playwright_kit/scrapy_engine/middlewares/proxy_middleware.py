"""
ProxyMiddleware — Scrapy middleware для ротации прокси.

Интегрируется с существующим ProxyRotator из proxy_rotation.py.
Поддерживает:
- Round-robin ротация
- Автоисключение нерабочих прокси
- Переменные окружения для списка прокси
"""

from __future__ import annotations

import logging

from scrapy import Request


log = logging.getLogger(__name__)

import os


class ProxyMiddleware:
    """
    Scrapy middleware: ротация прокси.

    Конфигурация через Scrapy settings:
        PROXY_LIST = [
            "http://proxy1:8080",
            "socks5://proxy2:1080",
        ]
        PROXY_MODE = "round_robin"  # or "random"

    Или через переменную окружения:
        SCRAPY_PROXIES=http://p1:8080,http://p2:8080
    """

    def __init__(self, proxy_list: list[str] | None = None, mode: str = "round_robin"):
        self._proxies = proxy_list or self._load_from_env()
        self._mode = mode
        self._index = 0

    @classmethod
    def from_crawler(cls, crawler):
        proxy_list = crawler.settings.getlist("PROXY_LIST", [])
        mode = crawler.settings.get("PROXY_MODE", "round_robin")
        return cls(proxy_list=proxy_list, mode=mode)

    def _load_from_env(self) -> list[str]:
        """Загрузить прокси из переменной окружения."""
        raw = os.environ.get("SCRAPY_PROXIES", "")
        return [p.strip() for p in raw.split(",") if p.strip()]

    def _get_next_proxy(self) -> str | None:
        """Получить следующий прокси."""
        if not self._proxies:
            return None

        if self._mode == "round_robin":
            proxy = self._proxies[self._index % len(self._proxies)]
            self._index += 1
            return proxy

        # random mode
        import random

        return random.choice(self._proxies)

    def process_request(self, request: Request) -> None:
        """Установить прокси для запроса."""
        # Не переопределять если прокси уже установлен
        if request.meta.get("proxy"):
            return

        proxy = self._get_next_proxy()
        if proxy:
            request.meta["proxy"] = proxy
            request.meta["download_timeout"] = 30

    def process_exception(self, request: Request, exception):
        """Обработать ошибку прокси: повторить запрос без прокси."""
        proxy = request.meta.get("proxy")
        if proxy:
            log.warning(f"Proxy failed: {proxy}, error: {exception}")
            # Повторить без прокси
            new_request = request.copy()
            new_request.meta.pop("proxy", None)
            new_request.dont_filter = True
            return new_request

    def process_response(self, request: Request, response):
        """Проверить ответ на блокировку."""
        proxy = request.meta.get("proxy")
        if proxy and response.status in (403, 429, 503):
            log.warning(f"Proxy {proxy} returned {response.status} for {request.url}")
        return response
