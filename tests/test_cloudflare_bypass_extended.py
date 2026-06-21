"""
Расширенные тесты для CloudflareBypass, FlareSolverrClient, BypassResult.

Покрывает:
  - BypassResult dataclass: defaults, to_dict
  - FlareSolverrClient: __init__, health_check (mocked)
  - CloudflareBypass: __init__, check_flaresolverr (mocked)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lab_playwright_kit.cloudflare_bypass import (
    BypassResult,
    CloudflareBypass,
    FlareSolverrClient,
)


# ─── BypassResult defaults ───────────────────────────────────────────────


class TestBypassResult:
    def test_default_success_false(self):
        r = BypassResult()
        assert r.success is False

    def test_default_cookies_empty(self):
        r = BypassResult()
        assert r.cookies == {}

    def test_default_user_agent_empty(self):
        r = BypassResult()
        assert r.user_agent == ""

    def test_default_response_text_empty(self):
        r = BypassResult()
        assert r.response_text == ""

    def test_default_elapsed_zero(self):
        r = BypassResult()
        assert r.elapsed_seconds == 0.0

    def test_default_method_none(self):
        r = BypassResult()
        assert r.method == "none"

    def test_default_error_empty(self):
        r = BypassResult()
        assert r.error == ""


# ─── BypassResult custom values ──────────────────────────────────────────


class TestBypassResultCustom:
    def test_success_true(self):
        r = BypassResult(success=True)
        assert r.success is True

    def test_with_cookies(self):
        r = BypassResult(cookies={"cf_clearance": "abc123"})
        assert r.cookies == {"cf_clearance": "abc123"}

    def test_with_user_agent(self):
        r = BypassResult(user_agent="Mozilla/5.0")
        assert r.user_agent == "Mozilla/5.0"

    def test_with_method(self):
        r = BypassResult(method="flaresolverr")
        assert r.method == "flaresolverr"

    def test_with_error(self):
        r = BypassResult(error="timeout")
        assert r.error == "timeout"


# ─── BypassResult.to_dict ────────────────────────────────────────────────


class TestBypassResultToDict:
    def test_to_dict_keys(self):
        r = BypassResult(
            success=True, cookies={"a": "b"}, user_agent="UA", elapsed_seconds=1.5, method="direct"
        )
        d = r.to_dict()
        assert "success" in d
        assert "cookies_count" in d
        assert "user_agent" in d
        assert "elapsed_seconds" in d
        assert "method" in d

    def test_to_dict_success(self):
        r = BypassResult(success=True)
        assert r.to_dict()["success"] is True

    def test_to_dict_cookies_count(self):
        r = BypassResult(cookies={"a": "b", "c": "d"})
        assert r.to_dict()["cookies_count"] == 2

    def test_to_dict_cookies_count_zero(self):
        r = BypassResult()
        assert r.to_dict()["cookies_count"] == 0

    def test_to_dict_user_agent_truncated(self):
        r = BypassResult(user_agent="A" * 100)
        assert len(r.to_dict()["user_agent"]) <= 50

    def test_to_dict_user_agent_empty(self):
        r = BypassResult()
        assert r.to_dict()["user_agent"] == ""


# ─── FlareSolverrClient init ─────────────────────────────────────────────


class TestFlareSolverrClientInit:
    def test_default_url(self):
        c = FlareSolverrClient()
        assert c.base_url == "http://localhost:8191"

    def test_custom_url(self):
        c = FlareSolverrClient(base_url="http://custom:9999")
        assert c.base_url == "http://custom:9999"

    def test_url_trailing_slash_stripped(self):
        c = FlareSolverrClient(base_url="http://custom:9999/")
        assert c.base_url == "http://custom:9999"

    def test_default_timeout(self):
        c = FlareSolverrClient()
        assert c.timeout == 120.0

    def test_custom_timeout(self):
        c = FlareSolverrClient(timeout=60.0)
        assert c.timeout == 60.0

    def test_default_max_retries(self):
        c = FlareSolverrClient()
        assert c.max_retries == 3

    def test_custom_max_retries(self):
        c = FlareSolverrClient(max_retries=5)
        assert c.max_retries == 5


# ─── FlareSolverrClient.health_check ─────────────────────────────────────


class TestFlareSolverrHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy(self):
        c = FlareSolverrClient()
        with patch("httpx.AsyncClient") as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_ctx.get = AsyncMock(return_value=mock_response)

            result = await c.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_unhealthy(self):
        c = FlareSolverrClient()
        with patch("httpx.AsyncClient") as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_ctx.get = AsyncMock(return_value=mock_response)

            result = await c.health_check()
            assert result is False

    @pytest.mark.asyncio
    async def test_connection_error(self):
        c = FlareSolverrClient()
        with patch("httpx.AsyncClient") as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.get = AsyncMock(side_effect=Exception("Connection refused"))

            result = await c.health_check()
            assert result is False


# ─── CloudflareBypass init ───────────────────────────────────────────────


class TestCloudflareBypassInit:
    def test_default_url(self):
        cb = CloudflareBypass()
        assert cb.flaresolverr.base_url == "http://localhost:8191"

    def test_custom_url(self):
        cb = CloudflareBypass(flaresolverr_url="http://custom:9999")
        assert cb.flaresolverr.base_url == "http://custom:9999"

    def test_default_use_cloakbrowser(self):
        cb = CloudflareBypass()
        assert cb.use_cloakbrowser is True

    def test_disable_cloakbrowser(self):
        cb = CloudflareBypass(use_cloakbrowser=False)
        assert cb.use_cloakbrowser is False

    def test_default_timeout(self):
        cb = CloudflareBypass()
        assert cb.flaresolverr.timeout == 120.0

    def test_custom_timeout(self):
        cb = CloudflareBypass(timeout=60.0)
        assert cb.flaresolverr.timeout == 60.0

    def test_flaresolverr_available_none(self):
        cb = CloudflareBypass()
        assert cb._flaresolverr_available is None


# ─── CloudflareBypass.check_flaresolverr ─────────────────────────────────


class TestCheckFlareSolverr:
    @pytest.mark.asyncio
    async def test_caches_result(self):
        cb = CloudflareBypass()
        with patch.object(cb.flaresolverr, "health_check", new_callable=AsyncMock) as mock_hc:
            mock_hc.return_value = True
            result1 = await cb.check_flaresolverr()
            result2 = await cb.check_flaresolverr()
            assert result1 is True
            assert result2 is True
            mock_hc.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_available(self):
        cb = CloudflareBypass()
        with patch.object(cb.flaresolverr, "health_check", new_callable=AsyncMock) as mock_hc:
            mock_hc.return_value = False
            result = await cb.check_flaresolverr()
            assert result is False
            assert cb._flaresolverr_available is False
