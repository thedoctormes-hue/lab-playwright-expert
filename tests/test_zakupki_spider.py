"""Тесты ZakupkiSpider — happy path + error path."""

from __future__ import annotations

import pytest
from scrapy.http import HtmlResponse, Request

from lab_playwright_kit.scrapy_engine.spiders.zakupki_spider import ZakupkiSpider


@pytest.fixture
def spider():
    return ZakupkiSpider(query="construction", max_pages=5)


def _make_response(url, body, meta=None):
    """Создать HtmlResponse с request.meta."""
    request = Request(url=url, meta=meta or {})
    return HtmlResponse(url=url, body=body, request=request)


class TestZakupkiSpiderParse:
    """Happy path: парсинг списка закупок."""

    def test_parse_listing_returns_items(self, spider):
        html = (
            b'<html><body>'
            b'<div class="registerBox">'
            b'<div class="registerBoxBank">'
            b'<a href="/contract/123">Contract Link</a>'
            b'<div class="textBox">'
            b'<div class="title">Build Road</div>'
            b'<div class="number">0123456789</div>'
            b'<div class="price">1 500 000</div>'
            b'<div class="customer">Customer</div>'
            b'<div class="status">Active</div>'
            b'</div></div></div></body></html>'
        )
        response = _make_response(
            "https://zakupki.gov.ru/epz/order/extendedsearch/search.html", html
        )
        results = list(spider.parse_listing(response))
        assert len(results) >= 1
        item = results[0]
        assert item["subject"] == "Build Road"
        assert item["spider_name"] == "zakupki"

    def test_parse_listing_multiple_cards(self, spider):
        html = (
            b'<html><body>'
            b'<div class="registerBox">'
            b'<div class="registerBoxBank">'
            b'<a href="/contract/1"></a>'
            b'<div class="textBox">'
            b'<div class="title">Contract A</div>'
            b'<div class="number">001</div>'
            b'<div class="price">100 000</div>'
            b'</div></div>'
            b'<div class="registerBoxBank">'
            b'<a href="/contract/2"></a>'
            b'<div class="textBox">'
            b'<div class="title">Contract B</div>'
            b'<div class="number">002</div>'
            b'<div class="price">200 000</div>'
            b'</div></div>'
            b'</div></body></html>'
        )
        response = _make_response("https://zakupki.gov.ru/search.html", html)
        results = list(spider.parse_listing(response))
        assert len(results) == 2
        assert results[0]["subject"] == "Contract A"
        assert results[1]["subject"] == "Contract B"


class TestZakupkiSpiderErrors:
    """Error path."""

    def test_parse_empty_page(self, spider):
        html = b"<html><body><p>No contracts found</p></body></html>"
        response = _make_response("https://zakupki.gov.ru/search.html", html)
        results = list(spider.parse_listing(response))
        assert len(results) == 0

    def test_parse_malformed_html(self, spider):
        html = b"<html><body><div class='registerBox'><div class='registerBoxBank'></div></body></html>"
        response = _make_response("https://zakupki.gov.ru/search.html", html)
        results = list(spider.parse_listing(response))
        assert isinstance(results, list)

    def test_max_pages_limit(self, spider):
        spider.max_pages = 1
        spider._current_page = 1
        html = (
            b'<html><body>'
            b'<div class="registerBox">'
            b'<div class="registerBoxBank">'
            b'<a href="/contract/1"></a>'
            b'<div class="textBox"><div class="title">Test</div></div>'
            b'</div></div></body></html>'
        )
        response = _make_response("https://zakupki.gov.ru/search.html", html)
        results = list(spider.parse_listing(response))
        assert len(results) == 0


class TestZakupkiSpiderSettings:
    """Проверка production-ready settings."""

    def test_stealth_middleware(self):
        assert "lab_playwright_kit.scrapy_engine.middlewares.StealthMiddleware" in \
            ZakupkiSpider.custom_settings.get("DOWNLOADER_MIDDLEWARES", {})

    def test_validation_pipeline(self):
        assert "lab_playwright_kit.scrapy_engine.pipelines.ValidationPipeline" in \
            ZakupkiSpider.custom_settings.get("ITEM_PIPELINES", {})

    def test_dedup_pipeline(self):
        assert "lab_playwright_kit.scrapy_engine.pipelines.DedupPipeline" in \
            ZakupkiSpider.custom_settings.get("ITEM_PIPELINES", {})

    def test_retry_times(self):
        assert ZakupkiSpider.custom_settings.get("RETRY_TIMES", 0) >= 3
