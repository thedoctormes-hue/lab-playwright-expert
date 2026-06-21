"""
Extended tests for price_parser.py — PriceParser, PriceItem, PriceReport, InvitroParser, CMDParser, KDLParser.

Covers: dataclasses, static methods, parser properties (mocked HTTP).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lab_playwright_kit.price_parser import (
    CMDParser,
    InvitroParser,
    KDLParser,
    PriceItem,
    PriceParser,
    PriceReport,
)


# ─── PriceItem Tests ─────────────────────────────────────────────────────────


class TestPriceItem:
    def test_defaults(self):
        item = PriceItem()
        assert item.lab == ""
        assert item.code == ""
        assert item.name == ""
        assert item.price == 0
        assert item.currency == "RUB"
        assert item.duration == ""
        assert item.category == ""
        assert item.url == ""

    def test_full(self):
        item = PriceItem(
            lab="Invitro",
            code="123",
            name="Анализ крови",
            price=500,
            currency="RUB",
            duration="1 к.д.",
            category="Общие",
            url="https://invitro.ru/123",
        )
        assert item.lab == "Invitro"
        assert item.price == 500

    def test_to_dict(self):
        item = PriceItem(lab="Invitro", code="123", name="Test", price=500)
        d = item.to_dict()
        assert d["lab"] == "Invitro"
        assert d["code"] == "123"
        assert d["name"] == "Test"
        assert d["price"] == 500
        assert d["currency"] == "RUB"


# ─── PriceReport Tests ───────────────────────────────────────────────────────


class TestPriceReport:
    def test_defaults(self):
        report = PriceReport()
        assert report.lab == ""
        assert report.items == []
        assert report.categories == {}
        assert report.total_price == 0
        assert report.elapsed_seconds == 0.0
        assert report.errors == []

    def test_avg_price(self):
        report = PriceReport(
            items=[
                PriceItem(price=100),
                PriceItem(price=200),
                PriceItem(price=300),
            ]
        )
        assert report.avg_price == 200.0

    def test_avg_price_empty(self):
        report = PriceReport()
        assert report.avg_price == 0.0

    def test_to_dict(self):
        report = PriceReport(
            lab="Invitro",
            items=[PriceItem(price=100), PriceItem(price=200)],
            categories={"Общие": 2},
            total_price=300,
            elapsed_seconds=5.0,
        )
        d = report.to_dict()
        assert d["lab"] == "Invitro"
        assert d["total_items"] == 2
        assert d["categories"] == {"Общие": 2}
        assert d["avg_price"] == 150.0


# ─── InvitroParser Tests ────────────────────────────────────────────────────


class TestInvitroParser:
    def test_constants(self):
        assert InvitroParser.BASE_URL == "https://www.invitro.ru"
        assert "v1/tests" in InvitroParser.API_TESTS
        assert "v1/popular" in InvitroParser.API_POPULAR

    def test_init(self):
        parser = InvitroParser(timeout=60.0)
        assert parser.timeout == 60.0

    def test_init_default(self):
        parser = InvitroParser()
        assert parser.timeout == 120.0

    def test_extract_from_data_empty(self):
        parser = InvitroParser()
        result = parser._extract_from_data([])
        assert result == []

    def test_extract_from_data_one_category(self):
        parser = InvitroParser()
        data = [
            {
                "category_name": "Общие",
                "products": [
                    {
                        "code": "123",
                        "title": "Анализ крови",
                        "price": 500,
                        "deadline": "1",
                        "bitrix_id": "456",
                        "id": "789",
                        "product_type": "TEST",
                    },
                    {
                        "code": "124",
                        "title": "Invalid",
                        "price": 0,
                        "deadline": "",
                        "bitrix_id": "0",
                        "id": "0",
                        "product_type": "",
                    },
                ],
            },
        ]
        result = parser._extract_from_data(data)
        assert len(result) == 1
        assert result[0].lab == "Invitro"
        assert result[0].code == "123"
        assert result[0].name == "Анализ крови"
        assert result[0].price == 500
        assert result[0].category == "Общие"
        assert "к.д." in result[0].duration

    def test_extract_from_data_multiple_categories(self):
        parser = InvitroParser()
        data = [
            {
                "category_name": "Гормоны",
                "products": [
                    {
                        "code": "1",
                        "title": "ТТГ",
                        "price": 300,
                        "deadline": "2",
                        "bitrix_id": "1",
                        "id": "1",
                        "product_type": "TEST",
                    },
                ],
            },
            {
                "category_name": "Витамины",
                "products": [
                    {
                        "code": "2",
                        "title": "B12",
                        "price": 400,
                        "deadline": "3",
                        "bitrix_id": "2",
                        "id": "2",
                        "product_type": "TEST",
                    },
                ],
            },
        ]
        result = parser._extract_from_data(data)
        assert len(result) == 2
        assert result[0].category == "Гормоны"
        assert result[1].category == "Витамины"

    def test_extract_from_data_invalid_prices(self):
        parser = InvitroParser()
        data = [
            {
                "category_name": "Test",
                "products": [
                    {
                        "code": "1",
                        "title": "NaN price",
                        "price": "invalid",
                        "deadline": "",
                        "bitrix_id": "1",
                        "id": "1",
                        "product_type": "",
                    },
                ],
            },
        ]
        result = parser._extract_from_data(data)
        assert len(result) == 0  # invalid price is skipped

    @pytest.mark.asyncio
    async def test_parse_empty(self):
        parser = InvitroParser()
        with patch.object(parser, "_fetch_all_tests", new_callable=AsyncMock, return_value=[]):
            report = await parser.parse()
            assert report.lab == "Invitro"
            assert report.items == []
            assert report.categories == {}
            assert report.total_price == 0

    @pytest.mark.asyncio
    async def test_parse_with_items(self):
        parser = InvitroParser()
        items = [
            PriceItem(lab="Invitro", code="1", name="Test", price=500, category="Общие"),
            PriceItem(lab="Invitro", code="2", name="Test2", price=300, category="Общие"),
        ]
        with patch.object(parser, "_fetch_all_tests", new_callable=AsyncMock, return_value=items):
            report = await parser.parse()
            assert len(report.items) == 2
            assert report.categories == {"Общие": 2}
            assert report.total_price == 800


# ─── CMDParser Tests ─────────────────────────────────────────────────────────


class TestCMDParser:
    def test_constants(self):
        assert CMDParser.BASE_URL == "https://www.cmd-online.ru"
        assert "catalog" in CMDParser.CATALOG_URL

    def test_init_with_browser(self):
        bm = MagicMock()
        parser = CMDParser(browser_manager=bm, timeout=30.0)
        assert parser._bm is bm
        assert parser.timeout == 30.0

    def test_init_without_browser(self):
        parser = CMDParser()
        assert parser._bm is None

    @pytest.mark.asyncio
    async def test_parse_with_mock_browser(self):
        parser = CMDParser(timeout=30.0)
        mock_bm = MagicMock()
        mock_page = MagicMock()
        mock_bm.new_page = AsyncMock(return_value=mock_page)
        mock_page.goto = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.wait_for_selector = AsyncMock()
        mock_page.evaluate = AsyncMock(
            return_value=[
                {
                    "title": "CMD Test",
                    "price": 530,
                    "href": "https://cmd-online.ru/1",
                    "category": "Анализы",
                    "code": "CMD1",
                    "duration": "2 к.д.",
                },
            ]
        )
        mock_page.close = AsyncMock()

        # Patch BrowserManager to return our mock
        with patch("lab_playwright_kit.price_parser.BrowserManager") as mock_bm_cls:
            mock_bm_instance = MagicMock()
            mock_bm_instance.start = AsyncMock()
            mock_bm_instance.new_page = AsyncMock(return_value=mock_page)
            mock_bm_instance.stop = AsyncMock()
            mock_bm_cls.return_value = mock_bm_instance

            report = await parser.parse()
            assert report.lab == "CMD"
            # Items depend on evaluate mock — if own_bm is True it'll use the patched BM


# ─── KDLParser Tests ─────────────────────────────────────────────────────────


class TestKDLParser:
    def test_constants(self):
        assert KDLParser.BASE_URL == "https://kdl.ru"
        assert "analizy" in KDLParser.PRICE_URL

    @pytest.mark.asyncio
    async def test_parse_returns_stub(self):
        parser = KDLParser()
        report = await parser.parse()
        assert report.lab == "KDL"
        assert len(report.errors) > 0
        assert "403" in report.errors[0]


# ─── PriceParser Tests ───────────────────────────────────────────────────────


class TestPriceParser:
    def test_init(self):
        parser = PriceParser()
        assert parser._bm is None

    def test_init_with_browser(self):
        bm = MagicMock()
        parser = PriceParser(browser_manager=bm)
        assert parser._bm is bm

    def test_export_to_json(self, tmp_path):
        report = PriceReport(
            lab="Invitro",
            items=[PriceItem(code="1", name="Test", price=500)],
            categories={"Общие": 1},
            total_price=500,
        )
        filepath = str(tmp_path / "test.json")
        PriceParser.export_to_json(report, filepath)
        import json

        with open(filepath) as f:
            data = json.load(f)
        assert data["lab"] == "Invitro"
        assert data["total_items"] == 1

    def test_export_to_csv(self, tmp_path):
        report = PriceReport(
            lab="Invitro",
            items=[
                PriceItem(
                    code="1",
                    name="Test",
                    price=500,
                    currency="RUB",
                    duration="1 к.д.",
                    category="Общие",
                    url="https://test.com",
                )
            ],
        )
        filepath = str(tmp_path / "test.csv")
        PriceParser.export_to_csv(report, filepath)
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        assert "Код" in content
        assert "Test" in content
        assert "500" in content

    @pytest.mark.asyncio
    async def test_parse_lab_invitro(self):
        parser = PriceParser()
        with patch.object(InvitroParser, "parse", new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = PriceReport(lab="Invitro", items=[])
            report = await parser.parse_lab("Invitro")
            assert report.lab == "Invitro"

    @pytest.mark.asyncio
    async def test_parse_lab_cmd(self):
        parser = PriceParser()
        with patch.object(CMDParser, "parse", new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = PriceReport(lab="CMD", items=[])
            report = await parser.parse_lab("CMD")
            assert report.lab == "CMD"

    @pytest.mark.asyncio
    async def test_parse_lab_kdl(self):
        parser = PriceParser()
        report = await parser.parse_lab("KDL")
        assert report.lab == "KDL"
        assert len(report.errors) > 0

    @pytest.mark.asyncio
    async def test_parse_lab_invalid(self):
        parser = PriceParser()
        with pytest.raises(ValueError, match="Unknown lab"):
            await parser.parse_lab("UnknownLab")

    @pytest.mark.asyncio
    async def test_parse_lab_case_insensitive(self):
        parser = PriceParser()
        with patch.object(InvitroParser, "parse", new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = PriceReport(lab="Invitro", items=[])
            report = await parser.parse_lab("invitro")
            assert report.lab == "Invitro"
