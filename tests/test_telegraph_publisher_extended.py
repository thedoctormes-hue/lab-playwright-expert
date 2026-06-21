"""
Extended tests for telegraph_publisher.py — TelegraphPublisher, TelegraphPage, etc.

Covers: dataclasses, HTML-to-nodes conversion, TelegraphPublisher methods (mocked HTTP).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lab_playwright_kit.telegraph_publisher import (
    AccountInfo,
    PublishResult,
    TelegraphError,
    TelegraphPage,
    TelegraphPublisher,
    create_telegraph_account,
    quick_publish,
)


# ─── TelegraphError Tests ────────────────────────────────────────────────────


class TestTelegraphError:
    def test_basic(self):
        err = TelegraphError("Something went wrong")
        assert str(err) == "Something went wrong"
        assert err.error_code == ""

    def test_with_code(self):
        err = TelegraphError("API error", error_code="ACCESS_DENIED")
        assert err.error_code == "ACCESS_DENIED"


# ─── TelegraphPage Tests ─────────────────────────────────────────────────────


class TestTelegraphPage:
    def test_defaults(self):
        page = TelegraphPage(path="test", url="https://telegra.ph/test", title="Test")
        assert page.path == "test"
        assert page.url == "https://telegra.ph/test"
        assert page.title == "Test"
        assert page.content == ""
        assert page.views == 0
        assert page.can_edit is False

    def test_full(self):
        page = TelegraphPage(
            path="my-page",
            url="https://telegra.ph/my-page",
            title="My Page",
            content="[]",
            author_name="Author",
            author_url="https://t.me/author",
            views=100,
            can_edit=True,
        )
        assert page.views == 100
        assert page.can_edit is True


# ─── PublishResult Tests ─────────────────────────────────────────────────────


class TestPublishResult:
    def test_success(self):
        page = TelegraphPage(path="test", url="https://telegra.ph/test", title="Test")
        result = PublishResult(success=True, page=page, elapsed_seconds=1.5)
        assert result.success is True
        assert result.page.url == "https://telegra.ph/test"

    def test_failure(self):
        result = PublishResult(success=False, error="API error", elapsed_seconds=0.5)
        assert result.success is False
        assert result.page is None
        assert result.error == "API error"

    def test_to_dict_success(self):
        page = TelegraphPage(path="test", url="https://telegra.ph/test", title="Test")
        result = PublishResult(success=True, page=page, elapsed_seconds=1.0)
        d = result.to_dict()
        assert d["success"] is True
        assert d["url"] == "https://telegra.ph/test"

    def test_to_dict_failure(self):
        result = PublishResult(success=False, error="fail")
        d = result.to_dict()
        assert d["success"] is False
        assert d["url"] == ""


# ─── AccountInfo Tests ───────────────────────────────────────────────────────


class TestAccountInfo:
    def test_defaults(self):
        info = AccountInfo()
        assert info.short_name == ""
        assert info.author_name == ""
        assert info.page_count == 0

    def test_full(self):
        info = AccountInfo(
            short_name="MyLab",
            author_name="DoctorM",
            author_url="https://t.me/doctorm",
            auth_url="https://telegra.ph/auth/xxx",
            page_count=10,
        )
        assert info.short_name == "MyLab"
        assert info.page_count == 10


# ─── TelegraphPublisher Tests ────────────────────────────────────────────────


class TestTelegraphPublisher:
    def test_init_defaults(self):
        pub = TelegraphPublisher()
        assert pub.access_token == ""
        assert pub.max_retries == 3
        assert pub.retry_delay == 1.0
        assert pub._session is None

    def test_init_with_token(self):
        pub = TelegraphPublisher(access_token="my_token", max_retries=5)
        assert pub.access_token == "my_token"
        assert pub.max_retries == 5

    @pytest.mark.asyncio
    async def test_connect(self):
        pub = TelegraphPublisher()
        await pub.connect()
        assert pub._session is not None
        await pub.close()

    @pytest.mark.asyncio
    async def test_close(self):
        pub = TelegraphPublisher()
        await pub.connect()
        await pub.close()
        assert pub._session is None

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with TelegraphPublisher() as pub:
            assert pub._session is not None

    @pytest.mark.asyncio
    async def test_request_without_session_raises(self):
        pub = TelegraphPublisher()
        with pytest.raises(RuntimeError, match="Not connected"):
            await pub._request("getAccountInfo")

    @pytest.mark.asyncio
    async def test_get_account_info(self):
        pub = TelegraphPublisher(access_token="test_token")
        await pub.connect()

        mock_resp = {
            "ok": True,
            "result": {
                "short_name": "test",
                "author_name": "Test",
                "author_url": "",
                "auth_url": "",
                "page_count": 5,
            },
        }

        with patch.object(pub._session, "post", new_callable=AsyncMock) as mock_post:
            mock_ctx = MagicMock()
            mock_ctx.__aenter__ = AsyncMock(
                return_value=MagicMock(
                    status=200,
                    json=AsyncMock(return_value=mock_resp),
                    text=AsyncMock(return_value=""),
                )
            )
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_post.return_value = mock_ctx

            info = await pub.get_account_info()
            assert info.short_name == "test"
            assert info.page_count == 5

        await pub.close()

    @pytest.mark.asyncio
    async def test_publish_success(self):
        pub = TelegraphPublisher(access_token="test_token")
        await pub.connect()

        with patch.object(pub, "create_page", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = TelegraphPage(
                path="test-page",
                url="https://telegra.ph/test-page",
                title="Test",
            )
            result = await pub.publish("Test", "<p>Content</p>")
            assert result.success is True
            assert result.page.url == "https://telegra.ph/test-page"

        await pub.close()

    @pytest.mark.asyncio
    async def test_publish_failure(self):
        pub = TelegraphPublisher(access_token="test_token")
        await pub.connect()

        with patch.object(pub, "create_page", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = TelegraphError("API error")
            result = await pub.publish("Test", "<p>Content</p>")
            assert result.success is False
            assert "API error" in result.error

        await pub.close()

    def test_html_to_nodes_json_empty(self):
        result = TelegraphPublisher._html_to_nodes_json("")
        import json

        data = json.loads(result)
        assert data == []

    def test_html_to_nodes_json_plain_text(self):
        result = TelegraphPublisher._html_to_nodes_json("Hello world")
        import json

        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["tag"] == "p"

    def test_html_to_nodes_json_with_headings(self):
        result = TelegraphPublisher._html_to_nodes_json("<h3>Title</h3><p>Text</p>")
        import json

        data = json.loads(result)
        tags = [n["tag"] for n in data]
        assert "h3" in tags

    def test_html_to_nodes_json_with_image(self):
        result = TelegraphPublisher._html_to_nodes_json('<img src="https://example.com/img.png">')
        import json

        data = json.loads(result)
        assert any(n["tag"] == "img" for n in data)

    def test_html_to_nodes_empty(self):
        result = TelegraphPublisher.html_to_nodes("")
        assert result == []

    def test_html_to_nodes_paragraph(self):
        result = TelegraphPublisher.html_to_nodes("<p>Hello</p>")
        assert len(result) == 1
        assert result[0]["tag"] == "p"
        assert result[0]["children"] == ["Hello"]

    def test_html_to_nodes_h3(self):
        result = TelegraphPublisher.html_to_nodes("<h3>Title</h3>")
        assert result[0]["tag"] == "h3"

    def test_html_to_nodes_h4(self):
        result = TelegraphPublisher.html_to_nodes("<h4>Subtitle</h4>")
        assert result[0]["tag"] == "h4"

    def test_html_to_nodes_image(self):
        result = TelegraphPublisher.html_to_nodes('<img src="https://example.com/img.png">')
        assert result[0]["tag"] == "img"
        assert result[0]["attrs"]["src"] == "https://example.com/img.png"

    def test_html_to_nodes_blockquote(self):
        result = TelegraphPublisher.html_to_nodes("<blockquote>Quote</blockquote>")
        assert result[0]["tag"] == "blockquote"

    def test_html_to_nodes_list(self):
        result = TelegraphPublisher.html_to_nodes("<ul><li>Item 1</li><li>Item 2</li></ul>")
        assert any(n["tag"] == "ul" for n in result)

    def test_html_to_nodes_ol(self):
        result = TelegraphPublisher.html_to_nodes("<ol><li>First</li></ol>")
        assert any(n["tag"] == "ol" for n in result)

    def test_html_to_nodes_fallback(self):
        """Non-HTML text should be wrapped in p."""
        result = TelegraphPublisher.html_to_nodes("Just text")
        assert len(result) == 1
        assert result[0]["tag"] == "p"
        assert result[0]["children"] == ["Just text"]


# ─── Convenience Functions Tests ─────────────────────────────────────────────


class TestConvenienceFunctions:
    @pytest.mark.asyncio
    async def test_quick_publish(self):
        with patch.object(TelegraphPublisher, "publish", new_callable=AsyncMock) as mock_pub:
            mock_pub.return_value = PublishResult(success=True)
            result = await quick_publish("Title", "<p>Content</p>", "token")
            assert isinstance(result, PublishResult)

    @pytest.mark.asyncio
    async def test_create_telegraph_account(self):
        pub = TelegraphPublisher()
        await pub.connect()

        mock_result = {"access_token": "new_token_123"}

        with patch.object(pub, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_result
            token, new_pub = await create_telegraph_account("TestLab", "Author")
            assert token == "new_token_123"
            assert new_pub.access_token == "new_token_123"

        await pub.close()
