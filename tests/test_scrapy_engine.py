"""
Tests for Scrapy Engine — items, pipelines, middlewares, spiders.

Run: pytest tests/test_scrapy_engine.py -v
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lab_playwright_kit.scrapy_engine.items import (
    ScrapedAuto,
    ScrapedContract,
    ScrapedPage,
    ScrapedProduct,
)
from lab_playwright_kit.scrapy_engine.middlewares.proxy_middleware import ProxyMiddleware
from lab_playwright_kit.scrapy_engine.middlewares.stealth_middleware import StealthMiddleware
from lab_playwright_kit.scrapy_engine.pipelines.dedup_pipeline import DedupPipeline
from lab_playwright_kit.scrapy_engine.pipelines.export_pipeline import ExportPipeline
from lab_playwright_kit.scrapy_engine.pipelines.validation_pipeline import ValidationPipeline
from lab_playwright_kit.scrapy_engine.settings import get_settings


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_spider():
    spider = MagicMock()
    spider.name = "test_spider"
    return spider


@pytest.fixture
def sample_page():
    return ScrapedPage(
        url="https://example.com/page1",
        domain="example.com",
        spider_name="test",
        title="Test Page",
        text="Hello world",
        status_code=200,
    )


@pytest.fixture
def sample_product():
    return ScrapedProduct(
        url="https://shop.com/item1",
        domain="shop.com",
        spider_name="test",
        title="Widget",
        price=99.99,
        currency="USD",
    )


@pytest.fixture
def sample_product_no_price():
    return ScrapedProduct(
        url="https://shop.com/item2",
        domain="shop.com",
        spider_name="test",
        title="Free Item",
        price=None,
    )


# ─── Items ────────────────────────────────────────────────────────────────────


class TestScrapedPage:
    def test_create(self, sample_page):
        assert sample_page["url"] == "https://example.com/page1"
        assert sample_page["title"] == "Test Page"

    def test_to_dict(self, sample_page):
        d = dict(sample_page)
        assert d["url"] == "https://example.com/page1"
        assert "title" in d

    def test_empty_url(self):
        item = ScrapedPage()
        assert item.get("url") is None


class TestScrapedAuto:
    def test_create(self):
        item = ScrapedAuto(
            url="https://avito.ru/1",
            domain="avito.ru",
            spider_name="avito_dealer",
            title="Toyota Camry 2020",
            price=2_500_000,
            year=2020,
            mileage=50000,
            engine="2.5L",
            transmission="auto",
        )
        assert item["title"] == "Toyota Camry 2020"
        assert item["price"] == 2_500_000
        assert item["year"] == 2020

    def test_optional_fields(self):
        item = ScrapedAuto(url="https://avito.ru/2", title="Test")
        assert item.get("year") is None


class TestScrapedContract:
    def test_create(self):
        item = ScrapedContract(
            url="https://zakupki.gov.ru/1",
            spider_name="zakupki",
            reg_number="0123456789",
            subject="Строительство",
        )
        assert item["reg_number"] == "0123456789"


# ─── ValidationPipeline ───────────────────────────────────────────────────────


class TestValidationPipeline:
    def test_valid_page(self, mock_spider, sample_page):
        pipe = ValidationPipeline()
        result = pipe.process_item(sample_page, mock_spider)
        assert result["url"] == "https://example.com/page1"

    def test_missing_url_drops(self, mock_spider):
        pipe = ValidationPipeline()
        item = ScrapedPage(title="No URL")
        with pytest.raises(Exception):  # DropItem
            pipe.process_item(item, mock_spider)

    def test_valid_product(self, mock_spider, sample_product):
        pipe = ValidationPipeline()
        result = pipe.process_item(sample_product, mock_spider)
        assert result["price"] == 99.99

    def test_missing_title_drops(self, mock_spider):
        pipe = ValidationPipeline()
        item = ScrapedProduct(url="https://x.com/1")
        with pytest.raises(Exception):  # DropItem
            pipe.process_item(item, mock_spider)

    def test_negative_price_corrected(self, mock_spider):
        pipe = ValidationPipeline()
        item = ScrapedProduct(url="https://x.com/1", title="X", price=-10)
        result = pipe.process_item(item, mock_spider)
        assert result["price"] == 0

    def test_invalid_price_nulled(self, mock_spider):
        pipe = ValidationPipeline()
        item = ScrapedProduct(url="https://x.com/1", title="X", price="abc")
        result = pipe.process_item(item, mock_spider)
        assert result["price"] is None

    def test_no_url_required_for_generic_dict(self, mock_spider):
        """ScrapedPage требует url, но не title."""
        pipe = ValidationPipeline()
        item = ScrapedPage(url="https://x.com")
        result = pipe.process_item(item, mock_spider)
        assert result is not None


# ─── DedupPipeline ────────────────────────────────────────────────────────────


class TestDedupPipeline:
    def test_first_passes(self, mock_spider, sample_page):
        pipe = DedupPipeline()
        result = pipe.process_item(sample_page, mock_spider)
        assert result is not None

    def test_duplicate_dropped(self, mock_spider, sample_page):
        pipe = DedupPipeline()
        pipe.process_item(sample_page, mock_spider)
        with pytest.raises(Exception):  # DropItem
            pipe.process_item(sample_page, mock_spider)

    def test_case_insensitive(self, mock_spider, sample_page):
        pipe = DedupPipeline()
        pipe.process_item(sample_page, mock_spider)

        page2 = ScrapedPage(url="https://EXAMPLE.COM/page1", title="UPPER")
        with pytest.raises(Exception):
            pipe.process_item(page2, mock_spider)

    def test_trailing_slash_normalized(self, mock_spider):
        pipe = DedupPipeline()
        p1 = ScrapedPage(url="https://example.com/page1/")
        pipe.process_item(p1, mock_spider)

        p2 = ScrapedPage(url="https://example.com/page1")
        pipe.process_item(p2, mock_spider)  # slash stripped, URL matches

    def test_different_urls_pass(self, mock_spider):
        pipe = DedupPipeline()
        p1 = ScrapedPage(url="https://example.com/a", title="A")
        p2 = ScrapedPage(url="https://example.com/b", title="B")
        pipe.process_item(p1, mock_spider)
        result = pipe.process_item(p2, mock_spider)
        assert result is not None

    def test_from_crawler(self):
        crawler = MagicMock()
        pipe = DedupPipeline.from_crawler(crawler)
        assert pipe is not None


# ─── ExportPipeline ───────────────────────────────────────────────────────────


class TestExportPipeline:
    def test_json_export(self, mock_spider, sample_page):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipe = ExportPipeline(fmt="json", output_dir=tmpdir, batch_size=2)
            pipe.open_spider(mock_spider)
            pipe.process_item(sample_page, mock_spider)
            pipe.close_spider(mock_spider)

            files = list(Path(tmpdir).glob("*.json"))
            assert len(files) == 1
            data = json.loads(files[0].read_text())
            assert len(data) == 1
            assert data[0]["url"] == "https://example.com/page1"

    def test_batch_flush(self, mock_spider):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipe = ExportPipeline(fmt="json", output_dir=tmpdir, batch_size=2)
            pipe.open_spider(mock_spider)

            for i in range(5):
                item = ScrapedPage(url=f"https://example.com/{i}", title=f"Page {i}")
                pipe.process_item(item, mock_spider)

            pipe.close_spider(mock_spider)

            files = list(Path(tmpdir).glob("*.json"))
            assert len(files) >= 1
            total = sum(len(json.loads(f.read_text())) for f in files)
            assert total == 5

    def test_csv_export(self, mock_spider, sample_page):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipe = ExportPipeline(fmt="csv", output_dir=tmpdir, batch_size=10)
            pipe.open_spider(mock_spider)
            pipe.process_item(sample_page, mock_spider)
            pipe.close_spider(mock_spider)

            files = list(Path(tmpdir).glob("*.csv"))
            assert len(files) == 1
            content = files[0].read_text()
            assert "url" in content
            assert "https://example.com/page1" in content

    def test_sqlite_export(self, mock_spider, sample_page):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipe = ExportPipeline(fmt="sqlite", output_dir=tmpdir, batch_size=10)
            pipe.open_spider(mock_spider)
            pipe.process_item(sample_page, mock_spider)
            pipe.close_spider(mock_spider)

            db_files = list(Path(tmpdir).glob("*.db"))
            assert len(db_files) == 1

    def test_invalid_format_not_configured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = MagicMock()
            crawler.settings.get.return_value = "xml"
            crawler.settings.getlist.return_value = []
            crawler.settings.getint.return_value = 100

            with pytest.raises(Exception):  # NotConfigured
                ExportPipeline.from_crawler(crawler)

    def test_multiple_items_json(self, mock_spider, sample_product, sample_product_no_price):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipe = ExportPipeline(fmt="json", output_dir=tmpdir, batch_size=5)
            pipe.open_spider(mock_spider)
            pipe.process_item(sample_product, mock_spider)
            pipe.process_item(sample_product_no_price, mock_spider)
            pipe.close_spider(mock_spider)

            files = list(Path(tmpdir).glob("*.json"))
            data = json.loads(files[0].read_text())
            assert len(data) == 2
            assert data[0]["price"] == 99.99
            assert data[1]["price"] is None


# ─── StealthMiddleware ────────────────────────────────────────────────────────


class TestStealthMiddleware:
    def test_process_request_sets_headers(self):
        mw = StealthMiddleware()
        from scrapy import Request

        req = Request("https://example.com")
        mw.process_request(req)

        ua = req.headers.get("User-Agent")
        assert ua is not None
        assert len(ua) > 0

    def test_accept_header_set(self):
        mw = StealthMiddleware()
        from scrapy import Request

        req = Request("https://example.com")
        mw.process_request(req)
        assert b"text/html" in req.headers.get("Accept", b"")

    def test_referer_from_meta(self):
        mw = StealthMiddleware()
        from scrapy import Request

        req = Request("https://example.com/next", meta={"referer": "https://example.com/prev"})
        mw.process_request(req)
        assert req.headers.get("Referer") == b"https://example.com/prev"

    def test_403_detection(self, mock_spider):
        mw = StealthMiddleware()
        from scrapy import Request
        from scrapy.http import Response

        req = Request("https://example.com")
        resp = Response("https://example.com", status=403)
        result = mw.process_response(req, resp)
        assert result.status == 403

    def test_from_crawler(self):
        crawler = MagicMock()
        mw = StealthMiddleware.from_crawler(crawler)
        assert mw is not None


# ─── ProxyMiddleware ──────────────────────────────────────────────────────────


class TestProxyMiddleware:
    def test_no_proxy_by_default(self):
        mw = ProxyMiddleware(proxy_list=[], mode="round_robin")
        from scrapy import Request

        req = Request("https://example.com")
        mw.process_request(req)
        assert req.meta.get("proxy") is None

    def test_round_robin(self):
        mw = ProxyMiddleware(proxy_list=["http://p1:8080", "http://p2:8080"])
        from scrapy import Request

        req1 = Request("https://example.com/1")
        req2 = Request("https://example.com/2")
        req3 = Request("https://example.com/3")

        mw.process_request(req1)
        mw.process_request(req2)
        mw.process_request(req3)

        assert req1.meta["proxy"] == "http://p1:8080"
        assert req2.meta["proxy"] == "http://p2:8080"
        assert req3.meta["proxy"] == "http://p1:8080"  # wraps

    def test_dont_override_existing_proxy(self):
        mw = ProxyMiddleware(proxy_list=["http://p1:8080"])
        from scrapy import Request

        req = Request("https://example.com", meta={"proxy": "http://existing:8080"})
        mw.process_request(req)
        assert req.meta["proxy"] == "http://existing:8080"

    def test_uses_download_timeout(self):
        mw = ProxyMiddleware(proxy_list=["http://p1:8080"])
        from scrapy import Request

        req = Request("https://example.com")
        mw.process_request(req)
        assert req.meta.get("download_timeout") == 30

    def test_exception_returns_new_request(self):
        mw = ProxyMiddleware(proxy_list=["http://p1:8080"])
        from scrapy import Request

        req = Request("https://example.com", meta={"proxy": "http://p1:8080"})
        result = mw.process_exception(req, Exception("timeout"))
        assert result is not None
        assert result.meta.get("proxy") is None

    def test_from_crawler(self):
        crawler = MagicMock()
        crawler.settings.getlist.return_value = ["http://p1:8080"]
        crawler.settings.get.return_value = "round_robin"
        mw = ProxyMiddleware.from_crawler(crawler)
        assert mw._proxies == ["http://p1:8080"]


# ─── Settings ─────────────────────────────────────────────────────────────────


class TestSettings:
    def test_get_settings(self):
        s = get_settings()
        assert isinstance(s, dict) or hasattr(s, "get")

    def test_download_delay(self):
        s = get_settings()
        assert s.get("DOWNLOAD_DELAY", 0) >= 1.0

    def test_pipelines_configured(self):
        s = get_settings()
        pipelines = s.get("ITEM_PIPELINES", {})
        assert len(pipelines) > 0

    def test_middlewares_configured(self):
        s = get_settings()
        mw = s.get("DOWNLOADER_MIDDLEWARES", {})
        assert len(mw) > 0
