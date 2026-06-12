"""
Cloudflare Bypass — обход Cloudflare и других защитных систем.

Поддерживает два метода:
  1. FlareSolverr — внешний сервис для решения Cloudflare challenges
  2. CloakBrowser — встроенные C++ патчи для обхода

FlareSolverr:
  - Отдельный Docker-контейнер
  - Решает JS challenges, CAPTCHA, Turnstile
  - Возвращает cookies для последующих запросов

Использование:
    >>> bypass = CloudflareBypass(flaresolverr_url="http://localhost:8191")
    >>> cookies = await bypass.solve("https://example.com")
    >>> # Использовать cookies в запросах
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger


@dataclass
class BypassResult:
    """Результат обхода защиты.

    Attributes:
        success: Успешно ли пройдена защита
        cookies: Полученные cookies
        user_agent: User-Agent для запросов
        response_text: Текст ответа (если нужен)
        elapsed_seconds: Время выполнения
        method: Метод обхода (flaresolverr, cloakbrowser, none)
        error: Текст ошибки (если есть)
    """
    success: bool = False
    cookies: dict[str, str] = field(default_factory=dict)
    user_agent: str = ""
    response_text: str = ""
    elapsed_seconds: float = 0.0
    method: str = "none"
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "cookies_count": len(self.cookies),
            "user_agent": self.user_agent[:50] if self.user_agent else "",
            "elapsed_seconds": self.elapsed_seconds,
            "method": self.method,
        }


class FlareSolverrClient:
    """Клиент для FlareSolverr.

    FlareSolverr — это прокси-сервис который решает Cloudflare challenges.
    Запускается как Docker контейнер:
        docker run -d --name flaresolverr -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest

    API:
        POST /v1 — решить challenge
        GET / — health check

    Использование:
        >>> client = FlareSolverrClient("http://localhost:8191")
        >>> result = await client.solve("https://example.com")
        >>> if result.success:
        ...     print(result.cookies)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8191",
        timeout: float = 120.0,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    async def health_check(self) -> bool:
        """Проверить доступность FlareSolverr."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/")
                return response.status_code == 200
        except Exception:
            return False

    async def solve(
        self,
        url: str,
        cookies: dict[str, str] | None = None,
        proxy: str | None = None,
        max_timeout_ms: int = 120000,
    ) -> BypassResult:
        """Решить Cloudflare challenge для URL.

        Args:
            url: URL для обхода
            cookies: Предварительные cookies
            proxy: Прокси (опционально)
            max_timeout_ms: Максимальное время ожидания (мс)

        Returns:
            BypassResult с cookies и user-agent
        """
        import time
        start = time.time()

        payload: dict[str, Any] = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": max_timeout_ms,
        }

        if cookies:
            payload["cookies"] = [
                {"name": k, "value": v} for k, v in cookies.items()
            ]

        if proxy:
            payload["proxy"] = {"url": proxy}

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/v1",
                        json=payload,
                    )

                    if response.status_code != 200:
                        logger.warning(
                            f"FlareSolverr error: HTTP {response.status_code}"
                        )
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(2 ** attempt)
                        continue

                    data = response.json()
                    solution = data.get("solution", {})

                    if solution.get("status") == 200:
                        cookies_dict = {
                            c["name"]: c["value"]
                            for c in solution.get("cookies", [])
                        }

                        elapsed = time.time() - start
                        logger.info(
                            f"FlareSolverr solved {url} in {elapsed:.1f}s"
                        )

                        return BypassResult(
                            success=True,
                            cookies=cookies_dict,
                            user_agent=solution.get("userAgent", ""),
                            response_text=solution.get("response", ""),
                            elapsed_seconds=elapsed,
                            method="flaresolverr",
                        )
                    else:
                        logger.warning(
                            f"FlareSolverr failed: {solution.get('message', 'unknown')}"
                        )

            except httpx.TimeoutException:
                logger.warning(f"FlareSolverr timeout (attempt {attempt + 1})")
            except Exception as e:
                logger.error(f"FlareSolverr error: {e}")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)

        elapsed = time.time() - start
        return BypassResult(
            success=False,
            elapsed_seconds=elapsed,
            method="flaresolverr",
            error="Max retries exceeded",
        )

    async def solve_post(
        self,
        url: str,
        post_data: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        max_timeout_ms: int = 120000,
    ) -> BypassResult:
        """Решить Cloudflare challenge для POST запроса.

        Args:
            url: URL для POST
            post_data: Данные для POST
            cookies: Предварительные cookies
            max_timeout_ms: Максимальное время ожидания

        Returns:
            BypassResult
        """
        import time
        start = time.time()

        payload: dict[str, Any] = {
            "cmd": "request.post",
            "url": url,
            "maxTimeout": max_timeout_ms,
        }

        if post_data:
            payload["postData"] = "&".join(
                f"{k}={v}" for k, v in post_data.items()
            )

        if cookies:
            payload["cookies"] = [
                {"name": k, "value": v} for k, v in cookies.items()
            ]

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1",
                    json=payload,
                )

                data = response.json()
                solution = data.get("solution", {})

                if solution.get("status") == 200:
                    cookies_dict = {
                        c["name"]: c["value"]
                        for c in solution.get("cookies", [])
                    }

                    return BypassResult(
                        success=True,
                        cookies=cookies_dict,
                        user_agent=solution.get("userAgent", ""),
                        response_text=solution.get("response", ""),
                        elapsed_seconds=time.time() - start,
                        method="flaresolverr",
                    )

        except Exception as e:
            logger.error(f"FlareSolverr POST error: {e}")

        return BypassResult(
            success=False,
            elapsed_seconds=time.time() - start,
            method="flaresolverr",
            error="POST request failed",
        )


class CloudflareBypass:
    """Универсальный обход Cloudflare.

    Автоматически выбирает метод:
    1. FlareSolverr (если доступен)
    2. CloakBrowser (если настроен)
    3. Прямой запрос (fallback)

    Использование:
        >>> bypass = CloudflareBypass()
        >>> result = await bypass.solve("https://example.com")
        >>> if result.success:
        ...     # Использовать cookies
        ...     async with httpx.AsyncClient() as client:
        ...         resp = await client.get(url, cookies=result.cookies)
    """

    def __init__(
        self,
        flaresolverr_url: str = "http://localhost:8191",
        use_cloakbrowser: bool = True,
        timeout: float = 120.0,
    ):
        self.flaresolverr = FlareSolverrClient(
            base_url=flaresolverr_url,
            timeout=timeout,
        )
        self.use_cloakbrowser = use_cloakbrowser
        self._flaresolverr_available: bool | None = None

    async def check_flaresolverr(self) -> bool:
        """Проверить доступность FlareSolverr."""
        if self._flaresolverr_available is None:
            self._flaresolverr_available = await self.flaresolverr.health_check()
            if self._flaresolverr_available:
                logger.info("FlareSolverr is available")
            else:
                logger.info("FlareSolverr is not available")
        return self._flaresolverr_available

    async def solve(self, url: str, **kwargs) -> BypassResult:
        """Решить Cloudflare challenge (авто-выбор метода)."""
        # Пробовать FlareSolverr
        if await self.check_flaresolverr():
            result = await self.flaresolverr.solve(url, **kwargs)
            if result.success:
                return result

        # Fallback: прямой запрос
        logger.info(f"Direct request fallback for {url}")
        return await self._direct_request(url)

    async def _direct_request(self, url: str) -> BypassResult:
        """Прямой запрос без обхода (fallback)."""
        import time
        start = time.time()

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                },
            ) as client:
                response = await client.get(url)

                cookies = {
                    c.name: c.value
                    for c in response.cookies.jar
                }

                return BypassResult(
                    success=response.status_code == 200,
                    cookies=cookies,
                    response_text=response.text[:1000],
                    elapsed_seconds=time.time() - start,
                    method="direct",
                )

        except Exception as e:
            return BypassResult(
                success=False,
                elapsed_seconds=time.time() - start,
                method="direct",
                error=str(e)[:200],
            )
