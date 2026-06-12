"""
Перехват и анализ сетевых запросов.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

from loguru import logger
from playwright.async_api import Page, Request, Response


@dataclass
class CapturedRequest:
    """Перехваченный запрос."""
    url: str
    method: str
    headers: dict[str, str]
    post_data: str | None
    resource_type: str
    response_status: int | None = None
    response_body: str | None = None


@dataclass
class NetworkLog:
    """Лог сетевых запросов."""
    requests: list[CapturedRequest] = field(default_factory=list)

    def filter_by_domain(self, domain: str) -> list[CapturedRequest]:
        return [r for r in self.requests if domain in r.url]

    def filter_by_type(self, resource_type: str) -> list[CapturedRequest]:
        return [r for r in self.requests if r.resource_type == resource_type]

    def filter_by_status(self, status: int) -> list[CapturedRequest]:
        return [r for r in self.requests if r.response_status == status]

    def get_api_calls(self) -> list[CapturedRequest]:
        """Получить все API-вызовы (XHR/Fetch)."""
        return [r for r in self.requests if r.resource_type in ("xhr", "fetch")]

    def to_dict(self) -> dict:
        return {
            "total": len(self.requests),
            "requests": [
                {
                    "url": r.url,
                    "method": r.method,
                    "status": r.response_status,
                    "type": r.resource_type,
                }
                for r in self.requests
            ],
        }


class NetworkInterceptor:
    """Перехватчик сетевых запросов."""

    def __init__(self, page: Page):
        self.page = page
        self.log = NetworkLog()
        self._handlers: list[Callable] = []

    def attach(self) -> None:
        """Подключить перехватчики."""
        self.page.on("request", self._on_request)
        self.page.on("response", self._on_response)
        logger.debug("Network interceptor attached")

    def detach(self) -> None:
        """Отключить перехватчики."""
        self.page.remove_listener("request", self._on_request)
        self.page.remove_listener("response", self._on_response)
        logger.debug("Network interceptor detached")

    async def _on_request(self, request: Request) -> None:
        """Обработчик запроса."""
        captured = CapturedRequest(
            url=request.url,
            method=request.method,
            headers=await request.all_headers(),
            post_data=request.post_data,
            resource_type=request.resource_type,
        )
        self.log.requests.append(captured)

    async def _on_response(self, response: Response) -> None:
        """Обработчик ответа."""
        # Найти соответствующий запрос
        for req in self.log.requests:
            if req.url == response.url:
                req.response_status = response.status
                try:
                    req.response_body = await response.text()
                except Exception:
                    pass
                break

    async def wait_for_api(
        self,
        url_pattern: str,
        timeout: int = 10000,
    ) -> CapturedRequest | None:
        """Подождать конкретный API-запрос по паттерну URL."""
        future = self.page.loop.create_future()

        def check_request(request: Request):
            if url_pattern in request.url and not future.done():
                future.set_result(request)

        self.page.on("request", check_request)
        try:
            await asyncio.wait_for(future, timeout=timeout / 1000)
            for req in self.log.requests:
                if url_pattern in req.url:
                    return req
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for API: {url_pattern}")
        finally:
            self.page.remove_listener("request", check_request)

        return None

    async def intercept_and_block(self, url_patterns: list[str]) -> None:
        """Блокировать запросы по паттернам."""

        async def block(route, request):
            await route.abort()

        for pattern in url_patterns:
            await self.page.route(pattern, block)
        logger.info(f"Blocked patterns: {url_patterns}")

    async def mock_response(
        self,
        url_pattern: str,
        body: str,
        status: int = 200,
        content_type: str = "application/json",
    ) -> None:
        """Подменить ответ для URL-паттерна."""

        async def mock(route, request):
            await route.fulfill(
                status=status,
                body=body,
                content_type=content_type,
            )

        await self.page.route(url_pattern, mock)
        logger.info(f"Mocked: {url_pattern}")
