"""
Tests for Distributed Crawler Framework.
Covers: CrawlerConfig, ResultStore, ProxyManager, RateLimiter,
        RobotsHandler, ContentExtractor, URLFilter, PageFetcher.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml


# ─── Setup paths ──────────────────────────────────────────────────────────────
import sys
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from scripts.distributed_crawler import (
    CrawlerConfig,
    ContentExtractor,
    ProxyManager,
    RateLimiter,
    ResultStore,
    RobotsHandler,
    URLFilter,
)


# ═══════════════════════════════════════════════════════════════════════════════
# CrawlerConfig
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrawlerConfig:
    """Tests for CrawlerConfig dataclass and factory methods."""

    def test_default_values(self):
        """Дефолтные значения конфигурации."""
        config = CrawlerConfig()
        assert config.seeds == ["https://example.com"]
        assert config.max_depth == 2
        assert config.max_pages == 50
        assert config.max_pages_per_domain == 0
        assert config.requests_per_second == 1.0
        assert config.delay_range == (1.0, 3.0)
        assert config.respect_robots_txt is True
        assert config.stealth_enabled is True
        assert config.stealth_profile == "casual_reader"
        assert config.stealth_level == "standard"
        assert config.proxy_enabled is False
        assert config.headless is True
        assert config.browser_type == "chromium"
        assert config.page_timeout == 30000
        assert config.output_format == "json"
        assert config.output_directory == "./crawl_output"
        assert config.save_screenshots is False
        assert config.save_html is False
        assert config.workers == 3
        assert config.follow_redirects is True
        assert config.retry_failed is True
        assert config.max_retries == 2
        assert config.dedup_content is True
        assert config.parse_sitemap is True
        assert config.verbose is False

    def test_default_exclude_patterns(self):
        """Дефолтные паттерны исключения."""
        config = CrawlerConfig()
        assert len(config.exclude_patterns) > 0
        combined = " ".join(config.exclude_patterns)
        assert "pdf" in combined
        assert "mailto:" in combined

    def test_from_yaml_full(self):
        """Загрузка полной конфигурации из YAML."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({
                "seeds": ["https://test.com", "https://test2.com"],
                "max_depth": 5,
                "max_pages": 100,
                "max_pages_per_domain": 10,
                "allowed_domains": ["test.com"],
                "excluded_domains": ["evil.com"],
                "url_patterns": [r"https://test\.com/.*"],
                "exclude_patterns": [r"\.(pdf|zip)$"],
                "rate_limit": {
                    "requests_per_second": 2.0,
                    "delay_range": [0.5, 1.5],
                    "respect_robots_txt": False,
                },
                "stealth": {
                    "enabled": False,
                    "profile": "power_user",
                    "level": "full",
                },
                "proxy": {
                    "enabled": True,
                    "file": "my_proxies.txt",
                    "strategy": "random",
                },
                "browser": {
                    "headless": False,
                    "type": "firefox",
                    "timeout": 60000,
                },
                "output": {
                    "format": "both",
                    "directory": "/tmp/test_output",
                    "screenshots": True,
                    "html": True,
                },
                "workers": 5,
                "behavior": {
                    "retry_failed": False,
                    "max_retries": 5,
                },
                "dedup_content": False,
                "parse_sitemap": False,
                "verbose": True,
                "log_file": "crawl.log",
            }, f)
            f.flush()
            config = CrawlerConfig.from_yaml(f.name)
            os.unlink(f.name)

        assert config.seeds == ["https://test.com", "https://test2.com"]
        assert config.max_depth == 5
        assert config.max_pages == 100
        assert config.max_pages_per_domain == 10
        assert config.allowed_domains == ["test.com"]
        assert config.excluded_domains == ["evil.com"]
        assert config.url_patterns == [r"https://test\.com/.*"]
        assert config.exclude_patterns == [r"\.(pdf|zip)$"]
        assert config.requests_per_second == 2.0
        assert config.delay_range == (0.5, 1.5)
        assert config.respect_robots_txt is False
        assert config.stealth_enabled is False
        assert config.stealth_profile == "power_user"
        assert config.stealth_level == "full"
        assert config.proxy_enabled is True
        assert config.proxy_file == "my_proxies.txt"
        assert config.proxy_strategy == "random"
        assert config.headless is False
        assert config.browser_type == "firefox"
        assert config.page_timeout == 60000
        assert config.output_format == "both"
        assert config.output_directory == "/tmp/test_output"
        assert config.save_screenshots is True
        assert config.save_html is True
        assert config.workers == 5
        assert config.retry_failed is False
        assert config.max_retries == 5
        assert config.dedup_content is False
        assert config.parse_sitemap is False
        assert config.verbose is True
        assert config.log_file == "crawl.log"

    def test_from_yaml_empty_file(self):
        """YAML-файл без данных — дефолтные значения."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            f.flush()
            config = CrawlerConfig.from_yaml(f.name)
            os.unlink(f.name)

        assert config.max_depth == 2
        assert config.max_pages == 50
        assert config.seeds == ["https://example.com"]

    def test_from_yaml_partial_override(self):
        """YAML переопределяет только указанные поля."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"max_depth": 10}, f)
            f.flush()
            config = CrawlerConfig.from_yaml(f.name)
            os.unlink(f.name)

        assert config.max_depth == 10
        assert config.max_pages == 50  # default
        assert config.seeds == ["https://example.com"]  # default

    def test_from_args_defaults(self):
        """from_args с минимальными аргументами."""
        args = MagicMock()
        args.config = None
        args.seed = None
        args.depth = None
        args.output = None
        args.stealth = False
        args.verbose = False
        args.workers = None
        args.max_pages = None
        args.proxy = None
        args.headless = None

        config = CrawlerConfig.from_args(args)
        assert config.seeds == ["https://example.com"]
        assert config.max_depth == 2

    def test_from_args_overrides(self):
        """from_args переопределяет значения из CLI."""
        args = MagicMock()
        args.config = None
        args.seed = "https://custom.com"
        args.depth = 7
        args.output = "/tmp/custom"
        args.stealth = True
        args.verbose = True
        args.workers = 10
        args.max_pages = 200
        args.proxy = "proxies.txt"
        args.headless = False

        config = CrawlerConfig.from_args(args)
        assert config.seeds == ["https://custom.com"]
        assert config.max_depth == 7
        assert config.output_directory == "/tmp/custom"
        assert config.stealth_enabled is True
        assert config.verbose is True
        assert config.workers == 10
        assert config.max_pages == 200
        assert config.proxy_enabled is True
        assert config.proxy_file == "proxies.txt"
        assert config.headless is False

    def test_from_args_with_yaml_base(self):
        """from_args с YAML-базой + CLI-переопределениями."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"max_depth": 3, "max_pages": 80}, f)
            f.flush()

            args = MagicMock()
            args.config = f.name
            args.seed = None
            args.depth = 10  # overrides YAML
            args.output = None
            args.stealth = False
            args.verbose = False
            args.workers = None
            args.max_pages = None
            args.proxy = None
            args.headless = None

            config = CrawlerConfig.from_args(args)
            os.unlink(f.name)

        assert config.max_depth == 10  # CLI overrides YAML
        assert config.max_pages == 80  # from YAML

    def test_custom_seeds(self):
        """Кастомные seed URLs."""
        config = CrawlerConfig(seeds=["https://a.com", "https://b.com", "https://c.com"])
        assert len(config.seeds) == 3

    def test_custom_allowed_domains(self):
        """Разрешённые домены."""
        config = CrawlerConfig(allowed_domains=["example.com", "test.org"])
        assert config.allowed_domains == ["example.com", "test.org"]

    def test_custom_excluded_domains(self):
        """Исключённые домены."""
        config = CrawlerConfig(excluded_domains=["spam.com", "ads.net"])
        assert config.excluded_domains == ["spam.com", "ads.net"]


# ═══════════════════════════════════════════════════════════════════════════════
# ResultStore
# ═══════════════════════════════════════════════════════════════════════════════

class TestResultStore:
    """Tests for ResultStore — JSON and SQLite storage."""

    def _make_config(self, fmt="json", dir=None):
        d = dir or tempfile.mkdtemp()
        return CrawlerConfig(output_format=fmt, output_directory=d), d

    def test_json_store_creates_directory(self):
        """ResultStore создаёт выходную директорio."""
        config, out_dir = self._make_config("json")
        try:
            store = ResultStore(config)
            assert Path(out_dir).exists()
            store.close()
        finally:
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_add_result(self):
        """Добавление результата в store."""
        config, out_dir = self._make_config("json")
        try:
            store = ResultStore(config)
            result = {"url": "https://example.com", "title": "Test", "depth": 0}
            store.add_result(result)
            assert store.total_saved == 1
            assert len(store._results) == 1
            store.close()
        finally:
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_add_multiple_results(self):
        """Добавление нескольких результатов."""
        config, out_dir = self._make_config("json")
        try:
            store = ResultStore(config)
            for i in range(5):
                store.add_result({"url": f"https://example.com/{i}", "depth": 0})
            assert store.total_saved == 5
            store.close()
        finally:
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_save_json(self):
        """Сохранение результатов в JSON-файл."""
        config, out_dir = self._make_config("json")
        try:
            store = ResultStore(config)
            store.add_result({
                "url": "https://example.com",
                "title": "Example",
                "domain": "example.com",
                "depth": 0,
                "crawled_at": time.time(),
            })
            path = store.save_json()
            assert Path(path).exists()

            with open(path) as f:
                data = json.load(f)
            assert "crawl_info" in data
            assert "results" in data
            assert data["crawl_info"]["total_pages"] == 1
            assert len(data["results"]) == 1
            store.close()
        finally:
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_save_json_empty(self):
        """Сохранение пустых результатов."""
        config, out_dir = self._make_config("json")
        try:
            store = ResultStore(config)
            path = store.save_json()
            with open(path) as f:
                data = json.load(f)
            assert data["crawl_info"]["total_pages"] == 0
            store.close()
        finally:
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_save_stats(self):
        """Сохранение статистики."""
        config, out_dir = self._make_config("json")
        try:
            store = ResultStore(config)
            stats = {"pages_crawled": 10, "errors": 2, "domains": ["a.com", "b.com"]}
            store.save_stats(stats)

            stats_file = Path(out_dir) / "crawl_stats.json"
            assert stats_file.exists()
            data = json.loads(stats_file.read_text())
            assert data["pages_crawled"] == 10
            store.close()
        finally:
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_sqlite_store(self):
        """SQLite-хранилище создаёт таблицы."""
        config, out_dir = self._make_config("sqlite")
        try:
            store = ResultStore(config)
            assert store._db is not None

            # Проверить таблицы
            cursor = store._db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in cursor.fetchall()}
            assert "pages" in tables
            assert "crawl_stats" in tables
            store.close()
        finally:
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_sqlite_add_result(self):
        """Добавление результата в SQLite."""
        config, out_dir = self._make_config("sqlite")
        try:
            store = ResultStore(config)
            result = {
                "id": "test-001",
                "url": "https://example.com",
                "domain": "example.com",
                "title": "Test Page",
                "text_content": "Hello World",
                "links": [{"href": "https://example.com/1"}],
                "images": [],
                "meta": {"description": "test"},
                "structured": {},
                "depth": 0,
                "status_code": 200,
                "content_hash": "abc123",
                "crawled_at": time.time(),
            }
            store.add_result(result)

            cursor = store._db.execute("SELECT COUNT(*) FROM pages")
            count = cursor.fetchone()[0]
            assert count == 1

            cursor = store._db.execute("SELECT url, title FROM pages WHERE id=?", ("test-001",))
            row = cursor.fetchone()
            assert row[0] == "https://example.com"
            assert row[1] == "Test Page"
            store.close()
        finally:
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_sqlite_save_stats(self):
        """Сохранение статистики в SQLite."""
        config, out_dir = self._make_config("sqlite")
        try:
            store = ResultStore(config)
            store.save_stats({"key1": "value1", "key2": 42})

            cursor = store._db.execute("SELECT value FROM crawl_stats WHERE key=?", ("key1",))
            row = cursor.fetchone()
            assert row[0] == "value1"
            store.close()
        finally:
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_both_format(self):
        """Формат 'both' — JSON + SQLite."""
        config, out_dir = self._make_config("both")
        try:
            store = ResultStore(config)
            assert store._db is not None
            store.add_result({
                "url": "https://example.com",
                "domain": "example.com",
                "title": "Test",
                "depth": 0,
                "crawled_at": time.time(),
            })
            store.save_json()

            # Проверить JSON
            json_path = Path(out_dir) / "crawl_results.json"
            assert json_path.exists()

            # Проверить SQLite
            cursor = store._db.execute("SELECT COUNT(*) FROM pages")
            assert cursor.fetchone()[0] == 1
            store.close()
        finally:
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_total_saved_property(self):
        """Свойство total_saved."""
        config, out_dir = self._make_config("json")
        try:
            store = ResultStore(config)
            assert store.total_saved == 0
            store.add_result({"url": "https://a.com"})
            assert store.total_saved == 1
            store.add_result({"url": "https://b.com"})
            assert store.total_saved == 2
            store.close()
        finally:
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ProxyManager
# ═══════════════════════════════════════════════════════════════════════════════

class TestProxyManager:
    """Tests for ProxyManager."""

    def _make_config(self, enabled=False, proxy_file="proxies.txt", strategy="round_robin"):
        return CrawlerConfig(
            proxy_enabled=enabled,
            proxy_file=proxy_file,
            proxy_strategy=strategy,
        )

    def test_disabled_proxy(self):
        """Прокси отключен — load возвращает False."""
        config = self._make_config(enabled=False)
        pm = ProxyManager(config)
        assert pm.load() is False
        assert pm.is_loaded is False

    def test_missing_proxy_file(self):
        """Файл прокси не найден — load возвращает False."""
        config = self._make_config(enabled=True, proxy_file="/nonexistent/proxies.txt")
        pm = ProxyManager(config)
        assert pm.load() is False
        assert pm.is_loaded is False

    def test_load_proxies(self):
        """Загрузка прокси из файла."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("# Comment line\n")
            f.write("http://proxy1:8080\n")
            f.write("http://proxy2:8080\n")
            f.write("socks5://proxy3:1080\n")
            f.write("\n")  # empty line
            f.flush()

            config = self._make_config(enabled=True, proxy_file=f.name)
            pm = ProxyManager(config)
            result = pm.load()
            os.unlink(f.name)

        assert result is True
        assert pm.is_loaded is True

    def test_get_proxy(self):
        """Получение прокси."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("http://proxy1:8080\n")
            f.write("http://proxy2:8080\n")
            f.flush()

            config = self._make_config(enabled=True, proxy_file=f.name)
            pm = ProxyManager(config)
            pm.load()
            os.unlink(f.name)

        proxy = pm.get_proxy()
        assert proxy is not None
        assert "server" in proxy

    def test_get_proxy_when_disabled(self):
        """Получение прокси когда отключено — None."""
        config = self._make_config(enabled=False)
        pm = ProxyManager(config)
        assert pm.get_proxy() is None

    def test_stats(self):
        """Статистика прокси."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("http://proxy1:8080\n")
            f.write("http://proxy2:8080\n")
            f.flush()

            config = self._make_config(enabled=True, proxy_file=f.name)
            pm = ProxyManager(config)
            pm.load()
            os.unlink(f.name)

        stats = pm.stats
        assert "total" in stats
        assert stats["total"] == 2

    def test_stats_when_disabled(self):
        """Статистика когда прокси отключены."""
        config = self._make_config(enabled=False)
        pm = ProxyManager(config)
        stats = pm.stats
        assert stats["total"] == 0

    def test_mark_success(self):
        """Пометить прокси как успешный."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("http://proxy1:8080\n")
            f.flush()

            config = self._make_config(enabled=True, proxy_file=f.name)
            pm = ProxyManager(config)
            pm.load()
            os.unlink(f.name)

        proxy = pm.get_proxy()
        pm.mark_success(proxy)  # Не должно падать

    def test_mark_failed(self):
        """Пометить прокси как неуспешный."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("http://proxy1:8080\n")
            f.flush()

            config = self._make_config(enabled=True, proxy_file=f.name)
            pm = ProxyManager(config)
            pm.load()
            os.unlink(f.name)

        proxy = pm.get_proxy()
        pm.mark_failed(proxy)  # Не должно падать


# ═══════════════════════════════════════════════════════════════════════════════
# RateLimiter
# ═══════════════════════════════════════════════════════════════════════════════

class TestRateLimiter:
    """Tests for RateLimiter."""

    def test_creation(self):
        """Создание rate limiter."""
        config = CrawlerConfig(requests_per_second=2.0)
        rl = RateLimiter(config)
        assert rl._default_limit is not None

    def test_acquire_allows_first_request(self):
        """Первый запрос проходит без задержки."""
        config = CrawlerConfig(requests_per_second=100.0)
        rl = RateLimiter(config)

        start = time.monotonic()
        asyncio.run(rl.acquire("example.com"))
        elapsed = time.monotonic() - start
        assert elapsed < 0.5  # Должен быть мгновенным

    def test_delay(self):
        """Случайная задержка между запросами."""
        config = CrawlerConfig(delay_range=(0.01, 0.02))
        rl = RateLimiter(config)

        start = time.monotonic()
        asyncio.run(rl.delay())
        elapsed = time.monotonic() - start
        assert 0.005 < elapsed < 0.1

    def test_update_from_robots(self):
        """Обновление rate limit из robots.txt."""
        config = CrawlerConfig(requests_per_second=10.0, crawl_delay_from_robots=True)
        rl = RateLimiter(config)

        # До обновления
        limit_before = rl._get_limit("example.com")

        # Обновить из robots.txt
        rl.update_from_robots("example.com", 5.0)

        limit_after = rl._get_limit("example.com")
        assert limit_after.cooldown_seconds >= 5.0

    def test_update_from_robots_disabled(self):
        """Обновление из robots.txt отключено."""
        config = CrawlerConfig(requests_per_second=10.0, crawl_delay_from_robots=False)
        rl = RateLimiter(config)

        rl.update_from_robots("example.com", 5.0)
        limit = rl._get_limit("example.com")
        # Не должно обновиться
        assert limit.cooldown_seconds < 5.0

    def test_per_domain_limits(self):
        """Rate limit разный для разных доменов."""
        config = CrawlerConfig(requests_per_second=1.0)
        rl = RateLimiter(config)

        limit_a = rl._get_limit("a.com")
        limit_b = rl._get_limit("b.com")
        assert limit_a is not limit_b

    def test_same_domain_returns_same_limit(self):
        """Один домен — один rate limit."""
        config = CrawlerConfig(requests_per_second=1.0)
        rl = RateLimiter(config)

        limit1 = rl._get_limit("example.com")
        limit2 = rl._get_limit("example.com")
        assert limit1 is limit2


# ═══════════════════════════════════════════════════════════════════════════════
# RobotsHandler
# ═══════════════════════════════════════════════════════════════════════════════

class TestRobotsHandler:
    """Tests for RobotsHandler."""

    def test_creation(self):
        """Создание handler."""
        rh = RobotsHandler(respect_robots=True, parse_sitemap=True)
        assert rh.respect_robots is True
        assert rh.parse_sitemap is True

    def test_can_fetch_when_disabled(self):
        """can_fetch всегда True когда robots.txt отключен."""
        rh = RobotsHandler(respect_robots=False)
        result = asyncio.run(rh.can_fetch("https://example.com/anything"))
        assert result is True

    def test_get_sitemap_urls_when_disabled(self):
        """get_sitemap_urls пуст когда sitemap отключен."""
        rh = RobotsHandler(parse_sitemap=False)
        result = asyncio.run(rh.get_sitemap_urls("https://example.com"))
        assert result == []

    def test_get_crawl_delay_no_parser(self):
        """get_crawl_delay возвращает None если нет парсера."""
        rh = RobotsHandler()
        result = rh.get_crawl_delay("https://example.com")
        assert result is None

    def test_can_fetch_with_robots(self):
        """can_fetch с загруженным robots.txt — мок через httpx.AsyncClient."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "User-agent: *\nDisallow: /admin/\nSitemap: https://example.com/sitemap.xml\n"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            rh = RobotsHandler(respect_robots=True, parse_sitemap=True)
            result = asyncio.run(rh.can_fetch("https://example.com/page"))
            assert result is True

    def test_can_fetch_blocked_path(self):
        """can_fetch блокирует запрещённый путь."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "User-agent: *\nDisallow: /admin/\n"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            rh = RobotsHandler(respect_robots=True)
            result = asyncio.run(rh.can_fetch("https://example.com/admin/secret"))
            assert result is False


# ═══════════════════════════════════════════════════════════════════════════════
# ContentExtractor
# ═══════════════════════════════════════════════════════════════════════════════

class TestContentExtractor:
    """Tests for ContentExtractor."""

    def test_creation(self):
        """Создание экстрактора."""
        config = CrawlerConfig()
        extractor = ContentExtractor(config)
        assert extractor.config == config

    def test_empty_result(self):
        """Пустой результат при ошибке."""
        config = CrawlerConfig()
        extractor = ContentExtractor(config)
        result = extractor._empty_result("https://example.com", depth=1)

        assert result["url"] == "https://example.com"
        assert result["domain"] == "example.com"
        assert result["depth"] == 1
        assert result["title"] == ""
        assert result["text_content"] == ""
        assert result["links"] == []
        assert result["images"] == []
        assert result["content_hash"] == ""
        assert "id" in result
        assert "crawled_at" in result

    def test_empty_result_with_error(self):
        """Пустой результат с ошибкой."""
        config = CrawlerConfig()
        extractor = ContentExtractor(config)
        result = extractor._empty_result("https://example.com", depth=0, error="timeout")

        assert result["error"] == "timeout"

    def test_extract_links(self):
        """Извлечение ссылок из результата."""
        config = CrawlerConfig()
        extractor = ContentExtractor(config)
        result = {
            "links": [
                {"href": "https://example.com/1"},
                {"href": "https://example.com/2"},
                {"href": ""},
                {"no_href": "skip"},
            ]
        }
        links = extractor.extract_links(result)
        assert "https://example.com/1" in links
        assert "https://example.com/2" in links

    def test_extract_links_empty(self):
        """Извлечение ссылок из пустого результата."""
        config = CrawlerConfig()
        extractor = ContentExtractor(config)
        links = extractor.extract_links({"links": []})
        assert links == []

    def test_extract_links_no_links_key(self):
        """Извлечение ссылок когда нет ключа links."""
        config = CrawlerConfig()
        extractor = ContentExtractor(config)
        links = extractor.extract_links({})
        assert links == []

    @pytest.mark.asyncio
    async def test_extract_with_mock_page(self):
        """Извлечение данных с мок-страницей."""
        config = CrawlerConfig()
        extractor = ContentExtractor(config)

        mock_page = MagicMock()
        mock_content = MagicMock()
        mock_content.url = "https://example.com"
        mock_content.domain = "example.com"
        mock_content.title = "Test Page"
        mock_content.text = "Hello World"
        mock_content.links = [{"href": "https://example.com/1"}]
        mock_content.images = []
        mock_content.meta = {"description": "test"}
        mock_content.structured = {}

        mock_parser = AsyncMock()
        mock_parser.parse = AsyncMock(return_value=mock_content)

        with patch("scripts.distributed_crawler.PageParser", return_value=mock_parser):
            result = await extractor.extract(mock_page, "https://example.com", depth=0)

        assert result["url"] == "https://example.com"
        assert result["title"] == "Test Page"
        assert result["text_content"] == "Hello World"
        assert result["depth"] == 0
        assert "content_hash" in result
        assert "id" in result

    @pytest.mark.asyncio
    async def test_extract_dedup_content(self):
        """Дедупликация контента по хэшу."""
        config = CrawlerConfig(dedup_content=True)
        extractor = ContentExtractor(config)

        mock_page = MagicMock()
        mock_content = MagicMock()
        mock_content.url = "https://example.com"
        mock_content.domain = "example.com"
        mock_content.title = "Test"
        mock_content.text = "Same content"
        mock_content.links = []
        mock_content.images = []
        mock_content.meta = {}
        mock_content.structured = {}

        mock_parser = AsyncMock()
        mock_parser.parse = AsyncMock(return_value=mock_content)

        with patch("scripts.distributed_crawler.PageParser", return_value=mock_parser):
            result1 = await extractor.extract(mock_page, "https://example.com/1", 0)
            result2 = await extractor.extract(mock_page, "https://example.com/2", 0)

        assert result1["content_hash"] == result2["content_hash"]

    @pytest.mark.asyncio
    async def test_extract_dedup_disabled(self):
        """Дедупликация отключена — пустой хэш."""
        config = CrawlerConfig(dedup_content=False)
        extractor = ContentExtractor(config)

        mock_page = MagicMock()
        mock_content = MagicMock()
        mock_content.url = "https://example.com"
        mock_content.domain = "example.com"
        mock_content.title = "Test"
        mock_content.text = "Content"
        mock_content.links = []
        mock_content.images = []
        mock_content.meta = {}
        mock_content.structured = {}

        mock_parser = AsyncMock()
        mock_parser.parse = AsyncMock(return_value=mock_content)

        with patch("scripts.distributed_crawler.PageParser", return_value=mock_parser):
            result = await extractor.extract(mock_page, "https://example.com", 0)

        assert result["content_hash"] == ""


# ═══════════════════════════════════════════════════════════════════════════════
# URLFilter
# ═══════════════════════════════════════════════════════════════════════════════

class TestURLFilter:
    """Tests for URLFilter."""

    def _make_config(self, **kwargs):
        defaults = {
            "max_depth": 2,
            "allowed_domains": [],
            "excluded_domains": [],
            "url_patterns": [],
            "exclude_patterns": [
                r"\.(pdf|jpg|jpeg|png|gif|svg|css|js|zip|tar|gz|mp3|mp4|avi|mov|doc|docx|xls|xlsx)$",
                r"mailto:",
                r"tel:",
                r"#",
            ],
        }
        defaults.update(kwargs)
        return CrawlerConfig(**defaults)

    def test_allows_valid_http(self):
        """Разрешить валидный HTTP URL."""
        config = self._make_config()
        uf = URLFilter(config)
        assert uf.should_crawl("https://example.com/page", 0) is True

    def test_blocks_exceeded_depth(self):
        """Заблочить URL при превышении глубины."""
        config = self._make_config(max_depth=2)
        uf = URLFilter(config)
        assert uf.should_crawl("https://example.com/page", 2) is False

    def test_allows_at_max_depth(self):
        """Разрешить URL на максимальной глубине (depth < max_depth)."""
        config = self._make_config(max_depth=3)
        uf = URLFilter(config)
        assert uf.should_crawl("https://example.com/page", 2) is True

    def test_blocks_non_http_schemes(self):
        """Заблочить не HTTP/HTTPS схемы."""
        config = self._make_config()
        uf = URLFilter(config)
        assert uf.should_crawl("ftp://example.com/file", 0) is False
        assert uf.should_crawl("file:///etc/passwd", 0) is False

    def test_blocks_excluded_domains(self):
        """Заблочить исключённые домены."""
        config = self._make_config(excluded_domains=["spam.com", "ads.net"])
        uf = URLFilter(config)
        assert uf.should_crawl("https://spam.com/page", 0) is False
        assert uf.should_crawl("https://sub.spam.com/page", 0) is False
        assert uf.should_crawl("https://example.com/page", 0) is True

    def test_allowed_domains_whitelist(self):
        """Белый список доменов."""
        config = self._make_config(allowed_domains=["example.com", "test.org"])
        uf = URLFilter(config)
        assert uf.should_crawl("https://example.com/page", 0) is True
        assert uf.should_crawl("https://test.org/page", 0) is True
        assert uf.should_crawl("https://other.com/page", 0) is False

    def test_blocks_excluded_patterns(self):
        """Заблочить URL по паттернам исключения."""
        config = self._make_config()
        uf = URLFilter(config)
        assert uf.should_crawl("https://example.com/file.pdf", 0) is False
        assert uf.should_crawl("https://example.com/image.jpg", 0) is False
        assert uf.should_crawl("https://example.com/script.js", 0) is False
        assert uf.should_crawl("https://example.com/style.css", 0) is False

    def test_blocks_mailto(self):
        """Заблочить mailto: ссылки."""
        config = self._make_config()
        uf = URLFilter(config)
        assert uf.should_crawl("mailto:test@example.com", 0) is False

    def test_blocks_tel(self):
        """Заблочить tel: ссылки."""
        config = self._make_config()
        uf = URLFilter(config)
        assert uf.should_crawl("tel:+1234567890", 0) is False

    def test_blocks_fragments(self):
        """Заблочить URL с фрагментом."""
        config = self._make_config()
        uf = URLFilter(config)
        assert uf.should_crawl("https://example.com/page#section", 0) is False

    def test_url_patterns_whitelist(self):
        """Включающие паттерны — только совпавшие URL."""
        config = self._make_config(url_patterns=[r"https://example\.com/blog/.*"])
        uf = URLFilter(config)
        assert uf.should_crawl("https://example.com/blog/post-1", 0) is True
        assert uf.should_crawl("https://example.com/about", 0) is False

    def test_empty_allowed_domains_allows_all(self):
        """Пустой allowed_domains — разрешить все."""
        config = self._make_config(allowed_domains=[])
        uf = URLFilter(config)
        assert uf.should_crawl("https://any-domain.com/page", 0) is True

    def test_depth_zero_allows(self):
        """Глубина 0 — разрешить (0 < max_depth)."""
        config = self._make_config(max_depth=1)
        uf = URLFilter(config)
        assert uf.should_crawl("https://example.com/", 0) is True
