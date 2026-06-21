"""
Tests for CloudflareBypass — обход Cloudflare challenges.

Run: pytest tests/test_cloudflare_bypass.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lab_playwright_kit.cloudflare_bypass import (
    BypassResult,
    CloudflareBypass,
    FlareSolverrClient,
)


# ─── BypassResult ────────────────────────────────────────────────────────────


class TestBypassResult:
    def test_default_values(self):
        r = BypassResult()
        assert r.success is False
        assert r.cookies == {}
        assert r.user_agent == ""
        assert r.method == "none"
        assert r.error == ""

    def test_to_dict(self):
        r = BypassResult(
            success=True,
            cookies={"a": "1", "b": "2"},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            elapsed_seconds=1.5,
            method="flaresolverr",
        )
        d = r.to_dict()
        assert d["success"] is True
        assert d["cookies_count"] == 2
        assert d["method"] == "flaresolverr"
        assert d["user_agent"].startswith("Mozilla/5.0")
        assert d["user_agent"] == "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"[:50]

    def test_to_dict_empty_ua(self):
        r = BypassResult(success=True, user_agent="")
        d = r.to_dict()
        assert d["user_agent"] == ""

    def test_to_dict_short_ua(self):
        r = BypassResult(success=True, user_agent="Short")
        d = r.to_dict()
        assert d["user_agent"] == "Short"


# ─── FlareSolverrClient ──────────────────────────────────────────────────────


class TestFlareSolverrClient:
    def test_default_init(self):
        c = FlareSolverrClient()
        assert c.base_url == "http://localhost:8191"
        assert c.timeout == 120.0
        assert c.max_retries == 3

    def test_custom_init(self):
        c = FlareSolverrClient(base_url="http://custom:8200/", timeout=60.0, max_retries=5)
        assert c.base_url == "http://custom:8200"
        assert c.timeout == 60.0
        assert c.max_retries == 5

    def test_url_strip_trailing_slash(self):
        c = FlareSolverrClient(base_url="http://example.com/")
        assert c.base_url == "http://example.com"

    @pytest.mark.anyio
    async def test_health_check_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_instance

            c = FlareSolverrClient()
            result = await c.health_check()
            assert result is True

    @pytest.mark.anyio
    async def test_health_check_failure(self):
        mock_response = MagicMock()
        mock_response.status_code = 503

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_instance

            c = FlareSolverrClient()
            result = await c.health_check()
            assert result is False

    @pytest.mark.anyio
    async def test_health_check_exception(self):
        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(side_effect=Exception("refused"))
            MockClient.return_value = mock_instance

            c = FlareSolverrClient()
            result = await c.health_check()
            assert result is False


class TestFlareSolverrSolve:
    """Тесты FlareSolverrClient.solve()."""

    @pytest.mark.anyio
    async def test_solve_success(self):
        """Успешное решение challenge."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "solution": {
                "status": 200,
                "cookies": [
                    {"name": "cf_clearance", "value": "abc123"},
                ],
                "userAgent": "Mozilla/5.0",
                "response": "<html>OK</html>",
            }
        }

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_instance

            c = FlareSolverrClient()
            result = await c.solve("https://example.com")

            assert result.success is True
            assert result.cookies == {"cf_clearance": "abc123"}
            assert result.method == "flaresolverr"
            assert result.elapsed_seconds > 0

    @pytest.mark.anyio
    async def test_solve_non_200_status(self):
        """Решение вернуло ошибку — метод max_retries, итоговый fail."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "solution": {
                "status": 500,
                "message": "challenge not solved",
            }
        }

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_instance

            c = FlareSolverrClient(max_retries=2)
            result = await c.solve("https://example.com")

            assert result.success is False
            assert result.method == "flaresolverr"
            assert "Max retries" in result.error

    @pytest.mark.anyio
    async def test_solve_timeout_retry(self):
        """Таймаут — retry, затем успех."""
        mock_fail = MagicMock()
        mock_fail.status_code = 200
        mock_fail.json.return_value = {"solution": {"status": 500}}

        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {
            "solution": {
                "status": 200,
                "cookies": [{"name": "a", "value": "1"}],
            }
        }

        with (
            patch("httpx.AsyncClient") as MockClient,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(side_effect=[mock_fail, mock_ok])
            MockClient.return_value = mock_instance

            c = FlareSolverrClient(max_retries=2)
            result = await c.solve("https://example.com")

            assert result.success is True
            assert result.cookies == {"a": "1"}

    @pytest.mark.anyio
    async def test_solve_with_cookies(self):
        """Передача cookies в payload."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"solution": {"status": 200, "cookies": []}}

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_instance

            c = FlareSolverrClient()
            await c.solve("https://example.com", cookies={"session": "xyz"})

            call_args = mock_instance.post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            cookies_list = payload.get("cookies", [])
            assert {"name": "session", "value": "xyz"} in cookies_list

    @pytest.mark.anyio
    async def test_solve_with_proxy(self):
        """Передача proxy в payload."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"solution": {"status": 200, "cookies": []}}

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_instance

            c = FlareSolverrClient()
            await c.solve("https://example.com", proxy="http://proxy:8080")

            call_args = mock_instance.post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            assert payload.get("proxy") == {"url": "http://proxy:8080"}


class TestFlareSolverrSolvePost:
    """Тесты FlareSolverrClient.solve_post()."""

    @pytest.mark.anyio
    async def test_solve_post_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "solution": {
                "status": 200,
                "cookies": [{"name": "sid", "value": "sess1"}],
            }
        }

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_instance

            c = FlareSolverrClient()
            result = await c.solve_post("https://example.com/form", post_data={"key": "val"})

            assert result.success is True
            assert result.cookies == {"sid": "sess1"}

    @pytest.mark.anyio
    async def test_solve_post_with_data(self):
        """postData формируется корректно."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"solution": {"status": 200, "cookies": []}}

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_instance

            c = FlareSolverrClient()
            await c.solve_post("https://example.com", post_data={"a": "1", "b": "2"})

            call_args = mock_instance.post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            assert "postData" in payload
            assert "a=1" in payload["postData"]

    @pytest.mark.anyio
    async def test_solve_post_failure(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"solution": {"status": 500, "message": "internal error"}}

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_instance

            c = FlareSolverrClient()
            result = await c.solve_post("https://example.com")

            assert result.success is False
            assert "POST request failed" in result.error


# ─── CloudflareBypass ────────────────────────────────────────────────────────


class TestCloudflareBypass:
    def test_default_init(self):
        b = CloudflareBypass()
        assert b.flaresolverr is not None
        assert b.use_cloakbrowser is True
        assert b._flaresolverr_available is None

    def test_custom_init(self):
        b = CloudflareBypass(
            flaresolverr_url="http://other:8200",
            use_cloakbrowser=False,
            timeout=60.0,
        )
        assert b.flaresolverr.base_url == "http://other:8200"
        assert b.use_cloakbrowser is False

    @pytest.mark.anyio
    async def test_check_flaresolverr_available(self):
        mock_health = AsyncMock(return_value=True)
        b = CloudflareBypass()
        b.flaresolverr.health_check = mock_health

        result = await b.check_flaresolverr()
        assert result is True
        assert b._flaresolverr_available is True

    @pytest.mark.anyio
    async def test_check_flaresolverr_not_available(self):
        mock_health = AsyncMock(return_value=False)
        b = CloudflareBypass()
        b.flaresolverr.health_check = mock_health

        result = await b.check_flaresolverr()
        assert result is False
        assert b._flaresolverr_available is False

    @pytest.mark.anyio
    async def test_check_flaresolverr_caches(self):
        """Повторный вызов не ходит в сеть."""
        mock_health = AsyncMock(return_value=True)
        b = CloudflareBypass()
        b.flaresolverr.health_check = mock_health
        b._flaresolverr_available = True

        result = await b.check_flaresolverr()
        assert result is True
        mock_health.assert_not_called()

    @pytest.mark.anyio
    async def test_solve_via_flaresolverr_success(self):
        """FlareSolverr доступен и решает успешно."""
        b = CloudflareBypass()
        b._flaresolverr_available = True
        b.flaresolverr.solve = AsyncMock(
            return_value=BypassResult(
                success=True,
                cookies={"cf": "clear"},
                method="flaresolverr",
            )
        )

        result = await b.solve("https://example.com")
        assert result.success is True
        assert result.method == "flaresolverr"

    @pytest.mark.anyio
    async def test_solve_fallback_to_direct(self):
        """FlareSolverr недоступен — fallback на direct request."""
        b = CloudflareBypass()
        b._flaresolverr_available = False

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.cookies = MagicMock()
            mock_resp.cookies.jar = []
            mock_resp.text = "OK"
            mock_instance.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value = mock_instance

            result = await b.solve("https://example.com")
            assert result.method == "direct"

    @pytest.mark.anyio
    async def test_solve_kwargs_forwarded(self):
        """kwargs передаются в FlareSolverr.solve()."""
        b = CloudflareBypass()
        b._flaresolverr_available = True
        b.flaresolverr.solve = AsyncMock(
            return_value=BypassResult(success=True, method="flaresolverr")
        )

        await b.solve("https://example.com", cookies={"s": "1"}, proxy="http://p:80")
        call_kwargs = b.flaresolverr.solve.call_args.kwargs
        assert call_kwargs.get("cookies") == {"s": "1"}
        assert call_kwargs.get("proxy") == "http://p:80"
