"""Тесты PlaywrightPartSpider — happy path + error path."""

from __future__ import annotations

import asyncio

import pytest
from scrapy.http import HtmlResponse, Request

from lab_playwright_kit.scrapy_engine.spiders.auto_parts.part_spider import (
    PlaywrightPartSpider,
    parse_delivery_days,
    parse_price,
)


@pytest.fixture
def spider():
    return PlaywrightPartSpider(article="OC244", shops="exist,emex")


class TestPlaywrightPartSpiderInit:
    """Тесты инициализации и конфигурации."""

    def test_name(self):
        spider = PlaywrightPartSpider(article="OC244")
        assert spider.name == "auto_parts"

    def test_article_normalized(self):
        spider = PlaywrightPartSpider(article="oc-244")
        assert spider.article == "OC-244"

    def test_all_shops_when_not_specified(self):
        spider = PlaywrightPartSpider(article="OC244")
        from lab_playwright_kit.scrapy_engine.spiders.auto_parts import SHOP_CONFIGS

        assert set(spider.shop_keys) == set(SHOP_CONFIGS.keys())

    def test_specific_shops(self):
        spider = PlaywrightPartSpider(article="OC244", shops="exist,emex,fobil")
        assert spider.shop_keys == ["exist", "emex", "fobil"]

    def test_invalid_shops_filtered(self):
        spider = PlaywrightPartSpider(article="OC244", shops="exist,foobar,emex")
        assert "foobar" not in spider.shop_keys
        assert "exist" in spider.shop_keys


class TestPlaywrightPartSpiderStartRequests:
    """Тесты генерации начальных запросов."""

    def test_start_requests(self):
        spider = PlaywrightPartSpider(article="OC244", shops="exist,emex")
        requests = list(spider.start_requests())
        assert len(requests) == 2
        for req in requests:
            assert req.meta["playwright"] is True
            assert req.meta["article"] == "OC244"

    def test_start_requests_url_param(self):
        """exist генерирует GET-запрос к URL с артикулом."""
        spider = PlaywrightPartSpider(article="OC244", shops="exist")
        requests = list(spider.start_requests())
        assert len(requests) == 1
        assert "OC244" in requests[0].url
        assert "exist.ru" in requests[0].url

    def test_start_requests_form_submit(self):
        """apex генерирует GET к базовому URL без артикула."""
        spider = PlaywrightPartSpider(article="OC244", shops="apex")
        requests = list(spider.start_requests())
        assert len(requests) == 1
        assert requests[0].url == "https://apex.ru"
        assert requests[0].callback == spider.submit_search_form


class TestPlaywrightPartSpiderErrors:
    """Error path."""

    def test_start_requests_empty_shops(self):
        """Невалидные магазины — должен вернуть пустой список."""
        spider = PlaywrightPartSpider(article="OC244", shops="nonexistent")
        requests = list(spider.start_requests())
        assert len(requests) == 0

    def test_parse_results_without_page(self):
        """parse_results без Playwright page должен вернуть пустой список."""
        spider = PlaywrightPartSpider(article="OC244", shops="exist")
        html = (
            b'<html><body>'
            b'<div class="price-wrapper">'
            b'<span class="price">1500</span>'
            b'<span class="caseDescription">Test Part</span>'
            b'</div></body></html>'
        )
        request = Request(
            url="https://exist.ru/search?text=OC244",
            meta={"shop_key": "exist", "article": "OC244"},
        )
        response = HtmlResponse(
            url="https://exist.ru/search?text=OC244",
            body=html,
            request=request,
        )

        async def _run():
            results = []
            async for item in spider.parse_results(response):
                results.append(item)
            return results

        results = asyncio.get_event_loop().run_until_complete(_run())
        assert len(results) == 0


class TestPlaywrightPartSpiderSettings:
    """Проверка production-ready settings."""

    def test_stealth_middleware(self):
        assert "lab_playwright_kit.scrapy_engine.middlewares.StealthMiddleware" in \
            PlaywrightPartSpider.custom_settings.get("DOWNLOADER_MIDDLEWARES", {})

    def test_validation_pipeline(self):
        assert "lab_playwright_kit.scrapy_engine.pipelines.ValidationPipeline" in \
            PlaywrightPartSpider.custom_settings.get("ITEM_PIPELINES", {})

    def test_dedup_pipeline(self):
        assert "lab_playwright_kit.scrapy_engine.pipelines.DedupPipeline" in \
            PlaywrightPartSpider.custom_settings.get("ITEM_PIPELINES", {})

    def test_retry_times(self):
        assert PlaywrightPartSpider.custom_settings.get("RETRY_TIMES", 0) >= 3


# ─── Helper function tests ────────────────────────────────────────────────────


class TestParsePrice:
    def test_basic(self):
        assert parse_price("1234") == 1234.0

    def test_with_ruble(self):
        assert parse_price("1 234") == 1234.0

    def test_comma_decimal(self):
        assert parse_price("1 234,56") == 1234.56

    def test_empty(self):
        assert parse_price("") == 0.0
        assert parse_price(None) == 0.0

    def test_noise(self):
        assert parse_price("Price: from 1500") == 1500.0


class TestParseDeliveryDays:
    def test_basic(self):
        assert parse_delivery_days("3 days") == 3

    def test_range(self):
        assert parse_delivery_days("2-5 days") == 2

    def test_empty(self):
        assert parse_delivery_days("") is None
        assert parse_delivery_days(None) is None
