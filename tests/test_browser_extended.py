"""
Расширенные тесты для BrowserManager.

Покрывает:
  - BrowserManager.__init__ — атрибуты, типы, значения по умолчанию
  - Engine selection: playwright vs cloakbrowser
  - StealthPipeline handling при инициализации
  - closed state
  - context/browser property access (без запуска браузера)
"""

from __future__ import annotations

import pytest

from lab_playwright_kit.browser import BrowserManager


# ─── Инициализация — атрибуты по умолчанию ──────────────────────────────


class TestBrowserManagerInitDefaults:
    def test_default_headless(self):
        bm = BrowserManager()
        assert bm.headless is True

    def test_default_browser_type(self):
        bm = BrowserManager()
        assert bm.browser_type == "chromium"

    def test_default_timeout(self):
        bm = BrowserManager()
        assert bm.timeout == 30000

    def test_default_viewport(self):
        bm = BrowserManager()
        assert bm.viewport == {"width": 1920, "height": 1080}

    def test_default_engine(self):
        bm = BrowserManager()
        assert bm.engine == "playwright"

    def test_default_humanize(self):
        bm = BrowserManager()
        assert bm.humanize is False

    def test_default_stealth_none(self):
        bm = BrowserManager()
        assert bm._stealth is None

    def test_default_closed(self):
        bm = BrowserManager()
        assert bm._closed is False

    def test_default_none_objects(self):
        bm = BrowserManager()
        assert bm._playwright is None
        assert bm._browser is None
        assert bm._context is None


# ─── Инициализация — кастомные параметры ─────────────────────────────────


class TestBrowserManagerInitCustom:
    def test_headless_false(self):
        bm = BrowserManager(headless=False)
        assert bm.headless is False

    def test_custom_timeout(self):
        bm = BrowserManager(timeout=60000)
        assert bm.timeout == 60000

    def test_custom_viewport(self):
        bm = BrowserManager(viewport={"width": 1280, "height": 720})
        assert bm.viewport == {"width": 1280, "height": 720}

    def test_custom_user_agent(self):
        bm = BrowserManager(user_agent="TestAgent/1.0")
        assert bm.user_agent == "TestAgent/1.0"

    def test_custom_proxy(self):
        proxy = {"server": "http://proxy:8080"}
        bm = BrowserManager(proxy=proxy)
        assert bm.proxy == proxy

    def test_custom_profile_dir(self):
        bm = BrowserManager(profile_dir="/tmp/profile")
        assert bm.profile_dir == "/tmp/profile"

    def test_cloak_platform(self):
        bm = BrowserManager(cloak_platform="macos")
        assert bm.cloak_platform == "macos"

    def test_cloak_fingerprint_seed(self):
        bm = BrowserManager(cloak_fingerprint_seed=42)
        assert bm.cloak_fingerprint_seed == 42


# ─── Engine selection ────────────────────────────────────────────────────


class TestEngineSelection:
    def test_playwright_engine(self):
        bm = BrowserManager(engine="playwright")
        assert bm.engine == "playwright"

    def test_cloakbrowser_engine(self):
        bm = BrowserManager(engine="cloakbrowser")
        assert bm.engine == "cloakbrowser"

    def test_cloakbrowser_stealth_forced_none(self):
        """При cloakbrowser stealth всегда None, даже если передан."""
        bm = BrowserManager(engine="cloakbrowser", stealth="full")
        assert bm._stealth is None

    def test_cloakbrowser_humanize(self):
        bm = BrowserManager(engine="cloakbrowser", humanize=True)
        assert bm.humanize is True


# ─── StealthPipeline handling ────────────────────────────────────────────


class TestStealthHandling:
    def test_string_stealth(self):
        bm = BrowserManager(stealth="standard")
        assert bm._stealth is not None

    def test_string_stealth_advanced(self):
        bm = BrowserManager(stealth="advanced")
        assert bm._stealth is not None

    def test_string_stealth_full(self):
        bm = BrowserManager(stealth="full")
        assert bm._stealth is not None

    def test_string_stealth_minimal(self):
        bm = BrowserManager(stealth="minimal")
        assert bm._stealth is not None

    def test_none_stealth(self):
        bm = BrowserManager(stealth=None)
        assert bm._stealth is None

    def test_object_stealth(self):
        from lab_playwright_kit.stealth_pipeline import StealthPipeline

        sp = StealthPipeline.level("standard")
        bm = BrowserManager(stealth=sp)
        assert bm._stealth is sp


# ─── Properties без запуска ──────────────────────────────────────────────


class TestPropertiesWithoutStart:
    def test_context_raises(self):
        bm = BrowserManager()
        with pytest.raises(RuntimeError, match="Browser not started"):
            _ = bm.context

    def test_browser_raises(self):
        bm = BrowserManager()
        with pytest.raises(RuntimeError, match="Browser not started"):
            _ = bm.browser


# ─── Closed state ────────────────────────────────────────────────────────


class TestClosedState:
    def test_initially_not_closed(self):
        bm = BrowserManager()
        assert bm._closed is False
