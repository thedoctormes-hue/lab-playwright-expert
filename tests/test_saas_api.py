"""
Tests for SaaS Parsing API.
Covers: Pydantic models, endpoints (with mocked browser), app factory.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from lab_playwright_kit.saas_api import (
    AppState,
    AuthCheckRequest,
    AuthLoginRequest,
    Auth2FARequest,
    BatchParseRequest,
    ParseRequest,
    PublishRequest,
    create_app,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_browser_manager():
    """Мок BrowserManager."""
    bm = MagicMock()
    bm.new_page = AsyncMock()
    bm.close = AsyncMock()
    return bm


@pytest.fixture
def mock_auth_manager():
    """Мок BrowserAuthManager."""
    am = MagicMock()
    am.login = AsyncMock()
    am.check_auth = AsyncMock(return_value=False)
    am.handle_2fa = AsyncMock()
    am.list_sessions.return_value = []
    am.delete_session = MagicMock()
    return am


@pytest.fixture
def mock_proxy_manager():
    """Мок VPNProxyManager."""
    pm = MagicMock()
    pm.list_proxies.return_value = []
    return pm


@pytest.fixture
def app(mock_browser_manager, mock_auth_manager, mock_proxy_manager):
    """FastAPI app с моками."""
    return create_app(
        browser_manager=mock_browser_manager,
        auth_manager=mock_auth_manager,
        proxy_manager=mock_proxy_manager,
    )


@pytest.fixture
def client(app):
    """TestClient."""
    return TestClient(app)


# ─── Pydantic Models Tests ───────────────────────────────────────────────────

class TestParseRequest:
    def test_defaults(self):
        r = ParseRequest(url="https://example.com")
        assert r.niche == ""
        assert r.timeout == 30.0
        assert r.proxy_url == ""
        assert r.wait_for == ""
        assert r.metadata == {}

    def test_custom(self):
        r = ParseRequest(
            url="https://habr.com/ru/articles/123/",
            niche="habr",
            timeout=60.0,
            proxy_url="socks5://localhost:1080",
        )
        assert r.niche == "habr"
        assert r.timeout == 60.0


class TestBatchParseRequest:
    def test_defaults(self):
        r = BatchParseRequest(urls=["https://example.com"])
        assert r.niche == ""
        assert r.timeout == 30.0
        assert r.max_concurrency == 3
        assert r.delay_between == 1.0

    def test_min_urls(self):
        with pytest.raises(Exception):
            BatchParseRequest(urls=[])

    def test_max_concurrency_range(self):
        with pytest.raises(Exception):
            BatchParseRequest(urls=["https://example.com"], max_concurrency=0)
        with pytest.raises(Exception):
            BatchParseRequest(urls=["https://example.com"], max_concurrency=11)


class TestAuthLoginRequest:
    def test_required_fields(self):
        r = AuthLoginRequest(platform="habr", username="user", password="pass")
        assert r.force is False
        assert r.proxy_url == ""

    def test_force(self):
        r = AuthLoginRequest(platform="habr", username="user", password="pass", force=True)
        assert r.force is True


class TestAuthCheckRequest:
    def test_defaults(self):
        r = AuthCheckRequest(platform="habr")
        assert r.username == ""


class TestAuth2FARequest:
    def test_required(self):
        r = Auth2FARequest(platform="twitter", username="user", code="123456")
        assert r.code == "123456"


# ─── Health & Status Tests ────────────────────────────────────────────────────

class TestHealthEndpoints:
    def test_health(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "uptime_seconds" in data
        assert "timestamp" in data

    def test_status(self, client):
        resp = client.get("/api/v1/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert "browser_active" in data
        assert "active_sessions" in data
        assert "available_niches" in data
        assert "available_presets" in data
        assert data["available_niches"] == 10
        assert data["available_presets"] == 5


# ─── Niches Tests ────────────────────────────────────────────────────────────

class TestNichesEndpoints:
    def test_list_niches(self, client):
        resp = client.get("/api/v1/niches")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 10

    def test_niche_has_required_fields(self, client):
        resp = client.get("/api/v1/niches")
        data = resp.json()
        for niche in data:
            assert "name" in niche
            assert "display_name" in niche
            assert "fields" in niche
            assert "url_patterns" in niche
            assert "required_fields" in niche

    def test_get_niche_habr(self, client):
        resp = client.get("/api/v1/niches/habr")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "habr"
        assert "title" in data["fields"]
        assert "content" in data["fields"]
        assert "author" in data["fields"]

    def test_get_niche_vcru(self, client):
        resp = client.get("/api/v1/niches/vcru")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "vcru"

    def test_get_niche_twitter(self, client):
        resp = client.get("/api/v1/niches/twitter")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "twitter"

    def test_get_niche_telegram(self, client):
        resp = client.get("/api/v1/niches/telegram")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "telegram"

    def test_get_niche_not_found(self, client):
        resp = client.get("/api/v1/niches/nonexistent")
        assert resp.status_code == 404


# ─── Auth Tests ──────────────────────────────────────────────────────────────

class TestAuthEndpoints:
    def test_login(self, client, mock_auth_manager):
        from lab_playwright_kit.browser_auth import AuthResult, AuthResultStatus
        mock_auth_manager.login.return_value = AuthResult(
            status=AuthResultStatus.SUCCESS,
            platform="habr",
            username="test@example.com",
            message="OK",
            session_name="habr_test@example.com",
            cookies_count=10,
            elapsed_seconds=3.5,
        )

        resp = client.post("/api/v1/auth/login", json={
            "platform": "habr",
            "username": "test@example.com",
            "password": "secret",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["status"] == "success"
        assert data["platform"] == "habr"

    def test_login_missing_fields(self, client):
        resp = client.post("/api/v1/auth/login", json={
            "platform": "habr",
        })
        assert resp.status_code == 422

    def test_check_auth(self, client, mock_auth_manager):
        mock_auth_manager.check_auth.return_value = True
        resp = client.post("/api/v1/auth/check", json={
            "platform": "habr",
            "username": "test@example.com",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["status"] == "authenticated"

    def test_check_auth_not_authenticated(self, client, mock_auth_manager):
        mock_auth_manager.check_auth.return_value = False
        resp = client.post("/api/v1/auth/check", json={
            "platform": "habr",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_2fa(self, client, mock_auth_manager):
        from lab_playwright_kit.browser_auth import AuthResult, AuthResultStatus
        mock_auth_manager.handle_2fa.return_value = AuthResult(
            status=AuthResultStatus.SUCCESS,
            platform="twitter",
            username="user",
            message="2FA OK",
            session_name="twitter_user",
            cookies_count=15,
            elapsed_seconds=2.0,
        )

        resp = client.post("/api/v1/auth/2fa", json={
            "platform": "twitter",
            "username": "user",
            "code": "123456",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_list_sessions(self, client, mock_auth_manager):
        mock_auth_manager.list_sessions.return_value = ["habr_user1", "vcru_user1"]
        resp = client.get("/api/v1/auth/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    def test_list_sessions_filtered(self, client, mock_auth_manager):
        mock_auth_manager.list_sessions.return_value = ["habr_user1"]
        resp = client.get("/api/v1/auth/sessions?platform=habr")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_delete_session(self, client, mock_auth_manager):
        resp = client.delete("/api/v1/auth/sessions/habr/test@example.com")
        assert resp.status_code == 200
        mock_auth_manager.delete_session.assert_called_once_with("habr", "test@example.com")

    def test_list_presets(self, client):
        resp = client.get("/api/v1/auth/presets")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        names = [p["name"] for p in data["presets"]]
        assert "habr" in names
        assert "vcru" in names
        assert "twitter" in names
        assert "telegram" in names


# ─── Parse Tests (mocked browser) ────────────────────────────────────────────

class TestParseEndpoints:
    def test_parse_invalid_niche(self, client):
        resp = client.post("/api/v1/parse", json={
            "url": "https://example.com",
            "niche": "nonexistent",
        })
        assert resp.status_code == 400

    def test_parse_missing_url(self, client):
        resp = client.post("/api/v1/parse", json={})
        assert resp.status_code == 422

    def test_batch_too_many_urls(self, client):
        urls = [f"https://example.com/{i}" for i in range(51)]
        resp = client.post("/api/v1/parse/batch", json={"urls": urls})
        assert resp.status_code == 422

    def test_batch_empty_urls(self, client):
        resp = client.post("/api/v1/parse/batch", json={"urls": []})
        assert resp.status_code == 422


# ─── App Factory Tests ───────────────────────────────────────────────────────

class TestAppFactory:
    def test_create_app_with_managers(self, mock_browser_manager, mock_auth_manager):
        app = create_app(
            browser_manager=mock_browser_manager,
            auth_manager=mock_auth_manager,
        )
        assert app is not None

    def test_create_app_without_managers(self):
        """App создаётся без менеджеров — они создадутся при startup."""
        app = create_app()
        assert app is not None

    def test_cors_headers(self, client):
        resp = client.options("/api/v1/health", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        })
        assert resp.status_code in (200, 204)


# ─── AppState Tests ──────────────────────────────────────────────────────────

class TestAppState:
    def test_defaults(self):
        s = AppState()
        assert s.browser_manager is None
        assert s.auth_manager is None
        assert s.proxy_manager is None
        assert s.request_count == 0
        assert s.error_count == 0
        assert s.start_time > 0

    def test_with_managers(self, mock_browser_manager, mock_auth_manager, mock_proxy_manager):
        s = AppState(
            browser_manager=mock_browser_manager,
            auth_manager=mock_auth_manager,
            proxy_manager=mock_proxy_manager,
        )
        assert s.browser_manager is mock_browser_manager
        assert s.auth_manager is mock_auth_manager
        assert s.proxy_manager is mock_proxy_manager


# ─── Publish Request ────────────────────────────────────────────────────────

class TestPublishRequest:
    def test_required_fields(self):
        r = PublishRequest(platform="habr", content="Test content")
        assert r.platform == "habr"
        assert r.content == "Test content"
        assert r.title == ""
        assert r.username == ""
        assert r.proxy_url == ""
        assert r.timeout == 60.0
        assert r.dry_run is False

    def test_all_fields(self):
        r = PublishRequest(
            platform="vcru",
            title="Title",
            content="Content",
            username="user@test.com",
            proxy_url="socks5://127.0.0.1:1080",
            timeout=90.0,
            dry_run=True,
        )
        assert r.platform == "vcru"
        assert r.title == "Title"
        assert r.content == "Content"
        assert r.username == "user@test.com"
        assert r.proxy_url == "socks5://127.0.0.1:1080"
        assert r.timeout == 90.0
        assert r.dry_run is True

    def test_default_values(self):
        """Пустые строки допустимы для title/username/proxy_url."""
        r = PublishRequest(platform="habr", content="Test")
        assert r.title == ""
        assert r.username == ""
        assert r.proxy_url == ""

    def test_minimal_request(self):
        """Минимальный запрос: только platform + content."""
        r = PublishRequest(platform="vcru", content="Hello")
        assert r.platform == "vcru"
        assert r.content == "Hello"


# ─── Publish Endpoint ────────────────────────────────────────────────────────

class TestPublishEndpoint:
    def test_publish_not_authenticated(self, client, mock_auth_manager):
        """Publish без авторизации возвращает NOT_AUTHENTICATED."""
        mock_auth_manager.check_auth.return_value = False
        resp = client.post("/api/v1/publish", json={
            "platform": "habr",
            "title": "Test",
            "content": "Content",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["error"] == "NOT_AUTHENTICATED"

    def test_publish_dry_run(self, client, mock_auth_manager):
        """Dry run проверяет авторизацию без публикации."""
        mock_auth_manager.check_auth.return_value = True
        resp = client.post("/api/v1/publish", json={
            "platform": "habr",
            "title": "Test",
            "content": "Content",
            "dry_run": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["dry_run"] is True
        assert "Dry run" in data["message"]

    def test_publish_request_validation(self, client):
        """Publish без content возвращает 422."""
        resp = client.post("/api/v1/publish", json={
            "platform": "habr",
        })
        assert resp.status_code == 422

    def test_publish_platform_validation(self, client):
        """Publish без platform возвращает 422."""
        resp = client.post("/api/v1/publish", json={
            "content": "Test",
        })
        assert resp.status_code == 422
