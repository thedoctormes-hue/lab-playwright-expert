"""
Tests for Hype Pilot Client.
Covers: HypeClient, CrossPostResult, CrossPostReport, convenience functions.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from lab_playwright_kit.hype_client import (
    CrossPostReport,
    CrossPostResult,
    HypeClient,
    check_api,
    quick_crosspost,
)


# ─── CrossPostResult Tests ───────────────────────────────────────────────────

class TestCrossPostResult:
    def test_defaults(self):
        r = CrossPostResult(platform="habr", success=True)
        assert r.platform == "habr"
        assert r.success is True
        assert r.url == ""
        assert r.error == ""
        assert r.elapsed_seconds == 0.0

    def test_with_data(self):
        r = CrossPostResult(
            platform="vcru",
            success=False,
            error="NOT_AUTHENTICATED",
            elapsed_seconds=3.5,
        )
        assert r.success is False
        assert r.error == "NOT_AUTHENTICATED"
        assert r.elapsed_seconds == 3.5


# ─── CrossPostReport Tests ───────────────────────────────────────────────────

class TestCrossPostReport:
    def test_empty(self):
        r = CrossPostReport(title="Test", platforms=[])
        assert r.all_success is False
        assert r.success_count == 0
        assert r.failed_platforms == []

    def test_all_success(self):
        r = CrossPostReport(
            title="Test",
            platforms=["habr", "vcru"],
            results=[
                CrossPostResult(platform="habr", success=True, url="https://habr.com/1"),
                CrossPostResult(platform="vcru", success=True, url="https://vc.ru/1"),
            ],
        )
        assert r.all_success is True
        assert r.success_count == 2
        assert r.failed_platforms == []

    def test_partial_success(self):
        r = CrossPostReport(
            title="Test",
            platforms=["habr", "vcru"],
            results=[
                CrossPostResult(platform="habr", success=True, url="https://habr.com/1"),
                CrossPostResult(platform="vcru", success=False, error="NOT_AUTH"),
            ],
        )
        assert r.all_success is False
        assert r.success_count == 1
        assert r.failed_platforms == ["vcru"]

    def test_all_failed(self):
        r = CrossPostReport(
            title="Test",
            platforms=["habr", "vcru"],
            results=[
                CrossPostResult(platform="habr", success=False, error="timeout"),
                CrossPostResult(platform="vcru", success=False, error="NOT_AUTH"),
            ],
        )
        assert r.all_success is False
        assert r.success_count == 0
        assert set(r.failed_platforms) == {"habr", "vcru"}

    def test_to_dict(self):
        r = CrossPostReport(
            title="Test",
            platforms=["habr"],
            results=[
                CrossPostResult(platform="habr", success=True, url="https://habr.com/1", elapsed_seconds=5.123),
            ],
            total_elapsed=5.5,
        )
        d = r.to_dict()
        assert d["title"] == "Test"
        assert d["success_count"] == 1
        assert d["all_success"] is True
        assert d["total_elapsed"] == 5.5
        assert d["results"][0]["platform"] == "habr"
        assert d["results"][0]["elapsed"] == 5.12


# ─── HypeClient Tests ───────────────────────────────────────────────

def _make_mock_session(json_data, status=200):
    """Создать мок-сессию aiohttp с заданным ответом."""
    mock_resp = MagicMock()
    mock_resp.json = AsyncMock(return_value=json_data)
    mock_resp.status = status
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.request = MagicMock(return_value=mock_resp)
    mock_session.close = AsyncMock()
    return mock_session, mock_resp


class TestHypeClient:
    def test_init_defaults(self):
        c = HypeClient()
        assert c.base_url == "http://localhost:8190"
        assert c.max_retries == 3
        assert c.retry_delay == 2.0
        assert c._session is None

    def test_init_custom(self):
        c = HypeClient(base_url="http://api.example.com:8080/", timeout=60.0, max_retries=5)
        assert c.base_url == "http://api.example.com:8080"
        assert c.max_retries == 5

    @pytest.mark.asyncio
    async def test_context_manager(self):
        client = HypeClient()
        mock_session = MagicMock()
        mock_session.close = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            async with client as c:
                assert c._session is not None
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_connected_raises(self):
        client = HypeClient()
        with pytest.raises(RuntimeError, match="not connected"):
            await client.health()

    @pytest.mark.asyncio
    async def test_health(self):
        mock_session, _ = _make_mock_session({"status": "healthy", "version": "2.0.0"})
        client = HypeClient()
        client._session = mock_session

        result = await client.health()
        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_is_healthy_true(self):
        mock_session, _ = _make_mock_session({"status": "healthy"})
        client = HypeClient()
        client._session = mock_session

        assert await client.is_healthy() is True

    @pytest.mark.asyncio
    async def test_is_healthy_false(self):
        mock_session, _ = _make_mock_session({"status": "error"})
        client = HypeClient()
        client._session = mock_session

        assert await client.is_healthy() is False

    @pytest.mark.asyncio
    async def test_is_healthy_exception(self):
        mock_resp = MagicMock()
        mock_resp.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("Connection refused"))
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.request = MagicMock(return_value=mock_resp)

        client = HypeClient()
        client._session = mock_session

        assert await client.is_healthy() is False

    @pytest.mark.asyncio
    async def test_status(self):
        mock_session, _ = _make_mock_session({
            "status": "running",
            "browser_active": True,
            "active_sessions": 2,
            "available_niches": 10,
            "available_presets": 5,
        })
        client = HypeClient()
        client._session = mock_session

        result = await client.status()
        assert result["status"] == "running"
        assert result["browser_active"] is True

    @pytest.mark.asyncio
    async def test_parse_url(self):
        mock_session, _ = _make_mock_session({"success": True, "url": "https://habr.com/1", "data": {}})
        client = HypeClient()
        client._session = mock_session

        result = await client.parse_url("https://habr.com/ru/articles/123/", niche="habr")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_parse_batch(self):
        mock_session, _ = _make_mock_session({"total": 2, "results": []})
        client = HypeClient()
        client._session = mock_session

        result = await client.parse_batch(["https://a.com", "https://b.com"], niche="habr")
        assert result["total"] == 2

    @pytest.mark.asyncio
    async def test_list_niches(self):
        mock_session, _ = _make_mock_session([{"name": "habr"}, {"name": "vcru"}])
        client = HypeClient()
        client._session = mock_session

        result = await client.list_niches()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_auth_login(self):
        mock_session, _ = _make_mock_session({"success": True, "status": "success"})
        client = HypeClient()
        client._session = mock_session

        result = await client.auth_login("habr", "user@test.ru", "pass123")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_auth_check(self):
        mock_session, _ = _make_mock_session({"success": True, "status": "authenticated"})
        client = HypeClient()
        client._session = mock_session

        result = await client.auth_check("habr", "user@test.ru")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_auth_2fa(self):
        mock_session, _ = _make_mock_session({"success": True, "status": "success"})
        client = HypeClient()
        client._session = mock_session

        result = await client.auth_2fa("twitter", "user", "123456")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_auth_list_sessions(self):
        mock_session, _ = _make_mock_session({"sessions": ["habr_user1"], "total": 1})
        client = HypeClient()
        client._session = mock_session

        result = await client.auth_list_sessions()
        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_auth_delete_session(self):
        mock_session, _ = _make_mock_session({"message": "Session deleted"})
        client = HypeClient()
        client._session = mock_session

        result = await client.auth_delete_session("habr", "user@test.ru")
        assert "message" in result

    @pytest.mark.asyncio
    async def test_crosspost(self):
        """Интеграционный тест crosspost через POST /api/v1/publish."""
        publish_resp = MagicMock()
        publish_resp.json = AsyncMock(return_value={
            "success": True, "url": "https://habr.com/1", "error": "",
        })
        publish_resp.status = 200
        publish_resp.__aenter__ = AsyncMock(return_value=publish_resp)
        publish_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.request = MagicMock(return_value=publish_resp)

        client = HypeClient()
        client._session = mock_session

        report = await client.crosspost("Title", "Content", ["habr"])
        assert report.success_count == 1
        assert report.all_success is True

    @pytest.mark.asyncio
    async def test_crosspost_not_authenticated(self):
        """CrossPost с истёкшей авторизацией."""
        publish_resp = MagicMock()
        publish_resp.json = AsyncMock(return_value={
            "success": False, "url": "", "error": "NOT_AUTHENTICATED",
        })
        publish_resp.status = 200
        publish_resp.__aenter__ = AsyncMock(return_value=publish_resp)
        publish_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.request = MagicMock(return_value=publish_resp)

        client = HypeClient()
        client._session = mock_session

        report = await client.crosspost("Title", "Content", ["habr"])
        assert report.success_count == 0
        assert report.failed_platforms == ["habr"]

    @pytest.mark.asyncio
    async def test_crosspost_default_platforms(self):
        """CrossPost с платформами по умолчанию (habr, vcru, telegraph)."""
        publish_resp = MagicMock()
        publish_resp.json = AsyncMock(return_value={
            "success": True, "url": "https://example.com", "error": "",
        })
        publish_resp.status = 200
        publish_resp.__aenter__ = AsyncMock(return_value=publish_resp)
        publish_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.request = MagicMock(return_value=publish_resp)

        client = HypeClient()
        client._session = mock_session

        report = await client.crosspost("Title", "Content")
        assert len(report.results) == 3
        assert [r.platform for r in report.results] == ["habr", "vcru", "telegraph"]

    def test_get_publish_url(self):
        assert HypeClient._get_publish_url("habr") == "https://habr.com/ru/articles/draft/"
        assert HypeClient._get_publish_url("vcru") == "https://vc.ru/write"
        assert HypeClient._get_publish_url("tenchat") == "https://tenchat.ru/post/new"
        assert HypeClient._get_publish_url("unknown") == ""

    @pytest.mark.asyncio
    async def test_publish(self):
        """Тест прямого вызова publish через POST /api/v1/publish."""
        publish_resp = MagicMock()
        publish_resp.json = AsyncMock(return_value={
            "success": True, "platform": "habr",
            "url": "https://habr.com/1", "message": "Published",
            "error": "", "elapsed_seconds": 5.0,
        })
        publish_resp.status = 200
        publish_resp.__aenter__ = AsyncMock(return_value=publish_resp)
        publish_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.request = MagicMock(return_value=publish_resp)

        client = HypeClient()
        client._session = mock_session

        result = await client.publish("habr", "Title", "Content")
        assert result["success"] is True
        assert result["platform"] == "habr"
        assert result["url"] == "https://habr.com/1"

    @pytest.mark.asyncio
    async def test_publish_dry_run(self):
        """Тест publish с dry_run=True."""
        publish_resp = MagicMock()
        publish_resp.json = AsyncMock(return_value={
            "success": True, "platform": "vcru",
            "url": "", "message": "Dry run — auth OK",
            "error": "", "elapsed_seconds": 1.0,
        })
        publish_resp.status = 200
        publish_resp.__aenter__ = AsyncMock(return_value=publish_resp)
        publish_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.request = MagicMock(return_value=publish_resp)

        client = HypeClient()
        client._session = mock_session

        result = await client.publish("vcru", "Title", "Content", dry_run=True)
        assert result["success"] is True


# ─── Convenience Functions Tests ──────────────────────────────────────────────

class TestConvenienceFunctions:
    @pytest.mark.asyncio
    async def test_check_api_success(self):
        mock_session = MagicMock()
        mock_session.close = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.json = AsyncMock(return_value={"status": "healthy"})
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session.request = MagicMock(return_value=mock_resp)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await check_api()
            assert result is True

    @pytest.mark.asyncio
    async def test_check_api_failure(self):
        mock_session = MagicMock()
        mock_session.close = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("fail"))
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session.request = MagicMock(return_value=mock_resp)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await check_api()
            assert result is False

    @pytest.mark.asyncio
    async def test_quick_crosspost(self):
        mock_report = CrossPostReport(
            title="Test",
            platforms=["habr"],
            results=[CrossPostResult(platform="habr", success=True, url="https://habr.com/1")],
        )

        mock_session = MagicMock()
        mock_session.close = AsyncMock()

        auth_resp = MagicMock()
        auth_resp.json = AsyncMock(return_value={"success": True})
        auth_resp.status = 200
        auth_resp.__aenter__ = AsyncMock(return_value=auth_resp)
        auth_resp.__aexit__ = AsyncMock(return_value=False)

        parse_resp = MagicMock()
        parse_resp.json = AsyncMock(return_value={"success": True, "url": "https://habr.com/1"})
        parse_resp.status = 200
        parse_resp.__aenter__ = AsyncMock(return_value=parse_resp)
        parse_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session.request = MagicMock(side_effect=[auth_resp, parse_resp])

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await quick_crosspost("Title", "Content", ["habr"])
            assert result.all_success is True
