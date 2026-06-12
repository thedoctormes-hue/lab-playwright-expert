"""
Тесты для Telegraph Publisher.

Покрывают:
- HTML → Node конвертацию
- PublishResult / TelegraphPage dataclasses
- TelegraphPublisher методы (mocked API)
- Интеграция с HypeClient
"""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from lab_playwright_kit.telegraph_publisher import (
    TelegraphPublisher,
    TelegraphPage,
    TelegraphError,
    PublishResult,
    AccountInfo,
    quick_publish,
    create_telegraph_account,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_html():
    return "<h3>Заголовок</h3><p>Параграф текста</p><p>Второй параграф</p>"


@pytest.fixture
def sample_nodes():
    return [
        {"tag": "h3", "children": ["Заголовок"]},
        {"tag": "p", "children": ["Параграф текста"]},
        {"tag": "p", "children": ["Второй параграф"]},
    ]


@pytest.fixture
def mock_page_result():
    return {
        "path": "Testovaya-statya-05-20",
        "url": "https://telegra.ph/Testovaya-statya-05-20",
        "title": "Тестовая статья",
        "author_name": "DoctorM&Ai",
        "author_url": "",
        "views": 0,
        "can_edit": True,
    }


# ─── HTML to Nodes ────────────────────────────────────────────────────────────

class TestHtmlToNodes:
    def test_simple_paragraph(self):
        html = "<p>Hello world</p>"
        nodes = TelegraphPublisher.html_to_nodes(html)
        assert len(nodes) == 1
        assert nodes[0] == {"tag": "p", "children": ["Hello world"]}

    def test_multiple_paragraphs(self):
        html = "<p>First</p><p>Second</p>"
        nodes = TelegraphPublisher.html_to_nodes(html)
        assert len(nodes) == 2
        assert nodes[0]["children"] == ["First"]
        assert nodes[1]["children"] == ["Second"]

    def test_heading_h3(self):
        html = "<h3>Заголовок</h3>"
        nodes = TelegraphPublisher.html_to_nodes(html)
        assert len(nodes) == 1
        assert nodes[0] == {"tag": "h3", "children": ["Заголовок"]}

    def test_heading_h4(self):
        html = "<h4>Подзаголовок</h4>"
        nodes = TelegraphPublisher.html_to_nodes(html)
        assert len(nodes) == 1
        assert nodes[0] == {"tag": "h4", "children": ["Подзаголовок"]}

    def test_blockquote(self):
        html = "<blockquote>Цитата</blockquote>"
        nodes = TelegraphPublisher.html_to_nodes(html)
        assert len(nodes) == 1
        assert nodes[0] == {"tag": "blockquote", "children": ["Цитата"]}

    def test_image(self):
        html = '<img src="https://example.com/image.jpg">'
        nodes = TelegraphPublisher.html_to_nodes(html)
        assert len(nodes) == 1
        assert nodes[0] == {"tag": "img", "attrs": {"src": "https://example.com/image.jpg"}}

    def test_unordered_list(self):
        html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
        nodes = TelegraphPublisher.html_to_nodes(html)
        assert len(nodes) == 1
        assert nodes[0]["tag"] == "ul"
        assert len(nodes[0]["children"]) == 2

    def test_ordered_list(self):
        html = "<ol><li>First</li><li>Second</li></ol>"
        nodes = TelegraphPublisher.html_to_nodes(html)
        assert len(nodes) == 1
        assert nodes[0]["tag"] == "ol"

    def test_empty_html(self):
        html = ""
        nodes = TelegraphPublisher.html_to_nodes(html)
        assert len(nodes) == 0

    def test_plain_text_fallback(self):
        html = "Just plain text"
        nodes = TelegraphPublisher.html_to_nodes(html)
        assert len(nodes) == 1
        assert nodes[0] == {"tag": "p", "children": ["Just plain text"]}

    def test_mixed_content(self):
        html = "<h3>Заголовок</h3><p>Текст</p><blockquote>Цитата</blockquote>"
        nodes = TelegraphPublisher.html_to_nodes(html)
        assert len(nodes) == 3
        tags = [n["tag"] for n in nodes]
        assert "h3" in tags
        assert "p" in tags
        assert "blockquote" in tags


# ─── HTML to Nodes JSON (internal) ───────────────────────────────────────────

class TestHtmlToJson:
    def test_basic_conversion(self):
        html = "<p>Hello</p>"
        result = TelegraphPublisher._html_to_nodes_json(html)
        data = json.loads(result)
        assert len(data) >= 1

    def test_empty_string(self):
        result = TelegraphPublisher._html_to_nodes_json("")
        data = json.loads(result)
        assert len(data) == 0


# ─── Dataclasses ──────────────────────────────────────────────────────────────

class TestDataclasses:
    def test_telegraph_page(self):
        page = TelegraphPage(
            path="Test-05-20",
            url="https://telegra.ph/Test-05-20",
            title="Test",
        )
        assert page.url == "https://telegra.ph/Test-05-20"
        assert page.views == 0

    def test_publish_result_success(self):
        page = TelegraphPage(path="Test", url="https://telegra.ph/Test", title="Test")
        result = PublishResult(success=True, page=page, elapsed_seconds=1.5)
        assert result.success is True
        assert result.error == ""
        d = result.to_dict()
        assert d["success"] is True
        assert d["url"] == "https://telegra.ph/Test"

    def test_publish_result_failure(self):
        result = PublishResult(success=False, error="API error")
        assert result.success is False
        d = result.to_dict()
        assert d["success"] is False
        assert d["error"] == "API error"

    def test_account_info(self):
        info = AccountInfo(short_name="LabDoctorM", page_count=5)
        assert info.short_name == "LabDoctorM"
        assert info.page_count == 5


# ─── TelegraphPublisher (mocked) ──────────────────────────────────────────────

class TestTelegraphPublisher:
    @pytest.mark.asyncio
    async def test_publish_success(self, mock_page_result):
        pub = TelegraphPublisher(access_token="test_token")
        pub._session = AsyncMock()

        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value={"ok": True, "result": mock_page_result})

        with patch.object(pub._session, "post", return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock(return_value=False),
        )):
            # Мокаем _request чтобы не делать реальные HTTP запросы
            pub._request = AsyncMock(return_value=mock_page_result)
            result = await pub.publish("Тест", "<p>Контент</p>")

        assert result.success is True
        assert result.page is not None
        assert result.page.url == "https://telegra.ph/Testovaya-statya-05-20"
        assert result.error == ""

    @pytest.mark.asyncio
    async def test_publish_error(self):
        pub = TelegraphPublisher(access_token="test_token")
        pub._request = AsyncMock(side_effect=TelegraphError("API error"))

        result = await pub.publish("Тест", "<p>Контент</p>")

        assert result.success is False
        assert result.page is None
        assert "API error" in result.error

    @pytest.mark.asyncio
    async def test_publish_no_token(self):
        pub = TelegraphPublisher(access_token="")
        pub._request = AsyncMock(side_effect=TelegraphError("No token"))

        result = await pub.publish("Тест", "<p>Контент</p>")

        assert result.success is False

    @pytest.mark.asyncio
    async def test_account_info(self):
        pub = TelegraphPublisher(access_token="test_token")
        pub._request = AsyncMock(return_value={
            "short_name": "LabDoctorM",
            "author_name": "DoctorM&Ai",
            "author_url": "",
            "auth_url": "https://telegra.ph/auth/abc",
            "page_count": 3,
        })

        info = await pub.get_account_info()
        assert info.short_name == "LabDoctorM"
        assert info.page_count == 3

    @pytest.mark.asyncio
    async def test_get_page_list(self):
        pub = TelegraphPublisher(access_token="test_token")
        pub._request = AsyncMock(return_value={
            "pages": [
                {"path": "Page-1", "url": "https://telegra.ph/Page-1", "title": "Page 1", "views": 10},
                {"path": "Page-2", "url": "https://telegra.ph/Page-2", "title": "Page 2", "views": 5},
            ]
        })

        pages = await pub.get_page_list()
        assert len(pages) == 2
        assert pages[0].title == "Page 1"
        assert pages[1].views == 5

    @pytest.mark.asyncio
    async def test_get_views(self):
        pub = TelegraphPublisher(access_token="test_token")
        pub._request = AsyncMock(return_value={"views": 42})

        views = await pub.get_views("Test-05-20")
        assert views == 42


# ─── HypeClient Telegraph Integration ─────────────────────────────────────────

class TestHypeClientTelegraph:
    @pytest.mark.asyncio
    async def test_publish_telegraph_dry_run(self):
        from lab_playwright_kit.hype_client import HypeClient

        client = HypeClient(
            base_url="http://localhost:8190",
            telegraph_token="test_token",
        )
        result = await client._publish_telegraph("Title", "<p>Content</p>", dry_run=True)

        assert result["success"] is True
        assert result["platform"] == "telegraph"
        assert result["dry_run"] is True

    @pytest.mark.asyncio
    async def test_publish_telegraph_no_token(self):
        from lab_playwright_kit.hype_client import HypeClient

        client = HypeClient(base_url="http://localhost:8190")
        result = await client._publish_telegraph("Title", "<p>Content</p>")

        assert result["success"] is False
        assert result["error"] == "NO_TELEGRAPH_TOKEN"

    @pytest.mark.asyncio
    async def test_publish_routes_to_telegraph(self):
        from lab_playwright_kit.hype_client import HypeClient

        client = HypeClient(
            base_url="http://localhost:8190",
            telegraph_token="test_token",
        )
        client._publish_telegraph = AsyncMock(return_value={
            "success": True,
            "platform": "telegraph",
            "url": "https://telegra.ph/Test",
            "message": "OK",
            "error": "",
            "elapsed_seconds": 1.0,
        })

        result = await client.publish("telegraph", "Title", "<p>Content</p>")
        assert result["success"] is True
        assert result["platform"] == "telegraph"

    @pytest.mark.asyncio
    async def test_crosspost_includes_telegraph_by_default(self):
        from lab_playwright_kit.hype_client import HypeClient, CrossPostReport

        client = HypeClient(
            base_url="http://localhost:8190",
            telegraph_token="test_token",
        )
        # Проверяем что telegraph в списке по умолчанию
        report = CrossPostReport(title="Test", platforms=["habr", "vcru", "telegraph"])
        assert "telegraph" in report.platforms


# ─── TelegraphError ───────────────────────────────────────────────────────────

class TestTelegraphError:
    def test_error_message(self):
        err = TelegraphError("Something went wrong")
        assert str(err) == "Something went wrong"
        assert err.error_code == ""

    def test_error_with_code(self):
        err = TelegraphError("Not found", error_code="NOT_FOUND")
        assert str(err) == "Not found"
        assert err.error_code == "NOT_FOUND"
