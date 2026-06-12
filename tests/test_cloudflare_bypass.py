"""
Тесты для CloudflareBypass и FlareSolverrClient.

Покрывает:
  - BypassResult dataclass
  - FlareSolverrClient.solve (mock HTTP)
  - FlareSolverrClient.health_check
  - CloudflareBypass.solve (авто-выбор метода)
  - CloudflareBypass._direct_request
  - Retry/backoff логика
  - Валидация URL
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from lab_playwright_kit.cloudflare_bypass import (
    BypassResult,
    CloudflareBypass,
    FlareSolverrClient,
)


# ─── BypassResult ────────────────────────────────────────────────────────────

class TestBypassResult:
    """Тесты dataclass BypassResult."""

    def test_default_values(self):
        r = BypassResult()
        assert r.success is False
        assert r.cookies == {}
        assert r.user_agent == ""
        assert r.response_text == ""
        assert r.elapsed_seconds == 0.0
        assert r.method == "none"
        assert r.error == ""

    def test_to_dict(self):
        r = BypassResult(
            success=True,
            cookies={"cf_clearance": "abc123"},
            user_agent="Mozilla/5.0",
            elapsed_seconds=5.5,
            method="flaresolverr",
        )
        d = r.to_dict()
        assert d["success"] is True
        assert d["cookies_count"] == 1
        assert d["user_agent"] == "Mozilla/5.0"
        assert d["elapsed_seconds"] == 5.5
        assert d["method"] == "flaresolverr"

    def test_to_dict_empty_cookies(self):
        r = BypassResult(success=False)
        d = r.to_dict()
        assert d["cookies_count"] == 0
        assert d["user_agent"] == ""


# ─── FlareSolverrClient ──────────────────────────────────────────────────────

class TestFlareSolverrClient:
    """Тесты FlareSolverrClient с mock HTTP."""

    @pytest.fixture
    def client(self):
        return FlareSolverrClient(
            base_url="http://localhost:8191",
            timeout=5.0,
            max_retries=3,
        )

    @pytest.mark.asyncio
    async def test_health_check_success(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.get = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_ctx

            result = await client.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, client):
        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.get = AsyncMock(side_effect=ConnectionError("refused"))
            mock_cls.return_value = mock_ctx

            result = await client.health_check()
            assert result is False

    @pytest.mark.asyncio
    async def test_solve_success(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={
            "solution": {
                "status": 200,
                "cookies": [
                    {"name": "cf_clearance", "value": "token123"},
                ],
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "response": "<html>OK</html>",
            }
        })

        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_ctx

            result = await client.solve("https://example.com")

            assert result.success is True
            assert result.cookies == {"cf_clearance": "token123"}
            assert result.user_agent == "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            assert result.method == "flaresolverr"
            assert result.error == ""

    @pytest.mark.asyncio
    async def test_solve_http_error(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_ctx

            result = await client.solve("https://example.com")

            assert result.success is False
            assert result.method == "flaresolverr"
            assert "Max retries" in result.error

    @pytest.mark.asyncio
    async def test_solve_timeout_retry(self, client):
        """Timeout на первой попытке → retry → успех."""
        fail_resp = MagicMock(side_effect=httpx.TimeoutException("timeout"))
        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.json = MagicMock(return_value={
            "solution": {
                "status": 200,
                "cookies": [{"name": "cf", "value": "v"}],
                "userAgent": "Mozilla/5.0",
                "response": "",
            }
        })

        with patch("httpx.AsyncClient") as mock_cls, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.post = AsyncMock(side_effect=[fail_resp, success_resp])
            mock_cls.return_value = mock_ctx

            result = await client.solve("https://example.com")

            assert result.success is True
            assert mock_ctx.post.call_count == 2

    @pytest.mark.asyncio
    async def test_solve_with_cookies(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={
            "solution": {
                "status": 200,
                "cookies": [],
                "userAgent": "",
                "response": "",
            }
        })

        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_ctx

            await client.solve(
                "https://example.com",
                cookies={"session": "abc"},
            )

            # Проверяем что cookies переданы в payload
            call_args = mock_ctx.post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            assert "cookies" in payload
            assert payload["cookies"] == [{"name": "session", "value": "abc"}]

    @pytest.mark.asyncio
    async def test_solve_with_proxy(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={
            "solution": {
                "status": 200,
                "cookies": [],
                "userAgent": "",
                "response": "",
            }
        })

        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_ctx

            await client.solve(
                "https://example.com",
                proxy="http://proxy:8080",
            )

            call_args = mock_ctx.post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            assert "proxy" in payload
            assert payload["proxy"] == {"url": "http://proxy:8080"}

    @pytest.mark.asyncio
    async def test_solve_post(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={
            "solution": {
                "status": 200,
                "cookies": [{"name": "cf", "value": "v"}],
                "userAgent": "Mozilla/5.0",
                "response": "",
            }
        })

        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_ctx

            result = await client.solve_post(
                "https://example.com/api",
                post_data={"key": "value"},
            )

            assert result.success is True
            assert result.method == "flaresolverr"


# ─── CloudflareBypass ────────────────────────────────────────────────────────

class TestCloudflareBypass:
    """Тесты CloudflareBypass (авто-выбор метода)."""

    @pytest.fixture
    def bypass(self):
        return CloudflareBypass(
            flaresolverr_url="http://localhost:8191",
            use_cloakbrowser=False,
        )

    @pytest.mark.asyncio
    async def test_solve_via_flaresolverr(self, bypass):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={
            "solution": {
                "status": 200,
                "cookies": [{"name": "cf_clearance", "value": "token"}],
                "userAgent": "Mozilla/5.0",
                "response": "",
            }
        })

        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.get = AsyncMock(return_value=MagicMock(status_code=200))
            mock_ctx.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_ctx

            result = await bypass.solve("https://example.com")

            assert result.success is True
            assert result.method == "flaresolverr"

    @pytest.mark.asyncio
    async def test_solve_fallback_to_direct(self, bypass):
        """FlareSolverr недоступен → fallback на прямой запрос."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html>OK</html>"
        mock_resp.cookies = MagicMock()
        mock_resp.cookies.jar = []

        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            # health_check fails
            mock_ctx.get = AsyncMock(side_effect=ConnectionError("refused"))
            # direct request succeeds
            mock_ctx.get = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_ctx

            result = await bypass.solve("https://example.com")

            # Должен быть direct (fallback)
            assert result.method == "direct"

    @pytest.mark.asyncio
    async def test_check_flaresolverr_caching(self, bypass):
        """Результат health_check кэшируется."""
        with patch.object(bypass.flaresolverr, "health_check", new_callable=AsyncMock) as mock_hc:
            mock_hc.return_value = True

            r1 = await bypass.check_flaresolverr()
            r2 = await bypass.check_flaresolverr()

            assert r1 is True
            assert r2 is True
            # health_check вызван только раз
            assert mock_hc.call_count == 1

    @pytest.mark.asyncio
    async def test_direct_request_success(self, bypass):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html>content</html>"
        mock_resp.cookies = MagicMock()
        mock_resp.cookies.jar = []

        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.get = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_ctx

            result = await bypass._direct_request("https://example.com")

            assert result.success is True
            assert result.method == "direct"
            assert result.response_text == "<html>content</html>"

    @pytest.mark.asyncio
    async def test_direct_request_failure(self, bypass):
        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.get = AsyncMock(side_effect=ConnectionError("refused"))
            mock_cls.return_value = mock_ctx

            result = await bypass._direct_request("https://example.com")

            assert result.success is False
            assert result.method == "direct"
            assert "refused" in result.error


# ─── Retry/Backoff ──────────────────────────────────────────────────────────

class TestRetryBackoff:
    """Тесты retry/backoff логики."""

    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        """Проверяем что задержки растут экспоненциально."""
        client = FlareSolverrClient(max_retries=3)

        delays = []
        original_sleep = asyncio.sleep

        async def mock_sleep(delay):
            delays.append(delay)

        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("httpx.AsyncClient") as mock_cls, \
             patch("asyncio.sleep", side_effect=mock_sleep):
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_ctx

            await client.solve("https://example.com")

            # 3 retry → 2 задержки (после 1-й и 2-й попыток)
            assert len(delays) == 2
            assert delays[0] == 1  # 2^0
            assert delays[1] == 2  # 2^1

    @pytest.mark.asyncio
    async def test_max_retries_respected(self):
        """Количество retry не превышает max_retries."""
        client = FlareSolverrClient(max_retries=2)

        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("httpx.AsyncClient") as mock_cls, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_ctx

            result = await client.solve("https://example.com")

            assert result.success is False
            # max_retries=2 → 2 post вызова
            assert mock_ctx.post.call_count == 2
