"""Тесты PlaywrightPartSpider и ScrapedPart Item."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from lab_playwright_kit.scrapy_engine.items import ScrapedPart
from lab_playwright_kit.scrapy_engine.spiders.auto_parts import SHOP_CONFIGS, SHOP_PRIORITY
from lab_playwright_kit.scrapy_engine.spiders.auto_parts.part_spider import (
    PlaywrightPartSpider,
    parse_delivery_days,
    parse_price,
)


# ─── ScrapedPart Item ─────────────────────────────────────────────────────────


class TestScrapedPart:
    def test_create(self):
        item = ScrapedPart(article="OC244", price=190.0, name="Фильтр масляный")
        assert item["article"] == "OC244"
        assert item["price"] == 190.0
        assert item["name"] == "Фильтр масляный"

    def test_all_fields_present(self):
        expected = {
            "url",
            "domain",
            "spider_name",
            "article",
            "name",
            "brand",
            "sku",
            "price",
            "currency",
            "old_price",
            "availability",
            "delivery_days",
            "warehouse",
            "shop_name",
            "shop_logo",
            "product_url",
            "image_url",
            "crawl_time",
            "status_code",
        }
        assert set(ScrapedPart.fields.keys()) == expected

    def test_optional_fields_default(self):
        item = ScrapedPart(article="TEST", price=100.0, name="Test")
        assert item.get("brand") is None or item.get("brand", "") in ("", None)


# ─── Shop Configs ─────────────────────────────────────────────────────────────


class TestShopConfigs:
    def test_seven_shops(self):
        assert len(SHOP_CONFIGS) == 7

    def test_all_shops_have_required_keys(self):
        for key, config in SHOP_CONFIGS.items():
            assert "display" in config, f"{key}: missing display"
            assert "base_url" in config, f"{key}: missing base_url"
            assert "selectors" in config, f"{key}: missing selectors"
            assert "search_method" in config, f"{key}: missing search_method"
            assert config["search_method"] in (
                "url_param",
                "form_submit",
                "api",
            ), f"{key}: invalid search_method"

    def test_url_param_shops_have_search_url(self):
        for key, config in SHOP_CONFIGS.items():
            if config["search_method"] == "url_param":
                assert config.get("search_url"), f"{key}: url_param but no search_url"
                assert "{article}" in config["search_url"], f"{key}: no {{article}} in search_url"

    def test_shop_priority_is_subset_of_configs(self):
        for shop in SHOP_PRIORITY:
            assert shop in SHOP_CONFIGS, f"{shop} in priority but not in configs"

    # Конкретные магазины

    def test_emex_config(self):
        cfg = SHOP_CONFIGS["emex"]
        assert cfg["display"] == "Emex.ru"
        assert cfg["search_url"] == "https://emex.ru/search?text={article}"
        assert cfg["search_method"] == "url_param"
        assert "result_row" in cfg["selectors"]

    def test_exist_config(self):
        cfg = SHOP_CONFIGS["exist"]
        assert cfg["search_method"] == "url_param"
        assert "fallback_row" in cfg["selectors"]
        assert "delivery" in cfg["selectors"]

    def test_fobil_config(self):
        cfg = SHOP_CONFIGS["fobil"]
        assert cfg["search_url"] == "https://fobil-auto.ru/search?pcode={article}"
        assert "tr.startSearching" in cfg["selectors"]["result_row"]

    def test_apex_config(self):
        cfg = SHOP_CONFIGS["apex"]
        assert cfg["search_method"] == "form_submit"
        assert "search_input" in cfg["selectors"]

    def test_autoeuro_config(self):
        cfg = SHOP_CONFIGS["autoeuro"]
        assert cfg["search_method"] == "form_submit"
        assert cfg["base_url"] == "https://shop.autoeuro.ru"

    def test_mymajor_config(self):
        cfg = SHOP_CONFIGS["mymajor"]
        assert cfg["search_method"] == "form_submit"

    def test_autodoc_config(self):
        cfg = SHOP_CONFIGS["autodoc"]
        assert cfg["search_method"] == "api"
        assert "autodoc" in cfg["base_url"]
        assert cfg.get("api_base") == "https://web.autodoc.ru"


class TestAutodocAPI:
    """Тесты для autodoc API-парсера (без браузера)."""

    def test_search_manufacturers_returns_list(self):
        """search_manufacturers возвращает список производителей."""
        import asyncio

        from lab_playwright_kit.scrapy_engine.spiders.auto_parts.part_spider import (
            PlaywrightPartSpider,
        )

        spider = PlaywrightPartSpider(article="OC471")
        config = SHOP_CONFIGS["autodoc"]

        async def _run():
            items = []
            async for item in spider._parse_autodoc_api("OC471", config):
                items.append(item)
            return items

        items = asyncio.get_event_loop().run_until_complete(_run())
        assert len(items) > 0, "autodoc API должен вернуть хотя бы одно предложение"

    def test_autodoc_offer_has_required_fields(self):
        """Каждое предложение от autodoc содержит article, brand, price."""
        import asyncio

        from lab_playwright_kit.scrapy_engine.spiders.auto_parts.part_spider import (
            PlaywrightPartSpider,
        )

        spider = PlaywrightPartSpider(article="OC471")
        config = SHOP_CONFIGS["autodoc"]

        async def _run():
            items = []
            async for item in spider._parse_autodoc_api("OC471", config):
                items.append(item)
            return items

        items = asyncio.get_event_loop().run_until_complete(_run())
        for item in items:
            assert item["article"] == "OC471"
            assert item["brand"] != ""
            assert item["shop_name"] == "Autodoc.ru"
            assert item["currency"] == "RUB"
            assert item["price"] >= 0

    def test_autodoc_known_article(self):
        """OC471 (фильтр масляный) должен иметь KNECHT|MAHLE с ценой."""
        import asyncio

        from lab_playwright_kit.scrapy_engine.spiders.auto_parts.part_spider import (
            PlaywrightPartSpider,
        )

        spider = PlaywrightPartSpider(article="OC471")
        config = SHOP_CONFIGS["autodoc"]

        async def _run():
            items = []
            async for item in spider._parse_autodoc_api("OC471", config):
                items.append(item)
            return items

        items = asyncio.get_event_loop().run_until_complete(_run())
        brands = [item["brand"] for item in items]
        assert any(
            "KNECHT" in b or "MAHLE" in b for b in brands
        ), f"Ожидается KNECHT|MAHLE в {brands}"
        prices = [item["price"] for item in items]
        assert any(p > 0 for p in prices), f"Ожидается цена > 0 в {prices}"

    @patch("lab_playwright_kit.scrapy_engine.spiders.auto_parts.part_spider.requests")
    def test_autodoc_api_mocked(self, mock_requests):
        """Mock-тест autodoc API без реальных HTTP-запросов."""
        # Подготовка mock-ответов
        mock_mnf_response = MagicMock()
        mock_mnf_response.status_code = 200
        mock_mnf_response.json.return_value = {
            "items": [
                {
                    "article": "OC471",
                    "manufacturer": {"name": "KNECHT|MAHLE", "id": 34},
                    "goodsName": "Фильтр масляный",
                    "imageUrl": "https://img.example.com/oc471.jpg",
                },
                {
                    "article": "OC471",
                    "manufacturer": {"name": "BOSCH", "id": 10},
                    "goodsName": "Filter ol",
                },
            ],
        }
        mock_mnf_response.raise_for_status = MagicMock()

        mock_price_ok = MagicMock()
        mock_price_ok.status_code = 200
        mock_price_ok.json.return_value = {"minimalPrice": 1995.00, "minimalDeliveryDays": 2}

        mock_price_zero = MagicMock()
        mock_price_zero.status_code = 200
        mock_price_zero.json.return_value = {"minimalPrice": 0, "minimalDeliveryDays": 5}

        # Первый вызов — manufacturers, затем два вызова price
        mock_requests.get.side_effect = [
            mock_mnf_response,  # manufacturers
            mock_price_ok,  # price KNECHT|MAHLE
            mock_price_zero,  # price BOSCH
        ]

        spider = PlaywrightPartSpider(article="OC471")
        config = SHOP_CONFIGS["autodoc"]

        async def _run():
            items = []
            async for item in spider._parse_autodoc_api("OC471", config):
                items.append(item)
            return items

        import asyncio

        items = asyncio.get_event_loop().run_until_complete(_run())

        assert len(items) == 2
        assert items[0]["brand"] == "KNECHT|MAHLE"
        assert items[0]["price"] == 1995.00
        assert items[0]["delivery_days"] == 2
        assert items[0]["currency"] == "RUB"
        assert items[0]["shop_name"] == "Autodoc.ru"
        assert items[0]["availability"] == "in_stock"

        assert items[1]["brand"] == "BOSCH"
        assert items[1]["price"] == 0
        assert items[1]["availability"] == "unknown"


# ─── Helper Functions ─────────────────────────────────────────────────────────


class TestParsePrice:
    def test_basic(self):
        assert parse_price("1234") == 1234.0

    def test_with_ruble(self):
        assert parse_price("1 234 ₽") == 1234.0

    def test_comma_decimal(self):
        assert parse_price("1 234,56 ₽") == 1234.56

    def test_empty(self):
        assert parse_price("") == 0.0
        assert parse_price(None) == 0.0

    def test_noise(self):
        assert parse_price("Цена: от 1500 руб.") == 1500.0

    def test_multiple_dots(self):
        # 1.234.56 → 1234.56
        assert parse_price("1.234.56") == 1234.56


class TestParseDeliveryDays:
    def test_basic(self):
        assert parse_delivery_days("3 дня") == 3

    def test_range(self):
        assert parse_delivery_days("2-5 дней") == 2

    def test_empty(self):
        assert parse_delivery_days("") is None
        assert parse_delivery_days(None) is None


# ─── Spider ──────────────────────────────────────────────────────────────────


class TestPlaywrightPartSpider:
    def test_name(self):
        spider = PlaywrightPartSpider(article="OC244")
        assert spider.name == "auto_parts"

    def test_article_normalized(self):
        spider = PlaywrightPartSpider(article="oc-244")
        assert spider.article == "OC-244"

    def test_all_shops_when_not_specified(self):
        spider = PlaywrightPartSpider(article="OC244")
        assert set(spider.shop_keys) == set(SHOP_CONFIGS.keys())

    def test_specific_shops(self):
        spider = PlaywrightPartSpider(article="OC244", shops="exist,emex,fobil")
        assert spider.shop_keys == ["exist", "emex", "fobil"]

    def test_spaces_in_shops(self):
        spider = PlaywrightPartSpider(article="OC244", shops=" exist , emex ")
        assert spider.shop_keys == ["exist", "emex"]

    def test_invalid_shops_filtered(self):
        spider = PlaywrightPartSpider(article="OC244", shops="exist,foobar,emex")
        assert "foobar" not in spider.shop_keys
        assert "exist" in spider.shop_keys
        assert "emex" in spider.shop_keys

    def test_allowed_domains(self):
        assert len(PlaywrightPartSpider.allowed_domains) >= 7

    def test_start_requests(self):
        spider = PlaywrightPartSpider(article="OC244", shops="exist,emex")
        requests = list(spider.start_requests())
        assert len(requests) == 2
        for req in requests:
            assert req.meta["playwright"] is True
            assert req.meta["article"] == "OC244"
            assert "shop_key" in req.meta

    def test_start_requests_url_param(self):
        """Проверяем, что exist генерит GET-запрос к URL с артикулом."""
        spider = PlaywrightPartSpider(article="OC244", shops="exist")
        requests = list(spider.start_requests())
        assert len(requests) == 1
        assert "OC244" in requests[0].url
        assert "exist.ru" in requests[0].url

    def test_start_requests_form_submit(self):
        """Проверяем, что apex генерит GET к базовому без арта в URL."""
        spider = PlaywrightPartSpider(article="OC244", shops="apex")
        requests = list(spider.start_requests())
        assert len(requests) == 1
        assert requests[0].url == "https://apex.ru"
        assert requests[0].callback == spider.submit_search_form

    def test_custom_settings(self):
        assert PlaywrightPartSpider.custom_settings["DOWNLOAD_DELAY"] >= 1
        assert PlaywrightPartSpider.custom_settings["CONCURRENT_REQUESTS"] == 1
