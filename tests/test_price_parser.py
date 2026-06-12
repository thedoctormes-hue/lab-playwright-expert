"""
Тесты для Price Parser — парсера прайс-листов медицинских лабораторий.

Запуск:
    pytest tests/test_price_parser.py -v --tb=short
"""
import pytest

from lab_playwright_kit.price_parser import (
    CMDParser,
    InvitroParser,
    KDLParser,
    PriceItem,
    PriceParser,
    PriceReport,
)


# ─── Data Models ─────────────────────────────────────────────────────────────

class TestPriceItem:
    """Тесты модели PriceItem."""

    def test_default_values(self):
        item = PriceItem()
        assert item.lab == ""
        assert item.code == ""
        assert item.name == ""
        assert item.price == 0
        assert item.currency == "RUB"
        assert item.duration == ""
        assert item.category == ""
        assert item.url == ""

    def test_to_dict(self):
        item = PriceItem(
            lab="Invitro",
            code="16",
            name="Глюкоза (в крови)",
            price=370,
            duration="1 к.д.",
            category="Глюкоза и метаболиты",
            url="https://www.invitro.ru/analizy-i-tseny/glukoza_2212/",
        )
        d = item.to_dict()
        assert d["lab"] == "Invitro"
        assert d["code"] == "16"
        assert d["name"] == "Глюкоза (в крови)"
        assert d["price"] == 370
        assert d["currency"] == "RUB"
        assert d["duration"] == "1 к.д."
        assert d["category"] == "Глюкоза и метаболиты"
        assert d["url"] == "https://www.invitro.ru/analizy-i-tseny/glukoza_2212/"

    def test_to_dict_with_product_fields(self):
        item = PriceItem(
            lab="Invitro",
            name="Биохимия крови",
            price=7345,
            product_id="24fca7b4-2dbe-4c75-9c3f-01c6ae982973",
            product_type="COMPLEX",
        )
        d = item.to_dict()
        assert d["product_id"] == "24fca7b4-2dbe-4c75-9c3f-01c6ae982973"
        assert d["product_type"] == "COMPLEX"


class TestPriceReport:
    """Тесты модели PriceReport."""

    def test_default_values(self):
        report = PriceReport(lab="Test")
        assert report.lab == "Test"
        assert report.items == []
        assert report.categories == {}
        assert report.total_price == 0
        assert report.elapsed_seconds == 0.0
        assert report.errors == []

    def test_avg_price_empty(self):
        report = PriceReport(lab="Test")
        assert report.avg_price == 0

    def test_avg_price_with_items(self):
        report = PriceReport(
            lab="Test",
            items=[
                PriceItem(price=100),
                PriceItem(price=200),
                PriceItem(price=300),
            ],
            total_price=600,
        )
        assert report.avg_price == 200.0

    def test_to_dict(self):
        report = PriceReport(
            lab="Invitro",
            items=[
                PriceItem(lab="Invitro", name="Глюкоза", price=370, category="Биохимия"),
                PriceItem(lab="Invitro", name="Ферритин", price=935, category="Железо"),
            ],
            categories={"Биохимия": 1, "Железо": 1},
            total_price=1305,
            elapsed_seconds=5.0,
        )
        d = report.to_dict()
        assert d["lab"] == "Invitro"
        assert d["total_items"] == 2
        assert d["categories"] == {"Биохимия": 1, "Железо": 1}
        assert d["avg_price"] == 652.5
        assert d["elapsed_seconds"] == 5.0
        assert len(d["items"]) == 2


# ─── Invitro Parser ──────────────────────────────────────────────────────────

class TestInvitroParser:
    """Тесты парсера Invitro."""

    def test_parser_creation(self):
        parser = InvitroParser()
        assert parser.BASE_URL == "https://www.invitro.ru"
        assert parser.CITY_ID_MOSCOW == "f1c3c4f0-3426-4cda-8449-e5d326e02f97"

    def test_parser_custom_timeout(self):
        parser = InvitroParser(timeout=60.0)
        assert parser.timeout == 60.0

    @pytest.mark.anyio
    async def test_parse_returns_report(self):
        """Интеграционный тест: парсинг Invitro через API."""
        parser = InvitroParser(timeout=120)
        report = await parser.parse()

        assert isinstance(report, PriceReport)
        assert report.lab == "Invitro"
        assert len(report.items) > 0, "Invitro должен вернуть анализы"
        assert len(report.categories) > 0
        assert report.avg_price > 0
        assert report.elapsed_seconds > 0

    @pytest.mark.anyio
    async def test_parse_items_have_required_fields(self):
        """Все анализы должны иметь название и цену."""
        parser = InvitroParser(timeout=120)
        report = await parser.parse()

        for item in report.items:
            assert item.name, f"Анализ без названия: {item}"
            assert item.price > 0, f"Анализ без цены: {item.name}"
            assert item.lab == "Invitro"

    @pytest.mark.anyio
    async def test_parse_categories_populated(self):
        """Категории должны быть заполнены."""
        parser = InvitroParser(timeout=120)
        report = await parser.parse()

        assert len(report.categories) > 10, "Ожидается >10 категорий"

    def test_extract_from_data_empty(self):
        """Пустые данные — пустой результат."""
        parser = InvitroParser()
        result = parser._extract_from_data([])
        assert result == []

    def test_extract_from_data_with_items(self):
        """Извлечение из структуры категорий."""
        parser = InvitroParser()
        data = [
            {
                "category_name": "Биохимия",
                "products": [
                    {
                        "title": "Глюкоза",
                        "price": 370,
                        "code": "16",
                        "deadline": 1,
                        "id": "abc-123",
                        "product_type": "TEST",
                        "bitrix_id": 2212,
                    },
                    {
                        "title": "Ферритин",
                        "price": 935,
                        "code": "2245",
                        "deadline": 2,
                        "id": "def-456",
                        "product_type": "TEST",
                        "bitrix_id": 2245,
                    },
                ],
            },
        ]

        items = parser._extract_from_data(data)
        assert len(items) == 2
        assert items[0].name == "Глюкоза"
        assert items[0].price == 370
        assert items[0].category == "Биохимия"
        assert items[0].code == "16"
        assert items[0].duration == "1 к.д."
        assert items[0].product_type == "TEST"

    def test_extract_from_data_skips_zero_price(self):
        """Продукты с нулевой ценой пропускаются."""
        parser = InvitroParser()
        data = [
            {
                "category_name": "Тест",
                "products": [
                    {"title": "Бесплатный", "price": 0, "code": "0"},
                    {"title": "Платный", "price": 500, "code": "1"},
                ],
            },
        ]

        items = parser._extract_from_data(data)
        assert len(items) == 1
        assert items[0].name == "Платный"

    def test_extract_from_data_handles_string_price(self):
        """Цена как строка корректно обрабатывается."""
        parser = InvitroParser()
        data = [
            {
                "category_name": "Тест",
                "products": [
                    {"title": "Анализ", "price": "500", "code": "1"},
                ],
            },
        ]

        items = parser._extract_from_data(data)
        assert len(items) == 1
        assert items[0].price == 500


# ─── CMD Parser ──────────────────────────────────────────────────────────────

class TestCMDParser:
    """Тесты парсера CMD."""

    def test_parser_creation(self):
        parser = CMDParser()
        assert parser.BASE_URL == "https://www.cmd-online.ru"
        assert "cmd-online.ru" in parser.CATALOG_URL

    def test_parser_custom_timeout(self):
        parser = CMDParser(timeout=30.0)
        assert parser.timeout == 30.0

    @pytest.mark.anyio
    async def test_parse_returns_report(self):
        """Интеграционный тест: парсинг CMD через браузер."""
        parser = CMDParser(timeout=60)
        report = await parser.parse()

        assert isinstance(report, PriceReport)
        assert report.lab == "CMD"
        # CMD показывает ~30 анализов на главной
        assert len(report.items) > 0, "CMD должен вернуть анализы"
        assert report.elapsed_seconds > 0

    @pytest.mark.anyio
    async def test_parse_items_have_required_fields(self):
        """Все анализы CMD должны иметь название и цену."""
        parser = CMDParser(timeout=60)
        report = await parser.parse()

        for item in report.items:
            assert item.name, f"Анализ без названия: {item}"
            assert item.price > 0, f"Анализ без цены: {item.name}"
            assert item.lab == "CMD"


# ─── KDL Parser ──────────────────────────────────────────────────────────────

class TestKDLParser:
    """Тесты парсера KDL (заглушка)."""

    def test_parser_creation(self):
        parser = KDLParser()
        assert parser.BASE_URL == "https://kdl.ru"

    @pytest.mark.anyio
    async def test_parse_returns_stub_report(self):
        """KDL возвращает заглушку с ошибкой 403."""
        parser = KDLParser()
        report = await parser.parse()

        assert isinstance(report, PriceReport)
        assert report.lab == "KDL"
        assert len(report.items) == 0
        assert len(report.errors) > 0
        assert "403" in report.errors[0]


# ─── PriceParser (Main) ──────────────────────────────────────────────────────

class TestPriceParser:
    """Тесты главного парсера."""

    def test_parser_creation(self):
        parser = PriceParser()
        assert parser._invitro is not None
        assert parser._cmd is not None
        assert parser._kdl is not None

    @pytest.mark.anyio
    async def test_parse_all_returns_all_labs(self):
        """parse_all возвращает отчёты для всех лабораторий."""
        parser = PriceParser()
        results = await parser.parse_all()

        assert "Invitro" in results
        assert "CMD" in results
        assert "KDL" in results

        # Invitro должен иметь данные
        assert len(results["Invitro"].items) > 0

    @pytest.mark.anyio
    async def test_parse_lab_invitro(self):
        """parse_lab('Invitro') возвращает отчёт Invitro."""
        parser = PriceParser()
        report = await parser.parse_lab("Invitro")

        assert report.lab == "Invitro"
        assert len(report.items) > 0

    @pytest.mark.anyio
    async def test_parse_lab_cmd(self):
        """parse_lab('CMD') возвращает отчёт CMD."""
        parser = PriceParser()
        report = await parser.parse_lab("CMD")

        assert report.lab == "CMD"
        assert len(report.items) > 0

    @pytest.mark.anyio
    async def test_parse_lab_kdl(self):
        """parse_lab('KDL') возвращает заглушку."""
        parser = PriceParser()
        report = await parser.parse_lab("KDL")

        assert report.lab == "KDL"
        assert len(report.items) == 0

    def test_parse_lab_unknown(self):
        """parse_lab с неизвестной лабораторией — ValueError."""
        parser = PriceParser()
        with pytest.raises(ValueError, match="Unknown lab"):
            asyncio_run(parser.parse_lab("UnknownLab"))

    def test_export_to_json(self, tmp_path):
        """Экспорт в JSON."""
        report = PriceReport(
            lab="Test",
            items=[
                PriceItem(lab="Test", name="Анализ1", price=500, category="Кат1"),
                PriceItem(lab="Test", name="Анализ2", price=1000, category="Кат2"),
            ],
            categories={"Кат1": 1, "Кат2": 1},
            total_price=1500,
            elapsed_seconds=1.0,
        )

        filepath = str(tmp_path / "test_report.json")
        PriceParser.export_to_json(report, filepath)

        import json
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["lab"] == "Test"
        assert data["total_items"] == 2
        assert len(data["items"]) == 2

    def test_export_to_csv(self, tmp_path):
        """Экспорт в CSV."""
        report = PriceReport(
            lab="Test",
            items=[
                PriceItem(lab="Test", name="Анализ1", price=500, code="1"),
                PriceItem(lab="Test", name="Анализ2", price=1000, code="2"),
            ],
        )

        filepath = str(tmp_path / "test_report.csv")
        PriceParser.export_to_csv(report, filepath)

        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 3  # header + 2 items
        assert "Код" in lines[0]
        assert "Название" in lines[0]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def asyncio_run(coro):
    """Запуск корутины для синхронных тестов."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # В уже запущенном loop — создаём новый поток
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)
