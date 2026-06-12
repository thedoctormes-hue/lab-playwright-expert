"""
Tests for Data API (FastAPI) and PostgreSQL integration.
Covers: Database layer, API endpoints (with TestClient), ResultStore PostgreSQL.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


# ═══════════════════════════════════════════════════════════════════════════════
# Database layer tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestDatabase:
    """Тесты Database слоя."""

    def test_sqlite_init(self):
        from scripts.data_api import Database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = Database(f"sqlite:///{f.name}")
            db.connect()
            db.init_schema()
            db.close()
        os.unlink(f.name)

    def test_insert_and_get_result(self):
        from scripts.data_api import Database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = Database(f"sqlite:///{f.name}")
            db.connect()
            db.init_schema()

            result_id = db.insert_result({
                "url": "https://example.com",
                "niche": "ecommerce",
                "domain": "example.com",
                "page_title": "Test",
                "data": {"title": "Product", "price": 99.99},
                "confidence": 0.9,
                "parse_time_ms": 150.0,
                "content_hash": "abc123",
                "errors": [],
            })

            result = db.get_result(result_id)
            assert result is not None
            assert result["url"] == "https://example.com"
            assert result["niche"] == "ecommerce"
            assert result["data"]["title"] == "Product"
            assert result["confidence"] == 0.9

            db.close()
        os.unlink(f.name)

    def test_get_nonexistent(self):
        from scripts.data_api import Database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = Database(f"sqlite:///{f.name}")
            db.connect()
            db.init_schema()

            result = db.get_result("nonexistent-id")
            assert result is None

            db.close()
        os.unlink(f.name)

    def test_list_results(self):
        from scripts.data_api import Database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = Database(f"sqlite:///{f.name}")
            db.connect()
            db.init_schema()

            for i in range(5):
                db.insert_result({
                    "url": f"https://example.com/{i}",
                    "niche": "ecommerce",
                    "domain": "example.com",
                    "data": {"title": f"Product {i}"},
                    "confidence": 0.5 + i * 0.1,
                    "parse_time_ms": 100.0,
                    "content_hash": f"hash{i}",
                    "errors": [],
                })

            results, total = db.list_results()
            assert total == 5
            assert len(results) == 5

            # Pagination
            results, total = db.list_results(page=1, page_size=2)
            assert len(results) == 2

            # Filter by niche
            results, total = db.list_results(niche="ecommerce")
            assert total == 5

            results, total = db.list_results(niche="news")
            assert total == 0

            db.close()
        os.unlink(f.name)

    def test_list_results_with_search(self):
        from scripts.data_api import Database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = Database(f"sqlite:///{f.name}")
            db.connect()
            db.init_schema()

            db.insert_result({
                "url": "https://example.com/1",
                "niche": "ecommerce",
                "domain": "example.com",
                "page_title": "iPhone 15 Pro",
                "data": {"title": "iPhone 15 Pro"},
                "confidence": 0.9,
                "parse_time_ms": 100.0,
                "content_hash": "h1",
                "errors": [],
            })
            db.insert_result({
                "url": "https://example.com/2",
                "niche": "ecommerce",
                "domain": "example.com",
                "page_title": "Samsung Galaxy",
                "data": {"title": "Samsung Galaxy"},
                "confidence": 0.8,
                "parse_time_ms": 100.0,
                "content_hash": "h2",
                "errors": [],
            })

            results, total = db.list_results(search="iPhone")
            assert total == 1

            db.close()
        os.unlink(f.name)

    def test_delete_result(self):
        from scripts.data_api import Database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = Database(f"sqlite:///{f.name}")
            db.connect()
            db.init_schema()

            result_id = db.insert_result({
                "url": "https://example.com",
                "niche": "ecommerce",
                "domain": "example.com",
                "data": {},
                "confidence": 0.5,
                "parse_time_ms": 100.0,
                "content_hash": "",
                "errors": [],
            })

            assert db.delete_result(result_id) is True
            assert db.get_result(result_id) is None
            assert db.delete_result(result_id) is False

            db.close()
        os.unlink(f.name)

    def test_get_stats(self):
        from scripts.data_api import Database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = Database(f"sqlite:///{f.name}")
            db.connect()
            db.init_schema()

            for i in range(3):
                db.insert_result({
                    "url": f"https://shop.com/{i}",
                    "niche": "ecommerce",
                    "domain": "shop.com",
                    "data": {},
                    "confidence": 0.8,
                    "parse_time_ms": 100.0,
                    "content_hash": f"h{i}",
                    "errors": [],
                })

            stats = db.get_stats()
            assert stats["total_results"] == 3
            assert stats["by_niche"]["ecommerce"] == 3
            assert stats["avg_confidence"] > 0

            db.close()
        os.unlink(f.name)

    def test_min_confidence_filter(self):
        from scripts.data_api import Database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = Database(f"sqlite:///{f.name}")
            db.connect()
            db.init_schema()

            db.insert_result({
                "url": "https://example.com/1",
                "niche": "ecommerce",
                "domain": "example.com",
                "data": {},
                "confidence": 0.3,
                "parse_time_ms": 100.0,
                "content_hash": "h1",
                "errors": [],
            })
            db.insert_result({
                "url": "https://example.com/2",
                "niche": "ecommerce",
                "domain": "example.com",
                "data": {},
                "confidence": 0.9,
                "parse_time_ms": 100.0,
                "content_hash": "h2",
                "errors": [],
            })

            results, total = db.list_results(min_confidence=0.5)
            assert total == 1

            db.close()
        os.unlink(f.name)


# ═══════════════════════════════════════════════════════════════════════════════
# FastAPI endpoints tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestAPIEndpoints:
    """Тесты FastAPI endpoints через TestClient."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test client with temp DB."""
        from scripts.data_api import app, db
        from fastapi.testclient import TestClient

        # Override DB to temp file
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()

        from scripts.data_api import Database
        test_db = Database(f"sqlite:///{self._tmp.name}")
        test_db.connect()
        test_db.init_schema()

        # Monkey-patch the global db
        import scripts.data_api as api_module
        self._orig_db = api_module.db
        api_module.db = test_db

        self.client = TestClient(app)
        yield

        # Cleanup
        api_module.db = self._orig_db
        test_db.close()
        os.unlink(self._tmp.name)

    def test_health_check(self):
        response = self.client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "2.0.0"

    def test_list_schemas(self):
        response = self.client.get("/api/v1/schemas")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 6
        niches = [s["niche"] for s in data["schemas"]]
        assert "ecommerce" in niches
        assert "news" in niches

    def test_get_stats_empty(self):
        response = self.client.get("/api/v1/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_results"] == 0

    def test_list_results_empty(self):
        response = self.client.get("/api/v1/results")
        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []
        assert data["total"] == 0

    def test_get_nonexistent_result(self):
        response = self.client.get("/api/v1/results/nonexistent")
        assert response.status_code == 404

    def test_export_json_empty(self):
        response = self.client.get("/api/v1/export/json")
        assert response.status_code == 404

    def test_export_csv_empty(self):
        response = self.client.get("/api/v1/export/csv")
        assert response.status_code == 404

    def test_batch_parse_too_many_urls(self):
        urls = [f"https://example.com/{i}" for i in range(100)]
        response = self.client.post("/api/v1/parse/batch", json={
            "urls": urls,
            "niche": "ecommerce",
        })
        # FastAPI/Pydantic возвращает 422 для validation error
        assert response.status_code in (400, 422)

    def test_batch_parse_valid(self):
        response = self.client.post("/api/v1/parse/batch", json={
            "urls": ["https://example.com/1", "https://example.com/2"],
            "niche": "ecommerce",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["total_urls"] == 2
        assert data["status"] == "pending"
        assert "task_id" in data


# ═══════════════════════════════════════════════════════════════════════════════
# ResultStore PostgreSQL tests (mocked)
# ═══════════════════════════════════════════════════════════════════════════════

class TestResultStorePostgres:
    """Тесты PostgreSQL интеграции в ResultStore."""

    def test_pg_init_without_psycopg2(self):
        """PostgreSQL инициализация без psycopg2 — graceful fallback."""
        from scripts.distributed_crawler import CrawlerConfig, ResultStore

        config = CrawlerConfig()
        config.use_postgresql = True
        config.output_format = "json"

        with patch.dict(sys.modules, {"psycopg2": None}):
            store = ResultStore(config)
            assert store._pg_conn is None
            store.close()

    def test_pg_save_without_connection(self):
        """_save_to_postgresql без подключения — не падает."""
        from scripts.distributed_crawler import CrawlerConfig, ResultStore

        config = CrawlerConfig()
        config.output_format = "json"

        store = ResultStore(config)
        store._pg_conn = None

        # Не должно падать
        store._save_to_postgresql({
            "url": "https://example.com",
            "domain": "example.com",
            "data": {},
        })

        store.close()

    def test_pg_config_from_yaml(self):
        """PostgreSQL конфигурация из YAML."""
        from scripts.distributed_crawler import CrawlerConfig

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            f.write("""
output:
  format: postgresql
proxy:
  enabled: false
""")
            f.flush()

            config = CrawlerConfig.from_yaml(f.name)
            assert config.output_format == "postgresql"

        os.unlink(f.name)
