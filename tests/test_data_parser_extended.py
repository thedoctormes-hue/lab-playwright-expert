"""
Extended tests for data_parser.py — Niche schemas, FieldMapping, parsing logic.

Covers: NicheType enum, FieldMapping, NicheSchema, all predefined schemas,
detect_niche, get_schema, export functions, TRANSFORMS.
"""

import pytest

from lab_playwright_kit.data_parser import (
    SCHEMA_REGISTRY,
    TRANSFORMS,
    FieldMapping,
    NicheSchema,
    NicheType,
    ParseResult,
    detect_niche,
    export_to_json,
    get_schema,
)


# ─── NicheType Tests ─────────────────────────────────────────────────────────


class TestNicheType:
    def test_all_types(self):
        assert NicheType.ECOMMERCE.value == "ecommerce"
        assert NicheType.NEWS.value == "news"
        assert NicheType.REALTY.value == "realty"
        assert NicheType.MEDTECH.value == "medtech"
        assert NicheType.JOBS.value == "jobs"
        assert NicheType.AUTO.value == "auto"
        assert NicheType.HABR.value == "habr"
        assert NicheType.VCRU.value == "vcru"
        assert NicheType.TWITTER.value == "twitter"
        assert NicheType.TELEGRAM.value == "telegram"
        assert NicheType.CUSTOM.value == "custom"
        assert NicheType.GENERIC.value == "generic"

    def test_from_string(self):
        assert NicheType("ecommerce") == NicheType.ECOMMERCE
        assert NicheType("habr") == NicheType.HABR

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            NicheType("nonexistent")


# ─── FieldMapping Tests ──────────────────────────────────────────────────────


class TestFieldMapping:
    def test_defaults(self):
        fm = FieldMapping(name="title")
        assert fm.name == "title"
        assert fm.selectors == []
        assert fm.attribute is None
        assert fm.regex is None
        assert fm.transform is None
        assert fm.default is None
        assert fm.required is False
        assert fm.is_list is False
        assert fm.description == ""

    def test_full(self):
        fm = FieldMapping(
            name="price",
            selectors=[".price", "[data-price]"],
            attribute="content",
            regex=r"[\d.]+",
            transform="float",
            default=0,
            required=True,
            is_list=False,
            description="Price field",
        )
        assert fm.name == "price"
        assert len(fm.selectors) == 2
        assert fm.attribute == "content"
        assert fm.regex == r"[\d.]+"
        assert fm.transform == "float"
        assert fm.default == 0
        assert fm.required is True
        assert fm.description == "Price field"


# ─── NicheSchema Tests ───────────────────────────────────────────────────────


class TestNicheSchema:
    def test_defaults(self):
        schema = NicheSchema(
            niche=NicheType.CUSTOM,
            name="Custom",
        )
        assert schema.niche == NicheType.CUSTOM
        assert schema.name == "Custom"
        assert schema.description == ""
        assert schema.fields == []
        assert schema.url_patterns == []
        assert schema.content_check is None
        assert schema.pagination_selector is None
        assert schema.item_selector is None

    def test_get_required_fields(self):
        schema = NicheSchema(
            niche=NicheType.CUSTOM,
            name="Test",
            fields=[
                FieldMapping(name="title", required=True),
                FieldMapping(name="desc", required=False),
                FieldMapping(name="price", required=True),
            ],
        )
        required = schema.get_required_fields()
        assert len(required) == 2
        assert required[0].name == "title"
        assert required[1].name == "price"

    def test_get_required_fields_empty(self):
        schema = NicheSchema(niche=NicheType.CUSTOM, name="Empty")
        assert schema.get_required_fields() == []

    def test_get_field_names(self):
        schema = NicheSchema(
            niche=NicheType.CUSTOM,
            name="Test",
            fields=[
                FieldMapping(name="title"),
                FieldMapping(name="price"),
            ],
        )
        assert schema.get_field_names() == ["title", "price"]

    def test_get_field_names_empty(self):
        schema = NicheSchema(niche=NicheType.CUSTOM, name="Empty")
        assert schema.get_field_names() == []


# ─── Schema Registry Tests ───────────────────────────────────────────────────


class TestSchemaRegistry:
    def test_all_schemas_present(self):
        expected = [
            NicheType.ECOMMERCE,
            NicheType.NEWS,
            NicheType.REALTY,
            NicheType.MEDTECH,
            NicheType.JOBS,
            NicheType.AUTO,
            NicheType.HABR,
            NicheType.VCRU,
            NicheType.TWITTER,
            NicheType.TELEGRAM,
            NicheType.CUSTOM,
            NicheType.GENERIC,
        ]
        for nt in expected:
            assert nt in SCHEMA_REGISTRY

    def test_ecommerce_schema(self):
        schema = SCHEMA_REGISTRY[NicheType.ECOMMERCE]
        assert schema.name == "E-Commerce"
        assert len(schema.fields) > 0
        assert schema.url_patterns  # has patterns

    def test_news_schema(self):
        schema = SCHEMA_REGISTRY[NicheType.NEWS]
        assert schema.name == "News"
        assert any(f.name == "title" for f in schema.fields)
        assert any(f.name == "content" for f in schema.fields)

    def test_habr_schema(self):
        schema = SCHEMA_REGISTRY[NicheType.HABR]
        assert schema.name == "Habr"
        assert any(f.name == "title" for f in schema.fields)
        assert any(f.name == "author" for f in schema.fields)
        assert any(f.name == "rating" for f in schema.fields)

    def test_vcru_schema(self):
        schema = SCHEMA_REGISTRY[NicheType.VCRU]
        assert schema.name == "VC.ru"
        assert any(f.name == "title" for f in schema.fields)

    def test_auto_schema(self):
        schema = SCHEMA_REGISTRY[NicheType.AUTO]
        assert schema.name == "Auto"
        assert any(f.name == "brand" for f in schema.fields)
        assert any(f.name == "mileage" for f in schema.fields)

    def test_jobs_schema(self):
        schema = SCHEMA_REGISTRY[NicheType.JOBS]
        assert schema.name == "Jobs"
        assert any(f.name == "salary" for f in schema.fields)

    def test_realty_schema(self):
        schema = SCHEMA_REGISTRY[NicheType.REALTY]
        assert schema.name == "Realty"
        assert any(f.name == "area" for f in schema.fields)

    def test_medtech_schema(self):
        schema = SCHEMA_REGISTRY[NicheType.MEDTECH]
        assert schema.name == "MedTech"
        assert any(f.name == "indications" for f in schema.fields)


# ─── detect_niche Tests ──────────────────────────────────────────────────────


class TestDetectNiche:
    def test_ecommerce_urls(self):
        assert detect_niche("https://shop.example.com/product/123") == NicheType.ECOMMERCE
        assert detect_niche("https://store.com/item/456") == NicheType.ECOMMERCE

    def test_news_urls(self):
        assert detect_niche("https://news.example.com/article/123") == NicheType.NEWS
        assert detect_niche("https://blog.example.com/2026/01/01/post") == NicheType.NEWS

    def test_habr_urls(self):
        assert detect_niche("https://habr.com/ru/articles/123456/") == NicheType.HABR

    def test_vcru_urls(self):
        assert detect_niche("https://vc.ru/marketing/12345") == NicheType.VCRU

    def test_generic_url(self):
        result = detect_niche("https://unknown.example.com/page")
        assert isinstance(result, NicheType)


# ─── get_schema Tests ────────────────────────────────────────────────────────


class TestGetSchema:
    def test_valid_niche(self):
        schema = get_schema(NicheType.ECOMMERCE)
        assert schema.niche == NicheType.ECOMMERCE

    def test_all_niches(self):
        for nt in SCHEMA_REGISTRY:
            schema = get_schema(nt)
            assert schema.niche == nt


# ─── TRANSFORMS Tests ────────────────────────────────────────────────────────


class TestTransforms:
    def test_int_transform(self):
        assert TRANSFORMS["int"]("42") == 42

    def test_float_transform(self):
        assert TRANSFORMS["float"]("3.14") == 3.14

    def test_strip_transform(self):
        assert TRANSFORMS["strip"]("  hello  ") == "hello"

    def test_lowercase_transform(self):
        assert TRANSFORMS["lowercase"]("HELLO") == "hello"

    def test_all_transforms_exist(self):
        assert "int" in TRANSFORMS
        assert "float" in TRANSFORMS
        assert "strip" in TRANSFORMS
        assert "lowercase" in TRANSFORMS


# ─── ParseResult Tests ───────────────────────────────────────────────────────


class TestParseResult:
    def test_creation(self):
        result = ParseResult(
            url="https://example.com",
            niche="news",
            data={"title": "Test"},
            confidence=0.9,
            page_title="Test",
            domain="example.com",
            errors=[],
        )
        assert result.url == "https://example.com"
        assert result.confidence == 0.9


# ─── export_to_json Tests ────────────────────────────────────────────────────


class TestExportToJson:
    def test_export(self, tmp_path):
        result = ParseResult(
            url="https://example.com",
            niche="news",
            data={"title": "Test"},
            confidence=0.9,
            page_title="Test",
            domain="example.com",
            errors=[],
        )
        filepath = str(tmp_path / "test.json")
        export_to_json(result, filepath)
        import json

        with open(filepath) as f:
            data = json.load(f)
        assert data["url"] == "https://example.com"
        assert data["niche"] == "news"
