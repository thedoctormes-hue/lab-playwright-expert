"""Конфигурация магазинов автозапчастей для PartSpider.

Каждый магазин описывается словарём:
  - name: уникальный ключ (совпадает с source_name из AutoExpert)
  - display: человекочитаемое название
  - base_url: базовый URL
  - search_url: URL поиска с {article} placeholder
  - selectors: CSS-селекторы для парсинга результатов
  - search_method: url_param, form_submit, или api
"""

from __future__ import annotations


SHOP_CONFIGS: dict[str, dict] = {
    "emex": {
        "display": "Emex.ru",
        "base_url": "https://emex.ru",
        "search_url": "https://emex.ru/search?text={article}",
        "search_method": "url_param",
        "selectors": {
            "result_row": ".result-item, .part-row, table tr",
            "name": ".part-name, td:nth-child(2)",
            "price": ".price, td[class*='price']",
            "url_to_product": "a",
        },
        "health_check_url": "https://www.emex.ru",
    },
    "exist": {
        "display": "Exist.ru",
        "base_url": "https://exist.ru",
        "search_url": "https://exist.ru/Price/?pcode={article}",
        "search_method": "url_param",
        "selectors": {
            "result_row": ".price-wrapper",
            "name": ".caseDescription, .caseBrand",
            "brand": ".caseBrand",
            "price": ".price, .price-wrapper__anchor",
            "delivery": ".delivery-time__list-item",
            "fallback_row": "table tr",
            "fallback_price": "td .price, td[class*='price']",
            "fallback_name": "td:first-child",
        },
        "health_check_url": "https://exist.ru",
    },
    "apex": {
        "display": "Apex.ru",
        "base_url": "https://apex.ru",
        "search_url": None,  # form submit
        "search_method": "form_submit",
        "selectors": {
            "search_input": 'input[name="search_term_string"], input[type="search"]',
            "result_item": ".search-result-item, .product-item, .catalog-item, table tr, .result-row",
            "name": ".name, .title, td:first-child, a",
            "price": ".price, td[class*='price'], span[class*='price'], strong",
        },
        "health_check_url": "https://apex.ru",
    },
    "fobil": {
        "display": "Fobil-Auto.ru",
        "base_url": "https://fobil-auto.ru",
        "search_url": "https://fobil-auto.ru/search?pcode={article}",
        "search_method": "url_param",
        "selectors": {
            "result_row": "tr.startSearching",
            "name": ".caseDescription",
            "brand": ".caseBrand",
            "price": ".casePrices",
        },
        "health_check_url": "https://fobil-auto.ru",
    },
    "autoeuro": {
        "display": "AutoEuro",
        "base_url": "https://shop.autoeuro.ru",
        "search_url": "https://shop.autoeuro.ru/main/search",
        "search_method": "form_submit",
        "selectors": {
            "search_input": 'input[name*="search"], input[type="search"]',
            "result_item": ".search-result-item, .product-item, table tr",
            "name": ".name, td:first-child",
            "price": ".price, td[class*='price']",
        },
        "health_check_url": "https://shop.autoeuro.ru",
    },
    "mymajor": {
        "display": "MyMajor.ru",
        "base_url": "https://mymajor.ru",
        "search_url": None,
        "search_method": "form_submit",
        "selectors": {
            "search_input": 'input[type="search"], input[name*="search"]',
            "result_item": ".search-result-item, .product-item, table tr",
            "name": ".name, td:first-child",
            "price": ".price, td[class*='price']",
        },
        "health_check_url": "https://mymajor.ru",
    },
    "autodoc": {
        "display": "Autodoc.ru",
        "base_url": "https://www.autodoc.ru",
        "search_url": None,
        "search_method": "api",
        "api_base": "https://web.autodoc.ru",
        "selectors": {},
        "health_check_url": "https://www.autodoc.ru",
    },
}

# Порядок — от которых ожидаем больше результатов
SHOP_PRIORITY = ["exist", "emex", "apex", "fobil", "autodoc", "autoeuro", "mymajor"]
