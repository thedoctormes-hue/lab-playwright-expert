"""Тесты AvitoDealerSpider — happy path + error path."""

from __future__ import annotations

import pytest
from scrapy.http import HtmlResponse, Request

from lab_playwright_kit.scrapy_engine.spiders.avito_dealer_spider import (
    AvitoDealerSpider,
    parse_avito_listing,
    parse_date_ru,
    parse_params,
    parse_price,
)


# ─── Helper function tests ────────────────────────────────────────────────────


class TestParsePrice:
    def test_basic(self):
        assert parse_price("1 750 000") == 1750000

    def test_empty(self):
        assert parse_price("") is None

    def test_no_digits(self):
        assert parse_price("no price") is None


class TestParseParams:
    def test_mileage(self):
        result = parse_params("170 000 км, 1.6 AT, седан, бензин")
        assert result["mileage_km"] == "170000"

    def test_transmission(self):
        result = parse_params("1.6 AT, седан")
        assert result["transmission"] == "AT"

    def test_engine_volume(self):
        result = parse_params("1.6 AT, 123 л.с.")
        assert result["engine_L"] == "1.6"

    def test_empty(self):
        result = parse_params("")
        assert result == {}


class TestParseDateRu:
    def test_today(self):
        from datetime import datetime

        result = parse_date_ru("Сегодня", datetime(2026, 6, 30))
        assert result == "2026-06-30"

    def test_yesterday(self):
        from datetime import datetime

        result = parse_date_ru("Вчера", datetime(2026, 6, 30))
        assert result == "2026-06-29"

    def test_empty(self):
        assert parse_date_ru("") == ""


# ─── parse_avito_listing tests ────────────────────────────────────────────────


class TestParseAvitoListing:
    def test_parse_valid_html(self):
        html = (
            '<html><body>'
            '<div data-marker="item">'
            '<span data-marker="item-title">Toyota Camry 2020</span>'
            '<span data-marker="item-price-value">1 750 000</span>'
            '<div data-marker="item-specific-params">170 000 км, 1.6 AT, седан</div>'
            '<div data-marker="item-location">Moscow</div>'
            '<div data-marker="item-date">Сегодня</div>'
            '<a itemprop="url" href="/moskva/avtomobili/toyota_camry_123">Link</a>'
            '</div></body></html>'
        )
        results = parse_avito_listing(html, "https://avito.ru", "Toyota")
        assert len(results) == 1
        assert results[0]["title"] == "Toyota Camry 2020"
        assert results[0]["price_rub"] == 1750000
        assert results[0]["brand"] == "Toyota"

    def test_parse_empty_html(self):
        results = parse_avito_listing("<html><body></body></html>")
        assert results == []

    def test_parse_no_items(self):
        html = '<html><body><div class="listing">No items here</div></body></html>'
        results = parse_avito_listing(html)
        assert results == []


# ─── Scrapy Spider tests ─────────────────────────────────────────────────────


@pytest.fixture
def spider():
    return AvitoDealerSpider(url="https://avito.ru/moskva/avtomobili", brand="Toyota", max_pages=5)


class TestAvitoDealerSpiderParse:
    """Happy path: парсинг страницы Авито через Scrapy response."""

    def test_parse_returns_items(self, spider):
        html = (
            b'<html><body>'
            b'<div data-marker="item">'
            b'<span data-marker="item-title">Toyota Camry 2020</span>'
            b'<span data-marker="item-price-value">1 750 000</span>'
            b'<div data-marker="item-specific-params">170 000 km, AT, sedan</div>'
            b'<div data-marker="item-location">Moscow</div>'
            b'<div data-marker="item-date">2 days ago</div>'
            b'<a itemprop="url" href="/moskva/avtomobili/toyota_123">Link</a>'
            b'</div></body></html>'
        )
        request = Request(url="https://avito.ru/moskva/avtomobili")
        response = HtmlResponse(url="https://avito.ru/moskva/avtomobili", body=html, request=request)
        results = list(spider.parse(response))
        assert len(results) >= 1
        assert results[0]["title"] == "Toyota Camry 2020"

    def test_parse_empty_page(self, spider):
        html = b"<html><body><p>No cars found</p></body></html>"
        request = Request(url="https://avito.ru/moskva/avtomobili")
        response = HtmlResponse(url="https://avito.ru/moskva/avtomobili", body=html, request=request)
        results = list(spider.parse(response))
        assert len(results) == 0


class TestAvitoDealerSpiderSettings:
    """Проверка production-ready settings."""

    def test_stealth_middleware(self):
        assert "lab_playwright_kit.scrapy_engine.middlewares.StealthMiddleware" in \
            AvitoDealerSpider.custom_settings.get("DOWNLOADER_MIDDLEWARES", {})

    def test_dedup_pipeline(self):
        assert "lab_playwright_kit.scrapy_engine.pipelines.DedupPipeline" in \
            AvitoDealerSpider.custom_settings.get("ITEM_PIPELINES", {})

    def test_retry_times(self):
        assert AvitoDealerSpider.custom_settings.get("RETRY_TIMES", 0) >= 3
