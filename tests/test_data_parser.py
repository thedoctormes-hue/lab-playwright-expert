"""
Tests for DataParser module.
Covers: NicheSchema, FieldMapping, DataParser, BatchParser, export utils.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sys

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from lab_playwright_kit.data_parser import (
    BatchParser,
    DataParser,
    FieldMapping,
    NicheSchema,
    NicheType,
    NicheProfile,
    ParseResult,
    detect_niche,
    export_to_csv,
    export_to_json,
    get_schema,
    SCHEMA_REGISTRY,
    TRANSFORMS,
    ECOMMERCE_SCHEMA,
    NEWS_SCHEMA,
    REALTY_SCHEMA,
    MEDTECH_SCHEMA,
    JOBS_SCHEMA,
    AUTO_SCHEMA,
    HABR_SCHEMA,
    VCRU_SCHEMA,
    TWITTER_SCHEMA,
    TELEGRAM_SCHEMA,
)


# ═══════════════════════════════════════════════════════════════════════════════
# FieldMapping
# ═══════════════════════════════════════════════════════════════════════════════

class TestFieldMapping:
    """Тесты FieldMapping dataclass."""

    def test_defaults(self):
        fm = FieldMapping(name="test")
        assert fm.name == "test"
        assert fm.selectors == []
        assert fm.attribute is None
        assert fm.regex is None
        assert fm.transform is None
        assert fm.default is None
        assert fm.required is False
        assert fm.is_list is False

    def test_full_config(self):
        fm = FieldMapping(
            name="price",
            selectors=[".price", "[data-price]"],
            regex=r"[\d.]+",
            transform="float",
            default=0.0,
            required=True,
        )
        assert fm.name == "price"
        assert len(fm.selectors) == 2
        assert fm.regex == r"[\d.]+"
        assert fm.transform == "float"
        assert fm.default == 0.0
        assert fm.required is True


# ═══════════════════════════════════════════════════════════════════════════════
# NicheSchema
# ═══════════════════════════════════════════════════════════════════════════════

class TestNicheSchema:
    """Тесты NicheSchema."""

    def test_get_required_fields(self):
        schema = NicheSchema(
            niche=NicheType.CUSTOM,
            name="Test",
            fields=[
                FieldMapping(name="title", required=True),
                FieldMapping(name="price", required=True),
                FieldMapping(name="desc"),
            ],
        )
        required = schema.get_required_fields()
        assert len(required) == 2
        assert required[0].name == "title"
        assert required[1].name == "price"

    def test_get_field_names(self):
        schema = NicheSchema(
            niche=NicheType.CUSTOM,
            name="Test",
            fields=[
                FieldMapping(name="a"),
                FieldMapping(name="b"),
            ],
        )
        assert schema.get_field_names() == ["a", "b"]

    def test_empty_schema(self):
        schema = NicheSchema(niche=NicheType.CUSTOM, name="Empty")
        assert schema.get_required_fields() == []
        assert schema.get_field_names() == []


# ═══════════════════════════════════════════════════════════════════════════════
# Schema Registry
# ═══════════════════════════════════════════════════════════════════════════════

class TestSchemaRegistry:
    """Тесты реестра схем."""

    def test_all_niches_present(self):
        expected = {
            NicheType.ECOMMERCE, NicheType.NEWS, NicheType.REALTY,
            NicheType.MEDTECH, NicheType.JOBS, NicheType.AUTO,
            NicheType.HABR, NicheType.VCRU, NicheType.TWITTER,
            NicheType.TELEGRAM,
        }
        assert set(SCHEMA_REGISTRY.keys()) == expected

    def test_ecommerce_schema(self):
        schema = get_schema(NicheType.ECOMMERCE)
        assert schema.niche == NicheType.ECOMMERCE
        assert len(schema.fields) >= 5
        field_names = schema.get_field_names()
        assert "title" in field_names
        assert "price" in field_names

    def test_news_schema(self):
        schema = get_schema(NicheType.NEWS)
        assert schema.niche == NicheType.NEWS
        field_names = schema.get_field_names()
        assert "title" in field_names
        assert "content" in field_names

    def test_realry_schema(self):
        schema = get_schema(NicheType.REALTY)
        field_names = schema.get_field_names()
        assert "price" in field_names
        assert "address" in field_names

    def test_medtech_schema(self):
        schema = get_schema(NicheType.MEDTECH)
        field_names = schema.get_field_names()
        assert "title" in field_names
        assert "description" in field_names

    def test_jobs_schema(self):
        schema = get_schema(NicheType.JOBS)
        field_names = schema.get_field_names()
        assert "title" in field_names
        assert "company" in field_names

    def test_auto_schema(self):
        schema = get_schema(NicheType.AUTO)
        field_names = schema.get_field_names()
        assert "title" in field_names
        assert "price" in field_names
        assert "brand" in field_names

    def test_unknown_niche_raises(self):
        with pytest.raises(ValueError):
            get_schema(NicheType.GENERIC)

    def test_ecommerce_required_fields(self):
        schema = get_schema(NicheType.ECOMMERCE)
        required = schema.get_required_fields()
        required_names = [f.name for f in required]
        assert "title" in required_names
        assert "price" in required_names


# ═══════════════════════════════════════════════════════════════════════════════
# Niche Detection
# ═══════════════════════════════════════════════════════════════════════════════

class TestNicheDetection:
    """Тесты автоопределения ниши по URL."""

    def test_ecommerce_urls(self):
        urls = [
            "https://shop.com/product/123",
            "https://store.com/item/456",
            "https://amazon.com/dp/B08N5WRWNW",
        ]
        for url in urls:
            assert detect_niche(url) == NicheType.ECOMMERCE, f"Failed for {url}"

    def test_news_urls(self):
        urls = [
            "https://news.com/article/123",
            "https://blog.com/blog/hello",
            "https://site.com/2024/05/17/something",
        ]
        for url in urls:
            assert detect_niche(url) == NicheType.NEWS, f"Failed for {url}"

    def test_jobs_urls(self):
        urls = [
            "https://hh.ru/vacancy/123",
            "https://rabota.ru/vakansiya/dev",
        ]
        for url in urls:
            assert detect_niche(url) == NicheType.JOBS, f"Failed for {url}"

    def test_auto_urls(self):
        urls = [
            "https://auto.ru/car/123",
            "https://drom.ru/auto/456",
        ]
        for url in urls:
            assert detect_niche(url) == NicheType.AUTO, f"Failed for {url}"

    def test_generic_url(self):
        assert detect_niche("https://example.com/page") == NicheType.GENERIC


# ═══════════════════════════════════════════════════════════════════════════════
# Transforms
# ═══════════════════════════════════════════════════════════════════════════════

class TestTransforms:
    """Тесты функций трансформации."""

    def test_int_transform(self):
        assert TRANSFORMS["int"]("123") == 123
        assert TRANSFORMS["int"](" 456 ") == 456
        assert TRANSFORMS["int"]("1 234") == 1234

    def test_float_transform(self):
        assert TRANSFORMS["float"]("99.99") == 99.99
        assert TRANSFORMS["float"]("1 234,56") == 1234.56

    def test_strip_transform(self):
        assert TRANSFORMS["strip"]("  hello  ") == "hello"
        assert TRANSFORMS["strip"]("world") == "world"

    def test_lowercase_transform(self):
        assert TRANSFORMS["strip"]("Hello World") == "Hello World"

    def test_none_handling(self):
        assert TRANSFORMS["int"](None) is None
        assert TRANSFORMS["float"](None) is None
        assert TRANSFORMS["strip"](None) is None


# ═══════════════════════════════════════════════════════════════════════════════
# ParseResult
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseResult:
    """Тесты ParseResult dataclass."""

    def test_defaults(self):
        result = ParseResult(url="https://example.com", niche=NicheType.GENERIC)
        assert result.url == "https://example.com"
        assert result.niche == NicheType.GENERIC
        assert result.data == {}
        assert result.confidence == 0.0
        assert result.is_valid is False

    def test_is_valid_with_data(self):
        result = ParseResult(
            url="https://example.com",
            niche=NicheType.ECOMMERCE,
            data={"title": "Test", "price": 99.99},
            confidence=0.8,
        )
        assert result.is_valid is True

    def test_is_valid_with_errors(self):
        result = ParseResult(
            url="https://example.com",
            niche=NicheType.GENERIC,
            confidence=0.8,
            errors=["page_load_failed"],
        )
        assert result.is_valid is False

    def test_to_dict(self):
        result = ParseResult(
            url="https://example.com",
            niche=NicheType.NEWS,
            data={"title": "Test"},
            confidence=0.5,
        )
        d = result.to_dict()
        assert d["url"] == "https://example.com"
        assert d["niche"] == "news"
        assert d["data"] == {"title": "Test"}
        assert d["confidence"] == 0.5

    def test_summary(self):
        result = ParseResult(
            url="https://example.com",
            niche=NicheType.ECOMMERCE,
            data={"title": "Test", "price": 99.99},
            confidence=0.8,
            parse_time_ms=150.0,
            domain="example.com",
        )
        s = result.summary()
        assert "ecommerce" in s
        assert "2/2 fields" in s
        assert "80.0%" in s

    def test_domain_parsed_fallback(self):
        result = ParseResult(
            url="https://example.com/page",
            niche=NicheType.GENERIC,
        )
        assert result.domain_parsed == "example.com"


# ═══════════════════════════════════════════════════════════════════════════════
# NicheProfile alias
# ═══════════════════════════════════════════════════════════════════════════════

class TestNicheProfile:
    """Тесты что NicheProfile == NicheType."""

    def test_alias(self):
        assert NicheProfile is NicheType

    def test_alias_values(self):
        assert NicheProfile.ECOMMERCE == NicheType.ECOMMERCE
        assert NicheProfile.NEWS == NicheType.NEWS
        assert NicheProfile.AUTO == NicheType.AUTO


# ═══════════════════════════════════════════════════════════════════════════════
# Export Utils
# ═══════════════════════════════════════════════════════════════════════════════

class TestExportUtils:
    """Тесты экспорта в CSV и JSON."""

    def _make_results(self) -> list[ParseResult]:
        return [
            ParseResult(
                url="https://shop.com/product/1",
                niche=NicheType.ECOMMERCE,
                data={"title": "Product 1", "price": 99.99, "brand": "TestBrand"},
                confidence=0.9,
                domain="shop.com",
            ),
            ParseResult(
                url="https://shop.com/product/2",
                niche=NicheType.ECOMMERCE,
                data={"title": "Product 2", "price": 149.99},
                confidence=0.7,
                domain="shop.com",
            ),
        ]

    def test_export_to_csv(self):
        results = self._make_results()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            export_to_csv(results, path)
            with open(path) as f:
                content = f.read()
            assert "url,niche,confidence,domain" in content
            assert "Product 1" in content
            assert "99.99" in content
        finally:
            os.unlink(path)

    def test_export_to_csv_empty(self):
        path = "/tmp/test_empty.csv"
        result = export_to_csv([], path)
        assert result == ""

    def test_export_to_json(self):
        results = self._make_results()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            export_to_json(results, path)
            with open(path) as f:
                data = json.load(f)
            assert data["meta"]["total"] == 2
            assert data["meta"]["valid"] == 2
            assert len(data["results"]) == 2
            assert data["results"][0]["niche"] == "ecommerce"
        finally:
            os.unlink(path)

    def test_export_to_json_empty(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            export_to_json([], path)
            with open(path) as f:
                data = json.load(f)
            assert data["meta"]["total"] == 0
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════════════════
# DataParser (unit tests with mocks)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataParser:
    """Unit-тесты DataParser с моками."""

    def test_init_defaults(self):
        mock_bm = MagicMock()
        parser = DataParser(mock_bm)
        assert parser._niche is None
        assert parser._custom_schema is None
        assert parser._timeout == 30.0
        assert parser._max_retries == 3
        assert parser._strict is False

    def test_init_with_niche(self):
        mock_bm = MagicMock()
        parser = DataParser(mock_bm, niche=NicheType.NEWS)
        assert parser._niche == NicheType.NEWS

    def test_init_with_custom_schema(self):
        mock_bm = MagicMock()
        schema = NicheSchema(
            niche=NicheType.CUSTOM,
            name="Test",
            fields=[FieldMapping(name="test")],
        )
        parser = DataParser(mock_bm, custom_schema=schema)
        assert parser._custom_schema is schema

    def test_init_strict_mode(self):
        mock_bm = MagicMock()
        parser = DataParser(mock_bm, strict=True)
        assert parser._strict is True


# ═══════════════════════════════════════════════════════════════════════════════
# BatchParser (unit tests with mocks)
# ═══════════════════════════════════════════════════════════════════════════════

class TestBatchParser:
    """Unit-тесты BatchParser."""

    def test_init_defaults(self):
        mock_bm = MagicMock()
        batch = BatchParser(mock_bm)
        assert batch._niche is None
        assert batch._rps == 1.0
        assert batch._max_concurrent == 3

    def test_init_custom(self):
        mock_bm = MagicMock()
        batch = BatchParser(
            mock_bm,
            niche=NicheType.NEWS,
            requests_per_second=2.0,
            max_concurrent=5,
        )
        assert batch._niche == NicheType.NEWS
        assert batch._rps == 2.0
        assert batch._max_concurrent == 5


# ═══════════════════════════════════════════════════════════════════════════════
# Schema field coverage
# ═══════════════════════════════════════════════════════════════════════════════

class TestSchemaFieldCoverage:
    """Тесты что все схемы содержат ожидаемые поля."""

    def test_ecommerce_has_price_and_title(self):
        schema = ECOMMERCE_SCHEMA
        names = schema.get_field_names()
        assert "title" in names
        assert "price" in names
        assert "description" in names

    def test_news_has_content_and_title(self):
        schema = NEWS_SCHEMA
        names = schema.get_field_names()
        assert "title" in names
        assert "content" in names
        assert "author" in names

    def test_realry_has_price_and_address(self):
        schema = REALTY_SCHEMA
        names = schema.get_field_names()
        assert "price" in names
        assert "address" in names
        assert "area" in names

    def test_medtech_has_description(self):
        schema = MEDTECH_SCHEMA
        names = schema.get_field_names()
        assert "title" in names
        assert "description" in names

    def test_jobs_has_title_and_company(self):
        schema = JOBS_SCHEMA
        names = schema.get_field_names()
        assert "title" in names
        assert "company" in names
        assert "salary" in names

    def test_auto_has_brand_and_model(self):
        schema = AUTO_SCHEMA
        names = schema.get_field_names()
        assert "brand" in names
        assert "model" in names
        assert "year" in names

    # ─── New Social / Content Platform Schemas ─────────────────────────────

    def test_habr_schema_registered(self):
        assert NicheType.HABR in SCHEMA_REGISTRY
        schema = HABR_SCHEMA
        assert schema.niche == NicheType.HABR
        assert schema.name == "Habr"

    def test_habr_has_required_fields(self):
        schema = HABR_SCHEMA
        names = schema.get_field_names()
        assert "title" in names
        assert "content" in names
        assert "author" in names
        assert "rating" in names
        assert "hubs" in names
        assert "tags" in names
        assert "views" in names
        assert "comments_count" in names
        assert "bookmarks_count" in names
        assert "reading_time" in names

    def test_habr_url_detection(self):
        assert detect_niche("https://habr.com/ru/articles/123456/") == NicheType.HABR
        assert detect_niche("https://habr.ru/en/post/789/") == NicheType.HABR

    def test_vcru_schema_registered(self):
        assert NicheType.VCRU in SCHEMA_REGISTRY
        schema = VCRU_SCHEMA
        assert schema.niche == NicheType.VCRU
        assert schema.name == "VC.ru"

    def test_vcru_has_required_fields(self):
        schema = VCRU_SCHEMA
        names = schema.get_field_names()
        assert "title" in names
        assert "content" in names
        assert "author" in names
        assert "rating" in names
        assert "views" in names
        assert "tags" in names
        assert "category" in names
        assert "image" in names

    def test_vcru_url_detection(self):
        assert detect_niche("https://vc.ru/marketing/123456-article") == NicheType.VCRU

    def test_twitter_schema_registered(self):
        assert NicheType.TWITTER in SCHEMA_REGISTRY
        schema = TWITTER_SCHEMA
        assert schema.niche == NicheType.TWITTER
        assert schema.name == "Twitter/X"

    def test_twitter_has_required_fields(self):
        schema = TWITTER_SCHEMA
        names = schema.get_field_names()
        assert "author" in names
        assert "text" in names
        assert "author_handle" in names
        assert "likes" in names
        assert "retweets" in names
        assert "replies" in names
        assert "views" in names
        assert "hashtags" in names
        assert "mentions" in names
        assert "images" in names

    def test_twitter_url_detection(self):
        assert detect_niche("https://twitter.com/user/status/123456") == NicheType.TWITTER
        assert detect_niche("https://x.com/user/status/789012") == NicheType.TWITTER

    def test_telegram_schema_registered(self):
        assert NicheType.TELEGRAM in SCHEMA_REGISTRY
        schema = TELEGRAM_SCHEMA
        assert schema.niche == NicheType.TELEGRAM
        assert schema.name == "Telegram"

    def test_telegram_has_required_fields(self):
        schema = TELEGRAM_SCHEMA
        names = schema.get_field_names()
        assert "channel_name" in names
        assert "text" in names
        assert "views" in names
        assert "published_date" in names
        assert "reactions" in names
        assert "images" in names
        assert "forwarded_from" in names
        assert "reply_to" in names

    def test_telegram_url_detection(self):
        assert detect_niche("https://t.me/channel_name/123") == NicheType.TELEGRAM

    def test_all_10_niches_registered(self):
        """Все 10 ниш зарегистрированы в SCHEMA_REGISTRY."""
        expected = {
            NicheType.ECOMMERCE, NicheType.NEWS, NicheType.REALTY,
            NicheType.MEDTECH, NicheType.JOBS, NicheType.AUTO,
            NicheType.HABR, NicheType.VCRU, NicheType.TWITTER,
            NicheType.TELEGRAM,
        }
        assert set(SCHEMA_REGISTRY.keys()) == expected
