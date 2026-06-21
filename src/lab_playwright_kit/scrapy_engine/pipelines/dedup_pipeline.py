"""DedupPipeline — дедупликация Scrapy items по URL."""

from __future__ import annotations

import logging

from scrapy.exceptions import DropItem


log = logging.getLogger(__name__)


class DedupPipeline:
    """Дедупликация по URL. Хранит множество обработанных URL в памяти."""

    def __init__(self):
        self._seen_urls: set[str] = set()

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_item(self, item, spider):
        """Проверить URL на дубликат."""
        try:
            url = item.get("url")
            if url:
                normalized = url.rstrip("#").rstrip("?").lower()
                if normalized in self._seen_urls:
                    raise DropItem(f"Duplicate URL: {url}")
                self._seen_urls.add(normalized)
            return item
        except DropItem:
            raise
        except Exception as e:
            log.error("Dedup error: %s", e)
            return item
