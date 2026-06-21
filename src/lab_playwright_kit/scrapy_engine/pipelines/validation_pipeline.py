"""ValidationPipeline — валидация Scrapy items перед экспортом."""

from __future__ import annotations

import logging

from scrapy.exceptions import DropItem


log = logging.getLogger(__name__)


class ValidationPipeline:
    """Валидация items: проверка обязательных полей, типов, диапазонов."""

    REQUIRED_FIELDS = {
        "ScrapedPage": ["url"],
        "ScrapedProduct": ["url", "title"],
        "ScrapedArticle": ["url", "title"],
        "ScrapedJob": ["url", "title"],
        "ScrapedRealty": ["url", "title"],
        "ScrapedAuto": ["url", "title"],
        "ScrapedContract": ["url"],
    }

    def process_item(self, item, spider):
        """Проверить item на валидность."""
        try:
            item_name = type(item).__name__

            # Проверка обязательных полей
            required = self.REQUIRED_FIELDS.get(item_name, [])
            for field_name in required:
                value = item.get(field_name)
                if not value:
                    raise DropItem(
                        f"{item_name}: missing required field '{field_name}' "
                        f"for {item.get('url', 'unknown')}"
                    )

            # Валидация цен (должны быть >= 0)
            if "price" in item.fields and item.get("price") is not None:
                try:
                    price = float(item["price"])
                    if price < 0:
                        item["price"] = 0
                except (ValueError, TypeError):
                    item["price"] = None

            return item
        except DropItem:
            raise
        except Exception as e:
            log.error("Validation error: %s", e)
            return item
