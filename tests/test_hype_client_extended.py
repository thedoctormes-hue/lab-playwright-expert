"""
Extended tests for hype_client.py — CrossPostResult, CrossPostReport, HypeClient.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lab_playwright_kit.hype_client import (
    CrossPostReport,
    CrossPostResult,
    HypeClient,
)


class TestCrossPostResult:
    def test_defaults(self):
        result = CrossPostResult()
        assert result.platform == ""
        assert result.success is False
        assert result.url == ""
        assert result.error == ""
        assert result.elapsed_seconds == 0.0

    def test_success(self):
        result = CrossPostResult(
            platform="telegram", success=True, url="https://t.me/chat/123", elapsed_seconds=1.5
        )
        assert result.success is True
        assert result.platform == "telegram"
        assert result.url == "https://t.me/chat/123"

    def test_failure(self):
        result = CrossPostResult(platform="twitter", success=False, error="Rate limited")
        assert result.success is False
        assert result.error == "Rate limited"

    def test_to_dict(self):
        result = CrossPostResult(platform="telegram", success=True, url="https://t.me/chat/123")
        d = result.to_dict()
        assert d["platform"] == "telegram"
        assert d["success"] is True
        assert d["url"] == "https://t.me/chat/123"


class TestCrossPostReport:
    def test_defaults(self):
        report = CrossPostReport()
        assert report.title == ""
        assert report.platforms == []
        assert report.results == []
        assert report.total_elapsed == 0.0

    def test_all_success(self):
        report = CrossPostReport(
            results=[
                CrossPostResult(platform="tg", success=True),
                CrossPostResult(platform="tw", success=True),
            ],
        )
        assert report.all_success is True

    def test_partial_success(self):
        report = CrossPostReport(
            results=[
                CrossPostResult(platform="tg", success=True),
                CrossPostResult(platform="tw", success=False),
            ],
        )
        assert report.all_success is False

    def test_success_count(self):
        report = CrossPostReport(
            results=[
                CrossPostResult(platform="tg", success=True),
                CrossPostResult(platform="tw", success=False),
                CrossPostResult(platform="dc", success=True),
            ],
        )
        assert report.success_count == 2
        assert report.fail_count == 1

    def test_to_dict(self):
        report = CrossPostReport(
            title="Test Post",
            results=[CrossPostResult(platform="tg", success=True)],
            total_elapsed=2.0,
        )
        d = report.to_dict()
        assert d["title"] == "Test Post"
        assert d["success_count"] == 1


class TestHypeClient:
    def test_init(self):
        client = HypeClient()
        assert client._session is None

    @pytest.mark.asyncio
    async def test_connect(self):
        client = HypeClient()
        await client.connect()
        assert client._session is not None
        await client.close()

    @pytest.mark.asyncio
    async def test_close(self):
        client = HypeClient()
        await client.connect()
        await client.close()
        assert client._session is None

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with HypeClient() as client:
            assert client._session is not None

    @pytest.mark.asyncio
    async def test_crosspost(self):
        client = HypeClient()
        await client.connect()
        with patch.object(client, "parse_url", new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = {"title": "Test", "content": "Hello"}
            with patch.object(client, "publish", new_callable=AsyncMock) as mock_publish:
                mock_publish.return_value = CrossPostResult(
                    platform="telegram", success=True, url="https://t.me/123"
                )
                report = await client.crosspost("https://example.com", platforms=["telegram"])
                assert isinstance(report, CrossPostReport)
        await client.close()

    @pytest.mark.asyncio
    async def test_crosspost_empty_platforms(self):
        client = HypeClient()
        await client.connect()
        report = await client.crosspost("https://example.com", platforms=[])
        assert isinstance(report, CrossPostReport)
        await client.close()

    @pytest.mark.asyncio
    async def test_is_healthy(self):
        client = HypeClient()
        await client.connect()
        with patch.object(client, "health", new_callable=AsyncMock, return_value={"status": "ok"}):
            result = await client.is_healthy()
            assert result is True
        await client.close()

    @pytest.mark.asyncio
    async def test_auth_login(self):
        client = HypeClient()
        await client.connect()
        with patch.object(client._session, "post", new_callable=AsyncMock) as mock_post:
            mock_ctx = MagicMock()
            mock_ctx.__aenter__ = AsyncMock(
                return_value=MagicMock(
                    status=200,
                    json=AsyncMock(return_value={"token": "abc123"}),
                    text=AsyncMock(return_value=""),
                )
            )
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_post.return_value = mock_ctx
            result = await client.auth_login("user", "pass")
            assert result is not None
        await client.close()

    @pytest.mark.asyncio
    async def test_parse_url(self):
        client = HypeClient()
        await client.connect()
        with patch.object(client._session, "get", new_callable=AsyncMock) as mock_get:
            mock_ctx = MagicMock()
            mock_ctx.__aenter__ = AsyncMock(
                return_value=MagicMock(
                    status=200,
                    text=AsyncMock(
                        return_value="<html><title>Test</title><body>Content</body></html>"
                    ),
                )
            )
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_get.return_value = mock_ctx
            result = await client.parse_url("https://example.com")
            assert isinstance(result, dict)
        await client.close()

    @pytest.mark.asyncio
    async def test_list_niches(self):
        client = HypeClient()
        await client.connect()
        with patch.object(client._session, "get", new_callable=AsyncMock) as mock_get:
            mock_ctx = MagicMock()
            mock_ctx.__aenter__ = AsyncMock(
                return_value=MagicMock(
                    status=200,
                    json=AsyncMock(return_value={"niches": [{"id": 1, "name": "tech"}]}),
                )
            )
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_get.return_value = mock_ctx
            result = await client.list_niches()
            assert isinstance(result, dict)
        await client.close()
