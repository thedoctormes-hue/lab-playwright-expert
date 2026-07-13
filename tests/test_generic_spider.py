"""Тесты GenericSpider — happy path + error path."""

from __future__ import annotations

import pytest
from scrapy.http import HtmlResponse, Request

from lab_playwright_kit.scrapy_engine.spiders.generic_spider import GenericSpider


@pytest.fixture
def spider():
    return GenericSpider(url="https://example.com", max_pages=10, max_depth=2)


def _make_response(url, body, meta=None):
    """Создать HtmlResponse с request.meta (нужно для response.meta)."""
    request = Request(url=url, meta=meta or {})
    return HtmlResponse(url=url, body=body, request=request)


class TestGenericSpiderParse:
    """Happy path: парсинг валидной HTML-страницы."""

    def test_parse_returns_item(self, spider):
        html = "<html><head><title>Test Page</title></head><body><p>Hello World</p></body></html>"
        response = _make_response("https://example.com", html.encode())
        results = list(spider.parse(response))
        assert len(results) >= 1
        item = results[0]
        assert item["url"] == "https://example.com"
        assert item["title"] == "Test Page"
        assert "Hello World" in item["text"]

    def test_parse_extracts_meta(self, spider):
        html = (
            b'<html><head><title>Meta Test</title>'
            b'<meta name="description" content="A test page">'
            b'<meta property="og:title" content="OG Title">'
            b'</head><body><p>Content</p></body></html>'
        )
        response = _make_response("https://example.com", html)
        results = list(spider.parse(response))
        assert len(results) >= 1
        meta = results[0]["meta"]
        assert meta.get("description") == "A test page"
        assert meta.get("og:title") == "OG Title"

    def test_parse_extracts_links(self, spider):
        html = (
            b'<html><head><title>Links</title></head><body>'
            b'<a href="/page1">Page 1</a>'
            b'<a href="/page2">Page 2</a>'
            b'</body></html>'
        )
        response = _make_response("https://example.com", html)
        results = list(spider.parse(response))
        assert len(results) >= 1
        links = results[0]["links"]
        assert len(links) >= 2

    def test_parse_respects_max_pages(self, spider):
        spider.max_pages = 1
        html = "<html><head><title>Single</title></head><body><p>Only one</p></body></html>"
        response = _make_response("https://example.com", html.encode())
        results = list(spider.parse(response))
        assert len(results) == 1
        response2 = _make_response("https://example.com/page2", html.encode())
        results2 = list(spider.parse(response2))
        assert len(results2) == 0


class TestGenericSpiderErrors:
    """Error path: невалидный HTML, пустой body."""

    def test_parse_empty_body(self, spider):
        response = _make_response("https://example.com", b"")
        results = list(spider.parse(response))
        assert len(results) == 1
        assert results[0]["title"] == ""

    def test_parse_malformed_html(self, spider):
        html = b"<html><head><title>Broken</head><body><p>Unclosed"
        response = _make_response("https://example.com", html)
        results = list(spider.parse(response))
        assert len(results) >= 1

    def test_parse_no_title(self, spider):
        html = b"<html><body><p>No title here</p></body></html>"
        response = _make_response("https://example.com", html)
        results = list(spider.parse(response))
        assert len(results) == 1
        assert results[0]["title"] == ""


class TestGenericSpiderSettings:
    """Проверка production-ready settings."""

    def test_stealth_middleware(self):
        assert "lab_playwright_kit.scrapy_engine.middlewares.StealthMiddleware" in \
            GenericSpider.custom_settings.get("DOWNLOADER_MIDDLEWARES", {})

    def test_validation_pipeline(self):
        assert "lab_playwright_kit.scrapy_engine.pipelines.ValidationPipeline" in \
            GenericSpider.custom_settings.get("ITEM_PIPELINES", {})

    def test_dedup_pipeline(self):
        assert "lab_playwright_kit.scrapy_engine.pipelines.DedupPipeline" in \
            GenericSpider.custom_settings.get("ITEM_PIPELINES", {})

    def test_retry_times(self):
        assert GenericSpider.custom_settings.get("RETRY_TIMES", 0) >= 3
