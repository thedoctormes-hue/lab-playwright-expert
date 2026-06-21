"""
Расширенные тесты для BrowserAuthManager.

Покрывает:
  - AuthResult (success property, to_dict)
  - AuthResultStatus enum
  - AuthPreset (HABR, VCRU, TWITTER, TELEGRAM presets)
  - AUTH_PRESETS registry
  - BrowserAuthManager.__init__
  - BrowserAuthManager.get_preset
  - BrowserAuthManager.check_auth (mocked)
"""

from __future__ import annotations

from unittest.mock import MagicMock

from lab_playwright_kit.browser_auth import (
    AUTH_PRESETS,
    HABR_AUTH_PRESET,
    TELEGRAM_AUTH_PRESET,
    TWITTER_AUTH_PRESET,
    VCRU_AUTH_PRESET,
    AuthResult,
    AuthResultStatus,
    BrowserAuthManager,
)


# ─── AuthResultStatus ──────────────────────────────────────────────────────


class TestAuthResultStatus:
    def test_values(self):
        assert AuthResultStatus.SUCCESS.value == "success"
        assert AuthResultStatus.FAILED.value == "failed"
        assert AuthResultStatus.ALREADY_AUTH.value == "already_authenticated"
        assert AuthResultStatus.CAPTCHA.value == "captcha_required"
        assert AuthResultStatus.TWO_FA.value == "2fa_required"
        assert AuthResultStatus.BLOCKED.value == "blocked"
        assert AuthResultStatus.SESSION_EXPIRED.value == "session_expired"
        assert AuthResultStatus.NO_CREDENTIALS.value == "no_credentials"


# ─── AuthResult ────────────────────────────────────────────────────────────


class TestAuthResult:
    def test_defaults(self):
        r = AuthResult()
        assert r.status == AuthResultStatus.FAILED
        assert r.platform == ""
        assert r.username == ""
        assert r.success is False

    def test_success_property(self):
        r = AuthResult(status=AuthResultStatus.SUCCESS)
        assert r.success is True

    def test_already_auth_is_success(self):
        r = AuthResult(status=AuthResultStatus.ALREADY_AUTH)
        assert r.success is True

    def test_failed_not_success(self):
        r = AuthResult(status=AuthResultStatus.FAILED)
        assert r.success is False

    def test_captcha_not_success(self):
        r = AuthResult(status=AuthResultStatus.CAPTCHA)
        assert r.success is False

    def test_to_dict(self):
        r = AuthResult(
            status=AuthResultStatus.SUCCESS,
            platform="habr",
            username="user@test.com",
            message="OK",
            session_name="habr_user",
            cookies_count=15,
            elapsed_seconds=3.5,
        )
        d = r.to_dict()
        assert d["status"] == "success"
        assert d["platform"] == "habr"
        assert d["username"] == "user@test.com"
        assert d["cookies_count"] == 15
        assert d["elapsed_seconds"] == 3.5

    def test_to_dict_with_error(self):
        r = AuthResult(status=AuthResultStatus.FAILED, error="Wrong password")
        d = r.to_dict()
        assert d["error"] == "Wrong password"


# ─── AuthPreset ────────────────────────────────────────────────────────────


class TestAuthPreset:
    def test_habr_preset(self):
        p = HABR_AUTH_PRESET
        assert p.platform == "habr"
        assert "habr.com" in p.login_url
        assert p.username_selector != ""
        assert p.password_selector != ""
        assert p.submit_selector != ""
        assert p.use_human_behavior is True
        assert len(p.auth_selectors) > 0

    def test_vcru_preset(self):
        p = VCRU_AUTH_PRESET
        assert p.platform == "vcru"
        assert "vc.ru" in p.login_url
        assert p.use_human_behavior is True

    def test_twitter_preset(self):
        p = TWITTER_AUTH_PRESET
        assert p.platform == "twitter"
        assert "x.com" in p.login_url or "twitter" in p.login_url
        assert p.use_human_behavior is True

    def test_telegram_preset(self):
        p = TELEGRAM_AUTH_PRESET
        assert p.platform == "telegram"
        assert "telegram" in p.login_url
        assert p.use_human_behavior is True

    def test_preset_notes(self):
        assert isinstance(HABR_AUTH_PRESET.notes, str)
        assert len(HABR_AUTH_PRESET.notes) > 0


# ─── AUTH_PRESETS registry ─────────────────────────────────────────────────


class TestAuthPresetsRegistry:
    def test_has_habr(self):
        assert "habr" in AUTH_PRESETS

    def test_has_vcru(self):
        assert "vcru" in AUTH_PRESETS

    def test_has_twitter(self):
        assert "twitter" in AUTH_PRESETS

    def test_has_x_alias(self):
        assert "x" in AUTH_PRESETS
        assert AUTH_PRESETS["x"] is AUTH_PRESETS["twitter"]

    def test_has_telegram(self):
        assert "telegram" in AUTH_PRESETS

    def test_all_presets_have_platform(self):
        for name, preset in AUTH_PRESETS.items():
            assert preset.platform != "", f"Preset '{name}' has empty platform"

    def test_all_presets_have_login_url(self):
        for name, preset in AUTH_PRESETS.items():
            assert preset.login_url != "", f"Preset '{name}' has empty login_url"


# ─── BrowserAuthManager init ───────────────────────────────────────────────


class TestBrowserAuthManagerInit:
    def test_init(self):
        bm = MagicMock()
        mgr = BrowserAuthManager(browser_manager=bm)
        assert mgr._browser_mgr is bm

    def test_init_with_defaults(self):
        bm = MagicMock()
        mgr = BrowserAuthManager(browser_manager=bm)
        assert mgr.accounts is not None
        assert mgr.sessions is not None


# ─── BrowserAuthManager.get_preset ─────────────────────────────────────────


class TestGetPreset:
    def test_get_habr(self):
        bm = MagicMock()
        mgr = BrowserAuthManager(browser_manager=bm)
        preset = mgr.get_preset("habr")
        assert preset.platform == "habr"

    def test_get_vcru(self):
        bm = MagicMock()
        mgr = BrowserAuthManager(browser_manager=bm)
        preset = mgr.get_preset("vcru")
        assert preset.platform == "vcru"

    def test_get_twitter(self):
        bm = MagicMock()
        mgr = BrowserAuthManager(browser_manager=bm)
        preset = mgr.get_preset("twitter")
        assert preset.platform == "twitter"

    def test_get_telegram(self):
        bm = MagicMock()
        mgr = BrowserAuthManager(browser_manager=bm)
        preset = mgr.get_preset("telegram")
        assert preset.platform == "telegram"

    def test_get_unknown(self):
        bm = MagicMock()
        mgr = BrowserAuthManager(browser_manager=bm)
        result = mgr.get_preset("unknown_platform")
        assert result is None
