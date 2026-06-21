"""
Extended tests for saas_api.py — SaaS Parsing API (FastAPI app).

Covers: Pydantic models, AppState, create_app factory, endpoints (mocked).
"""

from unittest.mock import MagicMock

from lab_playwright_kit.saas_api import (
    AppState,
    Auth2FARequest,
    AuthCheckRequest,
    AuthLoginRequest,
    AuthResponse,
    BatchParseRequest,
    BatchParseResponse,
    HealthResponse,
    NicheInfo,
    OSINTAccountResponse,
    OSINTPlatformInfo,
    OSINTPlatformsResponse,
    OSINTSearchRequest,
    OSINTSearchResponse,
    ParseRequest,
    ParseResponse,
    PublishRequest,
    PublishResponse,
    StatusResponse,
    create_app,
)


# ─── Pydantic Model Tests ────────────────────────────────────────────────────


class TestParseRequest:
    def test_default_values(self):
        req = ParseRequest(url="https://example.com")
        assert req.url == "https://example.com"
        assert req.niche == ""
        assert req.timeout == 30.0
        assert req.proxy_url == ""
        assert req.wait_for == ""
        assert req.metadata == {}

    def test_custom_values(self):
        req = ParseRequest(
            url="https://habr.com/ru/articles/123/",
            niche="habr",
            timeout=60.0,
            proxy_url="socks5://127.0.0.1:1080",
            wait_for="article",
            metadata={"key": "value"},
        )
        assert req.niche == "habr"
        assert req.timeout == 60.0
        assert req.proxy_url == "socks5://127.0.0.1:1080"
        assert req.wait_for == "article"
        assert req.metadata == {"key": "value"}


class TestBatchParseRequest:
    def test_default_values(self):
        req = BatchParseRequest(urls=["https://a.com", "https://b.com"])
        assert len(req.urls) == 2
        assert req.niche == ""
        assert req.timeout == 30.0
        assert req.max_concurrency == 3
        assert req.delay_between == 1.0

    def test_custom_values(self):
        req = BatchParseRequest(
            urls=["https://a.com"],
            niche="news",
            max_concurrency=5,
            delay_between=2.0,
        )
        assert req.max_concurrency == 5
        assert req.delay_between == 2.0

    def test_min_urls(self):
        """Must have at least 1 URL."""
        req = BatchParseRequest(urls=["https://a.com"])
        assert len(req.urls) == 1


class TestAuthLoginRequest:
    def test_required_fields(self):
        req = AuthLoginRequest(platform="habr", username="user", password="pass")
        assert req.platform == "habr"
        assert req.username == "user"
        assert req.password == "pass"
        assert req.proxy_url == ""
        assert req.force is False

    def test_force_relogin(self):
        req = AuthLoginRequest(platform="habr", username="user", password="pass", force=True)
        assert req.force is True


class TestAuthCheckRequest:
    def test_defaults(self):
        req = AuthCheckRequest(platform="habr")
        assert req.platform == "habr"
        assert req.username == ""

    def test_with_username(self):
        req = AuthCheckRequest(platform="habr", username="testuser")
        assert req.username == "testuser"


class TestAuth2FARequest:
    def test_fields(self):
        req = Auth2FARequest(platform="habr", username="user", code="123456")
        assert req.platform == "habr"
        assert req.code == "123456"


class TestPublishRequest:
    def test_defaults(self):
        req = PublishRequest(platform="habr", content="<p>Hello</p>")
        assert req.platform == "habr"
        assert req.content == "<p>Hello</p>"
        assert req.title == ""
        assert req.dry_run is False

    def test_full(self):
        req = PublishRequest(
            platform="telegraph",
            title="My Post",
            content="<p>Content</p>",
            username="author",
            dry_run=True,
        )
        assert req.title == "My Post"
        assert req.dry_run is True


# ─── Response Model Tests ────────────────────────────────────────────────────


class TestParseResponse:
    def test_creation(self):
        resp = ParseResponse(
            success=True,
            url="https://example.com",
            niche="news",
            data={"title": "Test"},
            confidence=0.9,
            parse_time_ms=150.0,
            page_title="Test Page",
            domain="example.com",
            errors=[],
            parsed_at="2026-01-01T00:00:00",
            request_id="abc123",
        )
        assert resp.success is True
        assert resp.confidence == 0.9
        assert resp.data["title"] == "Test"


class TestBatchParseResponse:
    def test_creation(self):
        resp = BatchParseResponse(
            total=5,
            successful=3,
            failed=2,
            results=[],
            elapsed_seconds=10.5,
            request_id="batch1",
        )
        assert resp.total == 5
        assert resp.successful == 3
        assert resp.failed == 2


class TestPublishResponse:
    def test_success(self):
        resp = PublishResponse(
            success=True,
            platform="habr",
            url="https://habr.com/post/123",
            message="OK",
            elapsed_seconds=5.0,
            error="",
            dry_run=False,
        )
        assert resp.success is True
        assert resp.platform == "habr"

    def test_failure(self):
        resp = PublishResponse(
            success=False,
            platform="habr",
            url="",
            message="",
            error="Auth failed",
            elapsed_seconds=1.0,
            dry_run=False,
        )
        assert resp.success is False


class TestAuthResponse:
    def test_success(self):
        resp = AuthResponse(
            success=True,
            status="authenticated",
            platform="habr",
            username="user",
            message="OK",
            session_name="habr_user",
            cookies_count=5,
            elapsed_seconds=3.0,
            error="",
        )
        assert resp.success is True
        assert resp.cookies_count == 5


class TestNicheInfo:
    def test_creation(self):
        info = NicheInfo(
            name="habr",
            display_name="Habr",
            description="Habr articles",
            fields=["title", "content"],
            url_patterns=["habr.com"],
            required_fields=["title"],
        )
        assert info.name == "habr"
        assert "title" in info.fields


class TestHealthResponse:
    def test_creation(self):
        resp = HealthResponse(
            status="healthy",
            version="2.0.0",
            uptime_seconds=3600.0,
            timestamp="2026-01-01T00:00:00",
        )
        assert resp.status == "healthy"
        assert resp.version == "2.0.0"


class TestStatusResponse:
    def test_creation(self):
        resp = StatusResponse(
            status="running",
            version="2.0.0",
            uptime_seconds=7200.0,
            browser_active=True,
            active_sessions=3,
            available_niches=10,
            available_presets=4,
            proxy_count=2,
            timestamp="2026-01-01T00:00:00",
        )
        assert resp.browser_active is True
        assert resp.active_sessions == 3
        assert resp.available_niches == 10


# ─── OSINT Request/Response Models ──────────────────────────────────────────


class TestOSINTSearchRequest:
    def test_defaults(self):
        req = OSINTSearchRequest(username="testuser")
        assert req.username == "testuser"
        assert req.platforms == []
        assert req.tags == []
        assert req.top_n == 50
        assert req.permute is False
        assert req.timeout == 15.0

    def test_custom(self):
        req = OSINTSearchRequest(
            username="octocat",
            platforms=["github", "twitter"],
            tags=["coding"],
            top_n=20,
            permute=True,
            timeout=30.0,
        )
        assert req.platforms == ["github", "twitter"]
        assert req.permute is True


class TestOSINTAccountResponse:
    def test_creation(self):
        resp = OSINTAccountResponse(
            platform="github",
            username="octocat",
            url="https://github.com/octocat",
            status="claimed",
            confidence=0.9,
            source="search",
            tags=["coding", "social"],
        )
        assert resp.status == "claimed"
        assert resp.confidence == 0.9


class TestOSINTSearchResponse:
    def test_creation(self):
        resp = OSINTSearchResponse(
            query="octocat",
            total_found=5,
            checked=50,
            elapsed_seconds=10.0,
            accounts=[],
        )
        assert resp.total_found == 5
        assert resp.checked == 50


class TestOSINTPlatformInfo:
    def test_creation(self):
        info = OSINTPlatformInfo(
            name="github",
            url_template="https://github.com/{username}",
            check_type="status_code",
            tags=["coding"],
            disabled=False,
        )
        assert info.name == "github"
        assert info.disabled is False


class TestOSINTPlatformsResponse:
    def test_creation(self):
        resp = OSINTPlatformsResponse(total=50, platforms=[])
        assert resp.total == 50


# ─── AppState Tests ─────────────────────────────────────────────────────────


class TestAppState:
    def test_defaults(self):
        state = AppState()
        assert state.browser_manager is None
        assert state.auth_manager is None
        assert state.proxy_manager is None
        assert state.browser_engine == "playwright"
        assert state.browser_humanize is False
        assert state.request_count == 0
        assert state.error_count == 0
        assert state.start_time > 0

    def test_custom(self):
        bm = MagicMock()
        am = MagicMock()
        pm = MagicMock()
        state = AppState(
            browser_manager=bm,
            auth_manager=am,
            proxy_manager=pm,
            browser_engine="cloakbrowser",
            browser_humanize=True,
        )
        assert state.browser_manager is bm
        assert state.auth_manager is am
        assert state.proxy_manager is pm
        assert state.browser_engine == "cloakbrowser"
        assert state.browser_humanize is True


# ─── create_app Factory Tests ────────────────────────────────────────────────


class TestCreateApp:
    def test_create_app_defaults(self):
        """create_app should return a FastAPI app."""
        from fastapi import FastAPI

        app = create_app()
        assert isinstance(app, FastAPI)

    def test_create_app_with_managers(self):
        """create_app with pre-configured managers."""
        from fastapi import FastAPI

        bm = MagicMock()
        am = MagicMock()
        pm = MagicMock()
        app = create_app(
            browser_manager=bm,
            auth_manager=am,
            proxy_manager=pm,
            browser_engine="cloakbrowser",
            browser_humanize=True,
        )
        assert isinstance(app, FastAPI)

    def test_create_app_has_routes(self):
        """App should have all expected routes."""
        app = create_app()
        routes = [r.path for r in app.routes]
        assert "/api/v1/health" in routes
        assert "/api/v1/status" in routes
        assert "/api/v1/parse" in routes
        assert "/api/v1/parse/batch" in routes
        assert "/api/v1/niches" in routes
        assert "/api/v1/auth/login" in routes
        assert "/api/v1/auth/check" in routes
        assert "/api/v1/auth/sessions" in routes

    def test_create_app_cors(self):
        """App should have CORS middleware."""
        app = create_app()
        # FastAPI adds CORSMiddleware to middleware_stack
        middleware_names = [type(m).__name__ for m in app.user_middleware]
        assert any("CORS" in name for name in middleware_names)
