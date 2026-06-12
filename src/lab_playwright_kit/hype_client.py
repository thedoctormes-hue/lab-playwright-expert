"""
Hype Pilot Client — клиент для SaaS Parsing API.

Интегрирует lab-playwright-expert с контент-пайплайном Hype Pilot.
Используется из crosspost.py, hype_orq.py и других компонентов.

Пример:
    >>> from lab_playwright_kit.hype_client import HypeClient
    >>> async with HypeClient("http://localhost:8190") as client:
    ...     result = await client.crosspost("Заголовок", "Текст", ["habr", "vcru", "telegraph"])
    ...     print(result)
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import aiohttp
from loguru import logger

from .telegraph_publisher import TelegraphPublisher, TelegraphError


@dataclass
class CrossPostResult:
    """Результат кросспостинга на одну платформу."""
    platform: str
    success: bool
    url: str = ""
    error: str = ""
    elapsed_seconds: float = 0.0


@dataclass
class CrossPostReport:
    """Отчёт о кросспостинге на все платформы."""
    title: str
    platforms: list[str]
    results: list[CrossPostResult] = field(default_factory=list)
    total_elapsed: float = 0.0

    @property
    def all_success(self) -> bool:
        return all(r.success for r in self.results) and len(self.results) > 0

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failed_platforms(self) -> list[str]:
        return [r.platform for r in self.results if not r.success]

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "platforms": self.platforms,
            "success_count": self.success_count,
            "total": len(self.results),
            "all_success": self.all_success,
            "failed_platforms": self.failed_platforms,
            "results": [
                {
                    "platform": r.platform,
                    "success": r.success,
                    "url": r.url,
                    "error": r.error,
                    "elapsed": round(r.elapsed_seconds, 2),
                }
                for r in self.results
            ],
            "total_elapsed": round(self.total_elapsed, 2),
        }


class HypeClient:
    """Клиент для SaaS Parsing API (Hype Pilot интеграция).

    Использование:
        # Как контекстный менеджер
        async with HypeClient("http://localhost:8190") as client:
            report = await client.crosspost("Title", "Content", ["habr", "vcru"])

        # Вручную
        client = HypeClient("http://localhost:8190")
        await client.connect()
        report = await client.crosspost("Title", "Content", ["habr"])
        await client.close()
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8190",
        timeout: float = 120.0,
        max_retries: int = 3,
        retry_delay: float = 2.0,
        telegraph_token: str = "",
        telegraph_author: str = "",
        telegraph_author_url: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._session: aiohttp.ClientSession | None = None
        self._telegraph_token = telegraph_token
        self._telegraph_author = telegraph_author
        self._telegraph_author_url = telegraph_author_url

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def connect(self):
        """Открыть HTTP-сессию."""
        if not self._session:
            self._session = aiohttp.ClientSession(timeout=self.timeout)

    async def close(self):
        """Закрыть HTTP-сессию."""
        if self._session:
            await self._session.close()
            self._session = None

    async def _request(
        self,
        method: str,
        path: str,
        json_data: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        """HTTP-запрос с ретраями."""
        if not self._session:
            raise RuntimeError("Client not connected. Use 'async with' or call connect()")

        url = f"{self.base_url}{path}"

        for attempt in range(1, self.max_retries + 1):
            try:
                async with self._session.request(
                    method, url, json=json_data, params=params
                ) as resp:
                    data = await resp.json()
                    if resp.status >= 400:
                        logger.warning(f"API error {resp.status}: {data}")
                    return data
            except aiohttp.ClientError as e:
                logger.warning(f"Request failed (attempt {attempt}/{self.max_retries}): {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay * attempt)
                else:
                    raise

    # ─── Health & Status ─────────────────────────────────────────────────

    async def health(self) -> dict:
        """Health check."""
        return await self._request("GET", "/api/v1/health")

    async def status(self) -> dict:
        """Статус системы."""
        return await self._request("GET", "/api/v1/status")

    async def is_healthy(self) -> bool:
        """Проверить что API жив."""
        try:
            data = await self.health()
            return data.get("status") == "healthy"
        except Exception:
            return False

    # ─── Parsing ─────────────────────────────────────────────────────────

    async def parse_url(
        self,
        url: str,
        niche: str = "",
        timeout: float = 30.0,
        proxy_url: str = "",
        wait_for: str = "",
        metadata: dict | None = None,
    ) -> dict:
        """Парсинг одного URL."""
        return await self._request("POST", "/api/v1/parse", json_data={
            "url": url,
            "niche": niche,
            "timeout": timeout,
            "proxy_url": proxy_url,
            "wait_for": wait_for,
            "metadata": metadata or {},
        })

    async def parse_batch(
        self,
        urls: list[str],
        niche: str = "",
        timeout: float = 30.0,
        max_concurrency: int = 3,
        delay_between: float = 1.0,
    ) -> dict:
        """Батч-парсинг."""
        return await self._request("POST", "/api/v1/parse/batch", json_data={
            "urls": urls,
            "niche": niche,
            "timeout": timeout,
            "max_concurrency": max_concurrency,
            "delay_between": delay_between,
        })

    async def list_niches(self) -> list[dict]:
        """Список доступных ниш."""
        return await self._request("GET", "/api/v1/niches")

    async def get_niche(self, name: str) -> dict:
        """Детали ниши."""
        return await self._request("GET", f"/api/v1/niches/{name}")

    # ─── Auth ────────────────────────────────────────────────────────────

    async def auth_login(
        self,
        platform: str,
        username: str,
        password: str,
        force: bool = False,
        proxy_url: str = "",
    ) -> dict:
        """Авторизация на платформе."""
        return await self._request("POST", "/api/v1/auth/login", json_data={
            "platform": platform,
            "username": username,
            "password": password,
            "force": force,
            "proxy_url": proxy_url,
        })

    async def auth_check(self, platform: str, username: str = "") -> dict:
        """Проверка авторизации."""
        return await self._request("POST", "/api/v1/auth/check", json_data={
            "platform": platform,
            "username": username,
        })

    async def auth_2fa(self, platform: str, username: str, code: str) -> dict:
        """Отправка 2FA кода."""
        return await self._request("POST", "/api/v1/auth/2fa", json_data={
            "platform": platform,
            "username": username,
            "code": code,
        })

    async def auth_list_sessions(self, platform: str = "") -> dict:
        """Список сессий."""
        params = {"platform": platform} if platform else None
        return await self._request("GET", "/api/v1/auth/sessions", params=params)

    async def auth_delete_session(self, platform: str, username: str) -> dict:
        """Удаление сессии."""
        return await self._request("DELETE", f"/api/v1/auth/sessions/{platform}/{username}")

    async def auth_list_presets(self) -> dict:
        """Список пресетов авторизации."""
        return await self._request("GET", "/api/v1/auth/presets")

    # ─── Publish ─────────────────────────────────────────────────────────

    async def publish(
        self,
        platform: str,
        title: str,
        content: str,
        username: str = "",
        proxy_url: str = "",
        timeout: float = 60.0,
        dry_run: bool = False,
    ) -> dict:
        """Опубликовать контент на платформе.

        Args:
            platform: Платформа (habr, vcru, tenchat, telegraph)
            title: Заголовок поста
            content: Текст контента (HTML для telegraph)
            username: Логин (пусто = первая доступная сессия)
            proxy_url: Прокси
            timeout: Таймаут в секундах
            dry_run: Тестовый прогон без публикации

        Returns:
            dict с ключами: success, platform, url, message, error, elapsed_seconds
        """
        # Telegraph публикация через REST API (не через SaaS API)
        if platform == "telegraph":
            return await self._publish_telegraph(title, content, dry_run)

        return await self._request("POST", "/api/v1/publish", json_data={
            "platform": platform,
            "title": title,
            "content": content,
            "username": username,
            "proxy_url": proxy_url,
            "timeout": timeout,
            "dry_run": dry_run,
        })

    async def _publish_telegraph(self, title: str, content: str, dry_run: bool = False) -> dict:
        """Опубликовать контент на Telegraph через REST API."""
        start = time.time()

        if dry_run:
            return {
                "success": True,
                "platform": "telegraph",
                "url": "https://telegra.ph/dry-run",
                "message": "Dry run — telegraph publish skipped",
                "error": "",
                "elapsed_seconds": 0.0,
                "dry_run": True,
            }

        if not self._telegraph_token:
            return {
                "success": False,
                "platform": "telegraph",
                "url": "",
                "message": "Telegraph token not configured",
                "error": "NO_TELEGRAPH_TOKEN",
                "elapsed_seconds": time.time() - start,
                "dry_run": False,
            }

        try:
            async with TelegraphPublisher(access_token=self._telegraph_token) as pub:
                result = await pub.publish(
                    title=title,
                    content=content,
                    author_name=self._telegraph_author,
                    author_url=self._telegraph_author_url,
                )

            elapsed = time.time() - start
            return {
                "success": result.success,
                "platform": "telegraph",
                "url": result.page.url if result.page else "",
                "message": f"Published to Telegraph: {result.page.url}" if result.success else result.error,
                "error": result.error,
                "elapsed_seconds": elapsed,
                "dry_run": False,
            }
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"Telegraph publish error: {e}")
            return {
                "success": False,
                "platform": "telegraph",
                "url": "",
                "message": str(e),
                "error": str(e),
                "elapsed_seconds": elapsed,
                "dry_run": False,
            }

    # ─── CrossPost (высокоуровневый) ─────────────────────────────────────

    async def crosspost(
        self,
        title: str,
        content: str,
        platforms: list[str] | None = None,
    ) -> CrossPostReport:
        """Кросспостинг на несколько платформ.

        Высокоуровневая обёртка: проверяет авторизацию,
        публикует, собирает отчёт.

        Args:
            title: Заголовок поста/статьи
            content: Текст (HTML для telegraph)
            platforms: Список платформ (habr, vcru, tenchat, telegraph).
                       None = все доступные.

        Returns:
            CrossPostReport с результатами
        """
        if platforms is None:
            platforms = ["habr", "vcru", "telegraph"]

        report = CrossPostReport(title=title, platforms=platforms)
        start = time.time()

        for platform in platforms:
            result = await self._crosspost_single(title, content, platform)
            report.results.append(result)

        report.total_elapsed = time.time() - start
        return report

    async def _crosspost_single(
        self,
        title: str,
        content: str,
        platform: str,
    ) -> CrossPostResult:
        """Кросспостинг на одну платформу через POST /api/v1/publish."""
        start = time.time()

        try:
            data = await self._request("POST", "/api/v1/publish", json_data={
                "platform": platform,
                "title": title,
                "content": content,
                "timeout": 60.0,
            })

            elapsed = time.time() - start

            return CrossPostResult(
                platform=platform,
                success=data.get("success", False),
                url=data.get("url", ""),
                error=data.get("error", ""),
                elapsed_seconds=elapsed,
            )

        except Exception as e:
            logger.error(f"CrossPost error [{platform}]: {e}")
            return CrossPostResult(
                platform=platform,
                success=False,
                error=str(e),
                elapsed_seconds=time.time() - start,
            )

    @staticmethod
    def _get_publish_url(platform: str) -> str:
        """URL для публикации на платформе."""
        urls = {
            "habr": "https://habr.com/ru/articles/draft/",
            "vcru": "https://vc.ru/write",
            "tenchat": "https://tenchat.ru/post/new",
            "telegraph": "https://telegra.ph/",
        }
        return urls.get(platform, "")


# ─── Convenience Functions ───────────────────────────────────────────────────

async def quick_crosspost(
    title: str,
    content: str,
    platforms: list[str] | None = None,
    api_url: str = "http://localhost:8190",
    telegraph_token: str = "",
) -> CrossPostReport:
    """Быстрый кросспостинг без явного создания клиента.

    Пример:
        report = await quick_crosspost("Title", "Content", ["habr", "vcru", "telegraph"],
                                       telegraph_token="your_token")
        print(report.to_dict())
    """
    async with HypeClient(api_url, telegraph_token=telegraph_token) as client:
        return await client.crosspost(title, content, platforms)


async def check_api(api_url: str = "http://localhost:8190") -> bool:
    """Проверить что SaaS API доступен."""
    try:
        async with HypeClient(api_url) as client:
            return await client.is_healthy()
    except Exception:
        return False
