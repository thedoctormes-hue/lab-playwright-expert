"""
Tests for BrowserAuthManager module.
Covers: AuthResult, AuthPreset, BrowserAuthManager (unit-level with mocks).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from lab_playwright_kit.browser_auth import (
    AUTH_PRESETS,
    HABR_AUTH_PRESET,
    VCRU_AUTH_PRESET,
    TWITTER_AUTH_PRESET,
    TELEGRAM_AUTH_PRESET,
    AuthPreset,
    AuthResult,
    AuthResultStatus,
    BrowserAuthManager,
)


# ─── AuthResult Tests ────────────────────────────────────────────────────────

class TestAuthResult:
    """Тесты AuthResult dataclass."""

    def test_success_status(self):
        r = AuthResult(status=AuthResultStatus.SUCCESS)
        assert r.success is True

    def test_already_auth_status(self):
        r = AuthResult(status=AuthResultStatus.ALREADY_AUTH)
        assert r.success is True

    def test_failed_status(self):
        r = AuthResult(status=AuthResultStatus.FAILED)
        assert r.success is False

    def test_captcha_status(self):
        r = AuthResult(status=AuthResultStatus.CAPTCHA)
        assert r.success is False

    def test_two_fa_status(self):
        r = AuthResult(status=AuthResultStatus.TWO_FA)
        assert r.success is False

    def test_blocked_status(self):
        r = AuthResult(status=AuthResultStatus.BLOCKED)
        assert r.success is False

    def test_no_credentials_status(self):
        r = AuthResult(status=AuthResultStatus.NO_CREDENTIALS)
        assert r.success is False

    def test_session_expired_status(self):
        r = AuthResult(status=AuthResultStatus.SESSION_EXPIRED)
        assert r.success is False

    def test_to_dict(self):
        r = AuthResult(
            status=AuthResultStatus.SUCCESS,
            platform="habr",
            username="test@example.com",
            cookies_count=12,
            elapsed_seconds=3.5,
        )
        d = r.to_dict()
        assert d["status"] == "success"
        assert d["platform"] == "habr"
        assert d["username"] == "test@example.com"
        assert d["cookies_count"] == 12
        assert d["elapsed_seconds"] == 3.5

    def test_default_values(self):
        r = AuthResult()
        assert r.status == AuthResultStatus.FAILED
        assert r.platform == ""
        assert r.username == ""
        assert r.cookies_count == 0
        assert r.error == ""
        assert r.metadata == {}


# ─── AuthPreset Tests ────────────────────────────────────────────────────────

class TestAuthPreset:
    """Тесты AuthPreset dataclass."""

    def test_habr_preset(self):
        p = HABR_AUTH_PRESET
        assert p.platform == "habr"
        assert "habr.com" in p.login_url
        assert p.username_selector != ""
        assert p.password_selector != ""
        assert p.submit_selector != ""
        assert len(p.auth_selectors) > 0
        assert p.use_human_behavior is True

    def test_vcru_preset(self):
        p = VCRU_AUTH_PRESET
        assert p.platform == "vcru"
        assert "vc.ru" in p.login_url
        assert p.username_selector != ""
        assert p.password_selector != ""
        assert len(p.auth_selectors) > 0

    def test_twitter_preset(self):
        p = TWITTER_AUTH_PRESET
        assert p.platform == "twitter"
        assert "twitter.com" in p.login_url or "x.com" in p.login_url
        assert p.username_selector != ""
        assert p.password_selector != ""
        assert p.post_login_wait >= 5.0
        assert len(p.pre_login_actions) > 0

    def test_telegram_preset(self):
        p = TELEGRAM_AUTH_PRESET
        assert p.platform == "telegram"
        assert "telegram" in p.login_url
        assert p.username_selector != ""
        assert p.use_human_behavior is True

    def test_custom_preset(self):
        p = AuthPreset(
            platform="custom",
            login_url="https://example.com/login",
            auth_check_url="https://example.com/dashboard",
            auth_selectors=[".user-menu", ".avatar"],
            username_selector="#email",
            password_selector="#password",
        )
        assert p.platform == "custom"
        assert p.post_login_wait == 3.0  # default
        assert p.use_human_behavior is True  # default


# ─── Preset Registry Tests ───────────────────────────────────────────────────

class TestPresetRegistry:
    """Тесты реестра пресетов."""

    def test_habr_registered(self):
        assert "habr" in AUTH_PRESETS

    def test_vcru_registered(self):
        assert "vcru" in AUTH_PRESETS

    def test_twitter_registered(self):
        assert "twitter" in AUTH_PRESETS

    def test_x_registered(self):
        assert "x" in AUTH_PRESETS

    def test_telegram_registered(self):
        assert "telegram" in AUTH_PRESETS

    def test_all_5_platforms(self):
        expected = {"habr", "vcru", "twitter", "x", "telegram"}
        assert set(AUTH_PRESETS.keys()) == expected

    def test_register_custom_preset(self):
        custom = AuthPreset(
            platform="mysite",
            login_url="https://mysite.com/login",
            auth_check_url="https://mysite.com/home",
            auth_selectors=[".logged-in"],
        )
        BrowserAuthManager.register_preset("mysite", custom)
        try:
            assert "mysite" in AUTH_PRESETS
            assert AUTH_PRESETS["mysite"].login_url == "https://mysite.com/login"
        finally:
            AUTH_PRESETS.pop("mysite", None)

    def test_get_preset(self):
        p = BrowserAuthManager.get_preset("habr")
        assert p is not None
        assert p.platform == "habr"

    def test_get_preset_unknown(self):
        p = BrowserAuthManager.get_preset("nonexistent")
        assert p is None

    def test_list_presets(self):
        presets = BrowserAuthManager.list_presets()
        assert "habr" in presets
        assert "vcru" in presets
        assert "twitter" in presets
        assert "telegram" in presets


# ─── BrowserAuthManager Unit Tests ───────────────────────────────────────────

class TestBrowserAuthManager:
    """Unit-тесты BrowserAuthManager с моками."""

    @pytest.fixture
    def mock_browser_manager(self):
        """Мок BrowserManager."""
        bm = MagicMock()
        bm.new_page = AsyncMock()
        bm.current_page = AsyncMock()
        return bm

    @pytest.fixture
    def mock_account_mgr(self):
        """Мок AccountManager."""
        with patch("lab_playwright_kit.browser_auth.AccountManager") as mock_cls:
            mgr = MagicMock()
            mock_cls.return_value = mgr
            mgr.create_account.return_value = 1
            mgr.get_account.return_value = MagicMock(id=1, platform="habr", username="test@example.com")
            mgr.list_accounts.return_value = []
            yield mgr

    @pytest.fixture
    def mock_session_mgr(self):
        """Мок SessionManager."""
        with patch("lab_playwright_kit.browser_auth.SessionManager") as mock_cls:
            mgr = MagicMock()
            mock_cls.return_value = mgr
            mgr.list_sessions.return_value = []
            mgr.get_session.return_value = None
            mgr.save_session = AsyncMock()
            mgr.load_session = AsyncMock(return_value=False)
            mgr.delete_session = MagicMock()
            yield mgr

    @pytest.fixture
    def auth_mgr(self, mock_browser_manager, mock_account_mgr, mock_session_mgr):
        """BrowserAuthManager с моками."""
        mgr = BrowserAuthManager(
            browser_manager=mock_browser_manager,
            db_path=":memory:",
            session_dir="/tmp/test_sessions",
        )
        return mgr

    def test_init(self, auth_mgr):
        assert auth_mgr._browser_mgr is not None
        assert auth_mgr._account_mgr is not None
        assert auth_mgr._session_mgr is not None
        assert auth_mgr._default_ttl == 86400 * 7

    def test_init_custom_ttl(self, mock_browser_manager, mock_account_mgr, mock_session_mgr):
        mgr = BrowserAuthManager(
            browser_manager=mock_browser_manager,
            default_ttl=3600,
        )
        assert mgr._default_ttl == 3600

    def test_create_account(self, auth_mgr, mock_account_mgr):
        account_id = auth_mgr.create_account(
            platform="habr",
            username="test@example.com",
            password="secret",
        )
        assert account_id == 1
        mock_account_mgr.create_account.assert_called_once()

    def test_create_account_with_metadata(self, auth_mgr, mock_account_mgr):
        auth_mgr.create_account(
            platform="habr",
            username="test@example.com",
            password="secret",
            metadata={"proxy": "socks5://localhost:1080"},
        )
        mock_account_mgr.update_metadata.assert_called_once()

    def test_get_account(self, auth_mgr, mock_account_mgr):
        account = auth_mgr.get_account("habr", "test@example.com")
        assert account is not None
        mock_account_mgr.get_account.assert_called_once_with("habr", "test@example.com")

    def test_list_accounts(self, auth_mgr, mock_account_mgr):
        auth_mgr.list_accounts(platform="habr", status="active")
        mock_account_mgr.list_accounts.assert_called_once_with(platform="habr", status="active")

    def test_list_sessions(self, auth_mgr, mock_session_mgr):
        mock_session_mgr.list_sessions.return_value = ["habr_user1", "habr_user2", "vcru_user1"]
        sessions = auth_mgr.list_sessions()
        assert len(sessions) == 3

    def test_list_sessions_filtered(self, auth_mgr, mock_session_mgr):
        mock_session_mgr.list_sessions.return_value = ["habr_user1", "habr_user2", "vcru_user1"]
        sessions = auth_mgr.list_sessions(platform="habr")
        assert sessions == ["habr_user1", "habr_user2"]

    def test_delete_session(self, auth_mgr, mock_session_mgr):
        auth_mgr.delete_session("habr", "test@example.com")
        mock_session_mgr.delete_session.assert_called_once_with("habr_test@example.com")

    @pytest.mark.asyncio
    async def test_save_session(self, auth_mgr, mock_session_mgr):
        mock_page = MagicMock()
        mock_session_mgr.save_session = AsyncMock()
        name = await auth_mgr.save_session("habr", "test@example.com", page=mock_page)
        assert name == "habr_test@example.com"
        mock_session_mgr.save_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_auth_no_sessions(self, auth_mgr, mock_session_mgr):
        mock_session_mgr.list_sessions.return_value = []
        mock_page = MagicMock()
        auth_mgr._browser_mgr.new_page = AsyncMock(return_value=mock_page)

        # Mock _verify_auth to return False
        with patch.object(auth_mgr, "_verify_auth", new_callable=AsyncMock, return_value=False):
            result = await auth_mgr.check_auth("habr")
            assert result is False

    @pytest.mark.asyncio
    async def test_get_authenticated_page_no_session(self, auth_mgr, mock_session_mgr):
        mock_session_mgr.load_session = AsyncMock(return_value=False)
        mock_page = MagicMock()
        auth_mgr._browser_mgr.new_page = AsyncMock(return_value=mock_page)

        result = await auth_mgr.get_authenticated_page("habr", "test@example.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_handle_2fa_no_selector(self, auth_mgr):
        result = await auth_mgr.handle_2fa("unknown_platform", "user", "123456")
        assert result.status == AuthResultStatus.FAILED
        assert "No 2FA selector" in result.error

    @pytest.mark.asyncio
    async def test_login_no_preset(self, auth_mgr):
        result = await auth_mgr.login("unknown_platform", "user", "pass")
        assert result.status == AuthResultStatus.FAILED
        assert "No auth preset" in result.error

    @pytest.mark.asyncio
    async def test_login_already_authenticated(self, auth_mgr, mock_session_mgr):
        """Если сессия валидна — возвращаем ALREADY_AUTH."""
        mock_session_mgr.list_sessions.return_value = ["habr_test@example.com"]
        mock_session_data = MagicMock()
        mock_session_data.is_expired = False
        mock_session_mgr.get_session.return_value = mock_session_data

        result = await auth_mgr.login("habr", "test@example.com", "pass")
        assert result.status == AuthResultStatus.ALREADY_AUTH

    @pytest.mark.asyncio
    async def test_refresh_session(self, auth_mgr, mock_session_mgr):
        """Refresh = delete + re-login."""
        mock_session_mgr.list_sessions.return_value = []
        mock_session_mgr.delete_session = MagicMock()

        # Mock login to avoid actual browser calls
        with patch.object(auth_mgr, "login", new_callable=AsyncMock) as mock_login:
            mock_login.return_value = AuthResult(
                status=AuthResultStatus.SUCCESS,
                platform="habr",
                username="test@example.com",
            )
            result = await auth_mgr.refresh_session("habr", "test@example.com", "pass")
            mock_session_mgr.delete_session.assert_called_once_with("habr_test@example.com")
            mock_login.assert_called_once()

    def test_accounts_property(self, auth_mgr):
        assert auth_mgr.accounts is auth_mgr._account_mgr

    def test_sessions_property(self, auth_mgr):
        assert auth_mgr.sessions is auth_mgr._session_mgr


# ─── Integration-style Tests ─────────────────────────────────────────────────

class TestAuthPresetFields:
    """Тесты что все пресеты имеют необходимые поля."""

    @pytest.mark.parametrize("name,preset", [
        ("habr", HABR_AUTH_PRESET),
        ("vcru", VCRU_AUTH_PRESET),
        ("twitter", TWITTER_AUTH_PRESET),
        ("telegram", TELEGRAM_AUTH_PRESET),
    ])
    def test_preset_has_login_url(self, name, preset):
        assert preset.login_url.startswith("http"), f"{name}: no login_url"

    @pytest.mark.parametrize("name,preset", [
        ("habr", HABR_AUTH_PRESET),
        ("vcru", VCRU_AUTH_PRESET),
        ("twitter", TWITTER_AUTH_PRESET),
        ("telegram", TELEGRAM_AUTH_PRESET),
    ])
    def test_preset_has_auth_selectors(self, name, preset):
        assert len(preset.auth_selectors) > 0, f"{name}: no auth_selectors"

    @pytest.mark.parametrize("name,preset", [
        ("habr", HABR_AUTH_PRESET),
        ("vcru", VCRU_AUTH_PRESET),
        ("twitter", TWITTER_AUTH_PRESET),
        ("telegram", TELEGRAM_AUTH_PRESET),
    ])
    def test_preset_has_username_selector(self, name, preset):
        assert preset.username_selector, f"{name}: no username_selector"

    @pytest.mark.parametrize("name,preset", [
        ("habr", HABR_AUTH_PRESET),
        ("vcru", VCRU_AUTH_PRESET),
        ("twitter", TWITTER_AUTH_PRESET),
        ("telegram", TELEGRAM_AUTH_PRESET),
    ])
    def test_preset_has_password_selector(self, name, preset):
        assert preset.password_selector, f"{name}: no password_selector"

    @pytest.mark.parametrize("name,preset", [
        ("habr", HABR_AUTH_PRESET),
        ("vcru", VCRU_AUTH_PRESET),
        ("twitter", TWITTER_AUTH_PRESET),
        ("telegram", TELEGRAM_AUTH_PRESET),
    ])
    def test_preset_has_submit_selector(self, name, preset):
        assert preset.submit_selector, f"{name}: no submit_selector"
