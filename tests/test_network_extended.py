"""
Расширенные тесты для Network Interceptor.

Покрывает:
  - NetworkInterceptor.attach/detach
  - NetworkInterceptor._on_request/_on_response
  - NetworkInterceptor.wait_for_api
  - NetworkInterceptor.intercept_and_block
  - NetworkInterceptor.mock_response
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# Создаём event loop для фикстур (один на все тесты)
_loop = asyncio.new_event_loop()

import pytest

from lab_playwright_kit.network import (
    CapturedRequest,
    NetworkInterceptor,
    NetworkLog,
)


# ─── CapturedRequest ─────────────────────────────────────────────────────────


class TestCapturedRequestExtended:
    def test_all_fields(self):
        req = CapturedRequest(
            url="https://api.example.com/data",
            method="POST",
            headers={"Authorization": "Bearer token"},
            post_data='{"key": "value"}',
            resource_type="xhr",
            response_status=201,
            response_body='{"id": 123}',
        )
        assert req.url == "https://api.example.com/data"
        assert req.method == "POST"
        assert req.post_data == '{"key": "value"}'
        assert req.response_status == 201
        assert req.response_body == '{"id": 123}'


# ─── NetworkLog ──────────────────────────────────────────────────────────────


class TestNetworkLogExtended:
    def test_filter_by_domain_multiple_matches(self):
        log = NetworkLog()
        log.requests = [
            CapturedRequest(
                url="https://a.com/1", method="GET", headers={}, post_data=None, resource_type="xhr"
            ),
            CapturedRequest(
                url="https://a.com/2",
                method="POST",
                headers={},
                post_data=None,
                resource_type="xhr",
            ),
            CapturedRequest(
                url="https://b.com/1", method="GET", headers={}, post_data=None, resource_type="xhr"
            ),
        ]
        filtered = log.filter_by_domain("a.com")
        assert len(filtered) == 2

    def test_filter_by_type_multiple(self):
        log = NetworkLog()
        log.requests = [
            CapturedRequest(
                url="https://a.com", method="GET", headers={}, post_data=None, resource_type="xhr"
            ),
            CapturedRequest(
                url="https://b.com", method="GET", headers={}, post_data=None, resource_type="fetch"
            ),
            CapturedRequest(
                url="https://c.com", method="GET", headers={}, post_data=None, resource_type="xhr"
            ),
        ]
        assert len(log.filter_by_type("xhr")) == 2
        assert len(log.filter_by_type("fetch")) == 1

    def test_get_api_calls_mixed(self):
        log = NetworkLog()
        log.requests = [
            CapturedRequest(
                url="https://a.com/api",
                method="GET",
                headers={},
                post_data=None,
                resource_type="xhr",
            ),
            CapturedRequest(
                url="https://b.com/fetch",
                method="POST",
                headers={},
                post_data=None,
                resource_type="fetch",
            ),
            CapturedRequest(
                url="https://c.com/page",
                method="GET",
                headers={},
                post_data=None,
                resource_type="document",
            ),
            CapturedRequest(
                url="https://d.com/style.css",
                method="GET",
                headers={},
                post_data=None,
                resource_type="stylesheet",
            ),
            CapturedRequest(
                url="https://e.com/script.js",
                method="GET",
                headers={},
                post_data=None,
                resource_type="script",
            ),
        ]
        api_calls = log.get_api_calls()
        assert len(api_calls) == 2
        assert all(r.resource_type in ("xhr", "fetch") for r in api_calls)

    def test_to_dict_with_requests(self):
        log = NetworkLog()
        log.requests = [
            CapturedRequest(
                url="https://a.com",
                method="GET",
                headers={},
                post_data=None,
                resource_type="xhr",
                response_status=200,
            ),
        ]
        d = log.to_dict()
        assert d["total"] == 1
        assert d["requests"][0]["url"] == "https://a.com"
        assert d["requests"][0]["method"] == "GET"
        assert d["requests"][0]["status"] == 200
        assert d["requests"][0]["type"] == "xhr"


# ─── NetworkInterceptor ─────────────────────────────────────────────────────


class TestNetworkInterceptor:
    @pytest.fixture
    def mock_page(self):
        """Мок Playwright Page с event listeners."""
        page = MagicMock()
        page.on = MagicMock()
        page.remove_listener = MagicMock()
        page.loop = MagicMock()
        page.loop.call_soon_threadsafe = MagicMock()
        page.loop.create_future = MagicMock(return_value=_loop.create_future())
        page.route = AsyncMock()
        return page

    @pytest.fixture
    def interceptor(self, mock_page):
        return NetworkInterceptor(mock_page)

    def test_init(self, interceptor, mock_page):
        assert interceptor.page is mock_page
        assert isinstance(interceptor.log, NetworkLog)
        assert len(interceptor.log.requests) == 0

    def test_attach(self, interceptor, mock_page):
        interceptor.attach()
        # Должен вызвать page.on для request и response
        assert mock_page.on.call_count == 2

    def test_detach(self, interceptor, mock_page):
        interceptor.attach()
        interceptor.detach()
        assert mock_page.remove_listener.call_count == 2

    @pytest.mark.asyncio
    async def test_on_request(self, interceptor):
        mock_request = MagicMock()
        mock_request.url = "https://api.example.com/data"
        mock_request.method = "POST"
        mock_request.all_headers = AsyncMock(return_value={"Content-Type": "application/json"})
        mock_request.post_data = '{"key": "value"}'
        mock_request.resource_type = "xhr"

        await interceptor._on_request(mock_request)

        assert len(interceptor.log.requests) == 1
        req = interceptor.log.requests[0]
        assert req.url == "https://api.example.com/data"
        assert req.method == "POST"
        assert req.resource_type == "xhr"

    @pytest.mark.asyncio
    async def test_on_response(self, interceptor):
        # Сначала добавляем запрос
        mock_request = MagicMock()
        mock_request.url = "https://api.example.com/data"
        mock_request.method = "GET"
        mock_request.all_headers = AsyncMock(return_value={})
        mock_request.post_data = None
        mock_request.resource_type = "xhr"

        await interceptor._on_request(mock_request)

        # Теперь ответ
        mock_response = MagicMock()
        mock_response.url = "https://api.example.com/data"
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"result": "ok"}')

        await interceptor._on_response(mock_response)

        req = interceptor.log.requests[0]
        assert req.response_status == 200
        assert req.response_body == '{"result": "ok"}'

    @pytest.mark.asyncio
    async def test_on_response_no_matching_request(self, interceptor):
        """Ответ без соответствующего запроса — не должен падать."""
        mock_response = MagicMock()
        mock_response.url = "https://unknown.com/api"
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="body")

        await interceptor._on_response(mock_response)
        # Не добавилось ничего
        assert len(interceptor.log.requests) == 0

    @pytest.mark.asyncio
    async def test_intercept_and_block(self, interceptor, mock_page):
        await interceptor.intercept_and_block(["*.css", "*.jpg"])
        assert mock_page.route.call_count == 2

    @pytest.mark.asyncio
    async def test_mock_response(self, interceptor, mock_page):
        await interceptor.mock_response(
            "https://api.example.com/data",
            body='{"mocked": true}',
            status=200,
        )
        mock_page.route.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_for_api_timeout(self, interceptor, mock_page):
        """wait_for_api с таймаутом — возвращает None."""
        with patch("lab_playwright_kit.network.asyncio.wait_for", side_effect=asyncio.TimeoutError):
            result = await interceptor.wait_for_api("https://api.example.com/data", timeout=100)
        assert result is None

    @pytest.mark.asyncio
    async def test_multiple_requests(self, interceptor):
        """Несколько запросов в логе."""
        for i in range(5):
            mock_request = MagicMock()
            mock_request.url = f"https://api.example.com/{i}"
            mock_request.method = "GET"
            mock_request.all_headers = AsyncMock(return_value={})
            mock_request.post_data = None
            mock_request.resource_type = "xhr"
            await interceptor._on_request(mock_request)

        assert len(interceptor.log.requests) == 5
        assert interceptor.log.filter_by_type("xhr") == interceptor.log.requests
