"""
Тесты для ParseCache — TTL-кэш результатов парсинга.

Проверяет: hit, miss, expiry, clear, stats, invalidate.
"""
from __future__ import annotations

import time

import pytest

from lab_playwright_kit.llm_parse import ParseCache


class TestParseCache:
    """Тесты ParseCache."""

    def test_set_and_get(self):
        """Базовый set/get — значение сохраняется и извлекается."""
        cache = ParseCache(ttl=3600)
        cache.set("key1", {"data": "value1"})

        result = cache.get("key1")
        assert result == {"data": "value1"}

    def test_miss(self):
        """get для несуществующего ключа возвращает None."""
        cache = ParseCache(ttl=3600)
        assert cache.get("nonexistent") is None

    def test_expiry(self):
        """Истёкший TTL — get возвращает None."""
        cache = ParseCache(ttl=0)  # TTL = 0, сразу истекает
        cache.set("key1", {"data": "value1"})

        time.sleep(0.05)  # Небольшая задержка для гарантии истечения
        assert cache.get("key1") is None

    def test_clear(self):
        """Clear удаляет все записи и возвращает их количество."""
        cache = ParseCache(ttl=3600)
        cache.set("key1", {"a": 1})
        cache.set("key2", {"b": 2})
        cache.set("key3", {"c": 3})

        count = cache.clear()
        assert count == 3
        assert cache.size == 0

    def test_invalidate(self):
        """Инвалидация конкретного ключа."""
        cache = ParseCache(ttl=3600)
        cache.set("key1", {"a": 1})
        cache.set("key2", {"b": 2})

        assert cache.invalidate("key1") is True
        assert cache.get("key1") is None
        assert cache.get("key2") == {"b": 2}  # Другой ключ не затронут

        # Инвалидация несуществующего ключа
        assert cache.invalidate("nonexistent") is False

    def test_stats(self):
        """Статистика кэша считает hits и misses."""
        cache = ParseCache(ttl=3600)
        cache.set("key1", {"a": 1})

        cache.get("key1")        # hit
        cache.get("nonexistent") # miss
        cache.get("key1")        # hit

        stats = cache.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == pytest.approx(2 / 3)

    def test_stats_empty(self):
        """Hit rate для пустого кэша = 0.0."""
        cache = ParseCache(ttl=3600)
        stats = cache.stats()
        assert stats["hit_rate"] == 0.0

    def test_size(self):
        """Размер кэша отражает количество записей."""
        cache = ParseCache(ttl=3600)
        assert cache.size == 0

        cache.set("a", {"1": 1})
        assert cache.size == 1

        cache.set("b", {"2": 2})
        assert cache.size == 2

        cache.clear()
        assert cache.size == 0

    def test_make_key(self):
        """make_key создаёт детерминированный ключ."""
        key1 = ParseCache.make_key("https://example.com", "все цены", "{}")
        key2 = ParseCache.make_key("https://example.com", "все цены", "{}")
        key3 = ParseCache.make_key("https://other.com", "все цены", "{}")

        assert key1 == key2  # Одинаковые входы = одинаковый ключ
        assert key1 != key3  # Разные URL = разный ключ
        assert len(key1) == 32  # MD5 hex digest

    def test_override_value(self):
        """Повторный set перезаписывает значение."""
        cache = ParseCache(ttl=3600)
        cache.set("key1", {"version": 1})
        cache.set("key1", {"version": 2})

        assert cache.get("key1") == {"version": 2}
        assert cache.size == 1

    def test_expired_entry_removed_from_cache(self):
        """Истёкшая запись физически удаляется из кэша."""
        cache = ParseCache(ttl=0)
        cache.set("key1", {"a": 1})
        time.sleep(0.05)

        cache.get("key1")  # Триггерит очистку
        assert cache.size == 0
