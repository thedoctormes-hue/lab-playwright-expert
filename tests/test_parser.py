"""
Тесты для parser.py — PageParser + ParsedContent.

Покрывает:
  - ParsedContent: создание, domain, summary()
  - PageParser: инициализация, extract_by_selector, extract_table,
    extract_emails, extract_phones, extract_structured, wait_for_content, scroll_to_bottom
"""
import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from lab_playwright_kit.parser import PageParser, ParsedContent


# ─── ParsedContent ───────────────────────────────────────────────────────────

class TestParsedContent:
    """Тесты dataclass ParsedContent."""

    def test_creation(self):
        content = ParsedContent(
            url="https://example.com/page",
            title="Test Page",
            text="Hello world",
            links=[{"text": "link1", "href": "https://example.com/1"}],
            images=["https://example.com/img.png"],
            meta={"description": "test"},
            structured={"json_ld": []},
        )
        assert content.url == "https://example.com/page"
        assert content.title == "Test Page"
        assert content.text == "Hello world"
        assert len(content.links) == 1
        assert len(content.images) == 1
        assert content.meta["description"] == "test"

    def test_domain(self):
        content = ParsedContent(url="https://example.com/path", title="", text="", links=[], images=[], meta={}, structured={})
        assert content.domain == "example.com"

    def test_domain_subdomain(self):
        content = ParsedContent(url="https://blog.example.com/post", title="", text="", links=[], images=[], meta={}, structured={})
        assert content.domain == "blog.example.com"

    def test_domain_with_port(self):
        """urlparse возвращает netloc с портом — это ожидаемое поведение."""
        content = ParsedContent(url="https://example.com:8080/path", title="", text="", links=[], images=[], meta={}, structured={})
        # urlparse возвращает "example.com:8080" для netloc
        assert "example.com" in content.domain

    def test_summary_short(self):
        """Короткий текст — без обрезки."""
        content = ParsedContent(url="", title="", text="Short text", links=[], images=[], meta={}, structured={})
        assert content.summary() == "Short text"

    def test_summary_long(self):
        """Длинный текст — обрезается."""
        text = "A" * 1000
        content = ParsedContent(url="", title="", text=text, links=[], images=[], meta={}, structured={})
        summary = content.summary(max_length=500)
        assert len(summary) < 1000
        assert "..." in summary

    def test_summary_custom_length(self):
        content = ParsedContent(url="", title="", text="A" * 200, links=[], images=[], meta={}, structured={})
        summary = content.summary(max_length=100)
        assert len(summary) <= 103  # 100 + "..."

    def test_summary_exact_length(self):
        """Текст ровно max_length — без обрезки."""
        text = "A" * 500
        content = ParsedContent(url="", title="", text=text, links=[], images=[], meta={}, structured={})
        assert content.summary(max_length=500) == text

    def test_empty_fields(self):
        content = ParsedContent(url="", title="", text="", links=[], images=[], meta={}, structured={})
        assert content.url == ""
        assert content.domain == ""


# ─── PageParser ──────────────────────────────────────────────────────────────

@pytest.fixture
def mock_page():
    """Мок Playwright Page."""
    page = AsyncMock()
    page.url = "https://example.com"
    page.title = AsyncMock(return_value="Test Page")
    page.evaluate = AsyncMock(return_value="")
    page.locator = MagicMock()
    return page


@pytest.fixture
def parser(mock_page):
    """PageParser с моком page."""
    return PageParser(mock_page)


class TestPageParserInit:
    """Тесты инициализации."""

    def test_init(self, mock_page):
        parser = PageParser(mock_page)
        assert parser.page is mock_page


class TestPageParserParse:
    """Тесты parse()."""

    @pytest.mark.asyncio
    async def test_parse_returns_parsed_content(self, parser, mock_page):
        """parse() возвращает ParsedContent."""
        mock_page.evaluate = AsyncMock(side_effect=[
            "Page text content",  # text
            [{"text": "link1", "href": "https://example.com/1"}],  # links
            ["https://example.com/img.png"],  # images
            {"description": "test"},  # meta
            [],  # json_ld
            {},  # opengraph
        ])
        result = await parser.parse()
        assert isinstance(result, ParsedContent)

    @pytest.mark.asyncio
    async def test_parse_url(self, parser, mock_page):
        """parse() берёт URL из page."""
        call_count = 0
        async def mock_evaluate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # parse() вызывает evaluate 6 раз: text, links, images, meta, json_ld, opengraph
            if call_count <= 4:
                return [] if call_count > 1 else "text"
            return {} if call_count == 6 else []
        mock_page.evaluate = mock_evaluate
        result = await parser.parse()
        assert result.url == "https://example.com"

    @pytest.mark.asyncio
    async def test_parse_title(self, parser, mock_page):
        """parse() берёт title из page."""
        call_count = 0
        async def mock_evaluate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 4:
                return [] if call_count > 1 else "text"
            return {} if call_count == 6 else []
        mock_page.evaluate = mock_evaluate
        result = await parser.parse()
        assert result.title == "Test Page"


class TestPageParserExtractBySelector:
    """Тесты extract_by_selector()."""

    @pytest.mark.asyncio
    async def test_extract_by_selector(self, parser, mock_page):
        """extract_by_selector возвращает список текстов."""
        mock_locator = AsyncMock()
        mock_locator.count = AsyncMock(return_value=2)
        mock_locator.nth = MagicMock()
        mock_nth_0 = AsyncMock()
        mock_nth_0.inner_text = AsyncMock(return_value="  Item 1  ")
        mock_nth_1 = AsyncMock()
        mock_nth_1.inner_text = AsyncMock(return_value="Item 2")
        mock_locator.nth.side_effect = [mock_nth_0, mock_nth_1]
        mock_page.locator = MagicMock(return_value=mock_locator)

        result = await parser.extract_by_selector(".item")
        assert result == ["Item 1", "Item 2"]

    @pytest.mark.asyncio
    async def test_extract_by_selector_empty(self, parser, mock_page):
        """Нет совпадений — пустой список."""
        mock_locator = AsyncMock()
        mock_locator.count = AsyncMock(return_value=0)
        mock_page.locator = MagicMock(return_value=mock_locator)

        result = await parser.extract_by_selector(".nonexistent")
        assert result == []


class TestPageParserExtractTable:
    """Тесты extract_table()."""

    @pytest.mark.asyncio
    async def test_extract_table_list(self, parser, mock_page):
        """extract_table без as_dict — list of lists."""
        mock_page.evaluate = AsyncMock(return_value=[
            ["Header1", "Header2"],
            ["Cell1", "Cell2"],
        ])
        result = await parser.extract_table("table")
        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_extract_table_dict(self, parser, mock_page):
        """extract_table с as_dict — list of dicts."""
        mock_page.evaluate = AsyncMock(return_value=[
            {"Header1": "Cell1", "Header2": "Cell2"},
        ])
        result = await parser.extract_table("table", as_dict=True)
        assert isinstance(result, list)
        assert result[0]["Header1"] == "Cell1"

    @pytest.mark.asyncio
    async def test_extract_table_empty(self, parser, mock_page):
        """Пустая таблица."""
        mock_page.evaluate = AsyncMock(return_value=[])
        result = await parser.extract_table("table")
        assert result == []


class TestPageParserExtractEmails:
    """Тесты extract_emails()."""

    @pytest.mark.asyncio
    async def test_extract_emails(self, parser, mock_page):
        """Извлечение email из текста."""
        mock_page.evaluate = AsyncMock(
            return_value="Contact us at info@example.com or support@test.org"
        )
        result = await parser.extract_emails()
        assert "info@example.com" in result
        assert "support@test.org" in result

    @pytest.mark.asyncio
    async def test_extract_emails_none(self, parser, mock_page):
        """Нет email — пустой список."""
        mock_page.evaluate = AsyncMock(return_value="No emails here")
        result = await parser.extract_emails()
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_emails_deduplicated(self, parser, mock_page):
        """Дубликаты убираются."""
        mock_page.evaluate = AsyncMock(
            return_value="same@example.com and same@example.com"
        )
        result = await parser.extract_emails()
        assert len(result) == 1


class TestPageParserExtractPhones:
    """Тесты extract_phones()."""

    @pytest.mark.asyncio
    async def test_extract_phones(self, parser, mock_page):
        """Извлечение телефонов."""
        mock_page.evaluate = AsyncMock(
            return_value="Call +7 (999) 123-45-67 or 8-999-123-45-67"
        )
        result = await parser.extract_phones()
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_extract_phones_none(self, parser, mock_page):
        """Нет телефонов — пустой список."""
        mock_page.evaluate = AsyncMock(return_value="No phones here")
        result = await parser.extract_phones()
        assert result == []


class TestPageParserExtractStructured:
    """Тесты extract_structured()."""

    @pytest.mark.asyncio
    async def test_extract_structured_simple(self, parser, mock_page):
        """Простая схема — title и description."""
        mock_locator = AsyncMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_locator.first = AsyncMock()
        mock_locator.first.inner_text = AsyncMock(return_value="  Page Title  ")
        mock_page.locator = MagicMock(return_value=mock_locator)

        schema = {"title": "h1"}
        result = await parser.extract_structured(schema)
        assert result["title"] == "Page Title"

    @pytest.mark.asyncio
    async def test_extract_structured_not_found(self, parser, mock_page):
        """Элемент не найден — None."""
        mock_locator = AsyncMock()
        mock_locator.count = AsyncMock(return_value=0)
        mock_page.locator = MagicMock(return_value=mock_locator)

        schema = {"title": "h1"}
        result = await parser.extract_structured(schema)
        assert result["title"] is None

    @pytest.mark.asyncio
    async def test_extract_structured_with_list(self, parser, mock_page):
        """list: префикс — извлечь все совпадения."""
        mock_locator = AsyncMock()
        mock_locator.count = AsyncMock(return_value=2)
        mock_nth_0 = AsyncMock()
        mock_nth_0.inner_text = AsyncMock(return_value="Tag1")
        mock_nth_1 = AsyncMock()
        mock_nth_1.inner_text = AsyncMock(return_value="Tag2")
        mock_locator.nth = MagicMock(side_effect=[mock_nth_0, mock_nth_1])
        mock_page.locator = MagicMock(return_value=mock_locator)

        schema = {"tags": "list:.tag"}
        result = await parser.extract_structured(schema)
        assert result["tags"] == ["Tag1", "Tag2"]

    @pytest.mark.asyncio
    async def test_extract_structured_with_attribute(self, parser, mock_page):
        """@attr — извлечь атрибут."""
        mock_locator = AsyncMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_locator.first = AsyncMock()
        mock_locator.first.get_attribute = AsyncMock(return_value="https://example.com/img.png")
        mock_page.locator = MagicMock(return_value=mock_locator)

        schema = {"image": "img.main@src"}
        result = await parser.extract_structured(schema)
        assert result["image"] == "https://example.com/img.png"

    @pytest.mark.asyncio
    async def test_extract_structured_multiple_fields(self, parser, mock_page):
        """Несколько полей."""
        mock_locator = AsyncMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_locator.first = AsyncMock()
        mock_locator.first.inner_text = AsyncMock(return_value="Value")
        mock_page.locator = MagicMock(return_value=mock_locator)

        schema = {"title": "h1", "desc": ".description"}
        result = await parser.extract_structured(schema)
        assert "title" in result
        assert "desc" in result


class TestPageParserWaitForContent:
    """Тесты wait_for_content()."""

    @pytest.mark.asyncio
    async def test_wait_for_content_success(self, parser, mock_page):
        """Элемент появился — True."""
        mock_page.wait_for_selector = AsyncMock()
        result = await parser.wait_for_content(".content")
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_content_timeout(self, parser, mock_page):
        """Таймаут — False."""
        mock_page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))
        result = await parser.wait_for_content(".content", timeout=100)
        assert result is False


class TestPageParserScrollToBottom:
    """Тесты scroll_to_bottom()."""

    @pytest.mark.asyncio
    async def test_scroll_to_bottom(self, parser, mock_page):
        """scroll_to_bottom возвращает количество скроллов."""
        mock_page.evaluate = AsyncMock(return_value=5)
        result = await parser.scroll_to_bottom()
        assert result == 5

    @pytest.mark.asyncio
    async def test_scroll_to_bottom_zero(self, parser, mock_page):
        """Нет скролла — 0."""
        mock_page.evaluate = AsyncMock(return_value=0)
        result = await parser.scroll_to_bottom()
        assert result == 0
