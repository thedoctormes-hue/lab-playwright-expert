"""
E2E tests for CloakBrowser engine, BrowserManager engine switching,
SaaS API, and BrowserAuthManager.

These tests run against real browser instances (playwright or cloakbrowser)
and verify end-to-end behavior.

Requirements:
  - CloakBrowser binary at /root/.cloakbrowser/chromium-146.0.7680.177.3/chrome
  - Xvfb available for headless environments (auto-started via xvfb-run)
  - /root/LabDoctorM/venv/ virtual environment

Run:
  cd /root/LabDoctorM/projects/lab-playwright-expert
  source /root/LabDoctorM/venv/bin/activate
  python3 -m pytest tests/test_e2e_cloakbrowser.py -v --tb=short
"""
from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import requests

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from lab_playwright_kit.browser import CLOAKBROWSER_PATH, BrowserManager
from lab_playwright_kit.browser_auth import (
    AUTH_PRESETS,
    HABR_AUTH_PRESET,
    VCRU_AUTH_PRESET,
    AuthResultStatus,
    BrowserAuthManager,
)
from lab_playwright_kit.saas_api import create_app


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _run_async(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── Marks ───────────────────────────────────────────────────────────────────

requires_cloakbrowser = pytest.mark.skipif(
    not os.path.exists(CLOAKBROWSER_PATH),
    reason=f"CloakBrowser not found at {CLOAKBROWSER_PATH}",
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def saas_api_server():
    """Start a real SaaS API server in a background process.

    Yields the base URL. Server is stopped after all tests in the module.
    Uses playwright engine (not cloakbrowser) for faster startup.
    """
    port = 18195
    url = f"http://127.0.0.1:{port}"

    proc = subprocess.Popen(
        [
            sys.executable, "-c",
            f"""
import uvicorn
from lab_playwright_kit.saas_api import create_app
app = create_app(browser_engine="playwright")
uvicorn.run(app, host="127.0.0.1", port={port}, log_level="warning")
""",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid,
    )

    # Wait for server to be ready
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            r = requests.get(f"{url}/api/v1/health", timeout=2)
            if r.status_code == 200:
                break
        except requests.ConnectionError:
            pass
        time.sleep(0.5)
    else:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=10)
        pytest.fail("SaaS API server did not start in time")

    yield url

    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    proc.wait(timeout=15)


@pytest.fixture
def temp_profile_dir():
    """Temporary directory for browser profile (persistent context)."""
    with tempfile.TemporaryDirectory(prefix="cloak_e2e_") as tmpdir:
        yield tmpdir


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CLOAKBROWSER ENGINE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@requires_cloakbrowser
class TestCloakBrowserEngine:
    """E2E tests for CloakBrowser engine via BrowserManager."""

    def test_cloakbrowser_basic_launch(self):
        """Launch cloakbrowser, navigate to habr.com, verify webdriver=False."""
        async def _test():
            bm = BrowserManager(engine="cloakbrowser", headless=True)
            await bm.start()
            try:
                page = await bm.goto("https://habr.com/ru/articles/", wait_until="domcontentloaded")
                title = await page.title()
                assert "Хабр" in title or "Habr" in title

                # Core stealth check: navigator.webdriver must be False
                webdriver = await page.evaluate("navigator.webdriver")
                assert webdriver is False or webdriver == False, (
                    f"navigator.webdriver should be False, got {webdriver!r}"
                )
            finally:
                await bm.stop()

        _run_async(_test())

    def test_cloakbrowser_humanize(self):
        """Launch cloakbrowser with humanize=True, navigate to example.com."""
        async def _test():
            bm = BrowserManager(engine="cloakbrowser", headless=True, humanize=True)
            await bm.start()
            try:
                page = await bm.goto("https://example.com")
                title = await page.title()
                assert title == "Example Domain"
            finally:
                await bm.stop()

        _run_async(_test())

    def test_cloakbrowser_fingerprint_seed(self):
        """Two launches with the same seed produce identical fingerprints (UA + platform)."""
        results = []

        for _ in range(2):
            async def _test():
                bm = BrowserManager(
                    engine="cloakbrowser",
                    headless=True,
                    cloak_fingerprint_seed=42,
                )
                await bm.start()
                try:
                    page = await bm.goto("https://example.com")
                    ua = await page.evaluate("navigator.userAgent")
                    platform = await page.evaluate("navigator.platform")
                    results.append((ua, platform))
                finally:
                    await bm.stop()

            _run_async(_test())

        assert len(results) == 2
        assert results[0][0] == results[1][0], (
            f"UA mismatch: {results[0][0][:80]} vs {results[1][0][:80]}"
        )
        assert results[0][1] == results[1][1], (
            f"Platform mismatch: {results[0][1]} vs {results[1][1]}"
        )

    def test_cloakbrowser_persistent_context(self):
        """Persistent context: cookies survive between restarts (same profile_dir).

        NOTE: This test is marked xfail because CloakBrowser's launch_persistent_context
        crashes with SIGSEGV. When the bug is fixed, this test should pass.
        """
        async def _test():
            with tempfile.TemporaryDirectory(prefix="cloak_persist_") as tmpdir:
                profile = os.path.join(tmpdir, "profile")

                # First run: set a cookie via JS
                bm1 = BrowserManager(
                    engine="cloakbrowser", headless=True, profile_dir=profile,
                )
                await bm1.start()
                try:
                    page1 = await bm1.goto("https://example.com")
                    await page1.evaluate("document.cookie = 'e2e_test=cloak_persist; path=/; max-age=3600'")
                    await asyncio.sleep(0.5)
                finally:
                    await bm1.stop()

                # Second run: check cookie persists
                bm2 = BrowserManager(
                    engine="cloakbrowser", headless=True, profile_dir=profile,
                )
                await bm2.start()
                try:
                    page2 = await bm2.goto("https://example.com")
                    cookies = await page2.context.cookies()
                    found = [c for c in cookies if c["name"] == "e2e_test"]
                    assert len(found) == 1, (
                        f"Expected e2e_test cookie, got: {[c['name'] for c in cookies]}"
                    )
                    assert found[0]["value"] == "cloak_persist"
                finally:
                    await bm2.stop()

        _run_async(_test())

    def test_cloakbrowser_non_persistent_context(self):
        """Non-persistent context: cookies are available within the same session."""
        async def _test():
            bm = BrowserManager(engine="cloakbrowser", headless=True)
            await bm.start()
            try:
                page = await bm.goto("https://example.com")
                # Set a cookie via JS
                await page.evaluate("document.cookie = 'session_test=hello; path=/; max-age=3600'")
                # Read it back
                cookies = await page.context.cookies()
                found = [c for c in cookies if c["name"] == "session_test"]
                assert len(found) == 1, (
                    f"Expected session_test cookie in same session, got: {[c['name'] for c in cookies]}"
                )
                assert found[0]["value"] == "hello"
            finally:
                await bm.stop()

        _run_async(_test())

    def test_cloakbrowser_stealth_not_applied(self):
        """StealthPipeline must NOT be applied when engine=cloakbrowser.

        The BrowserManager should have _stealth=None for cloakbrowser,
        because stealth is built into the C++ binary.
        """
        bm = BrowserManager(engine="cloakbrowser", headless=True)
        assert bm._stealth is None, (
            f"StealthPipeline should be None for cloakbrowser, got {type(bm._stealth)}"
        )
        assert bm.engine == "cloakbrowser"

    def test_cloakbrowser_bot_detection(self):
        """Navigate to bot.sannysoft.com, verify webdriver=False and plugins >= 3."""
        async def _test():
            bm = BrowserManager(engine="cloakbrowser", headless=True)
            await bm.start()
            try:
                page = await bm.goto(
                    "https://bot.sannysoft.com",
                    wait_until="networkidle",
                )
                # Core stealth checks
                webdriver = await page.evaluate("navigator.webdriver")
                assert webdriver is False or webdriver == False, (
                    f"navigator.webdriver should be False, got {webdriver!r}"
                )

                plugins = await page.evaluate("navigator.plugins.length")
                assert plugins >= 3, (
                    f"Expected >= 3 plugins for realistic browser, got {plugins}"
                )
            finally:
                await bm.stop()

        _run_async(_test())


# ═══════════════════════════════════════════════════════════════════════════════
# 2. BROWSERMANAGER ENGINE SWITCHING
# ═══════════════════════════════════════════════════════════════════════════════

class TestBrowserManagerEngineSwitching:
    """Tests for engine selection logic in BrowserManager."""

    def test_engine_playwright_default(self):
        """Default engine is 'playwright'."""
        bm = BrowserManager()
        assert bm.engine == "playwright"

    def test_engine_cloakbrowser_explicit(self):
        """Explicitly setting engine='cloakbrowser' stores the value."""
        bm = BrowserManager(engine="cloakbrowser")
        assert bm.engine == "cloakbrowser"

    def test_engine_invalid(self):
        """Unknown engine value is stored as-is (falls back to playwright at start)."""
        bm = BrowserManager(engine="unknown_engine")
        assert bm.engine == "unknown_engine"

    def test_engine_playwright_starts_successfully(self):
        """Playwright engine starts and navigates to a page."""
        async def _test():
            bm = BrowserManager(engine="playwright", headless=True)
            await bm.start()
            try:
                page = await bm.goto("https://example.com")
                title = await page.title()
                assert title == "Example Domain"
            finally:
                await bm.stop()

        _run_async(_test())

    @requires_cloakbrowser
    def test_engine_cloakbrowser_starts_successfully(self):
        """CloakBrowser engine starts and navigates to a page."""
        async def _test():
            bm = BrowserManager(engine="cloakbrowser", headless=True)
            await bm.start()
            try:
                page = await bm.goto("https://example.com")
                title = await page.title()
                assert title == "Example Domain"
            finally:
                await bm.stop()

        _run_async(_test())

    def test_engine_invalid_falls_back_to_playwright(self):
        """Invalid engine falls back to playwright at start() time."""
        async def _test():
            bm = BrowserManager(engine="nonexistent_engine", headless=True)
            await bm.start()  # Should not raise, falls back to playwright
            try:
                page = await bm.goto("https://example.com")
                title = await page.title()
                assert title == "Example Domain"
            finally:
                await bm.stop()

        _run_async(_test())

    def test_cloakbrowser_no_stealth_pipeline(self):
        """CloakBrowser should never have StealthPipeline applied, even if requested."""
        bm = BrowserManager(
            engine="cloakbrowser",
            headless=True,
            stealth="maximum",  # Should be ignored
        )
        assert bm._stealth is None

    def test_playwright_gets_stealth_pipeline(self):
        """Playwright engine should accept StealthPipeline."""
        from lab_playwright_kit.stealth_pipeline import StealthPipeline

        bm = BrowserManager(
            engine="playwright",
            headless=True,
            stealth="standard",
        )
        assert bm._stealth is not None
        assert isinstance(bm._stealth, StealthPipeline)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. SaaS API E2E
# ═══════════════════════════════════════════════════════════════════════════════

class TestSaasApiE2E:
    """E2E tests for SaaS Parsing API (real server, real browser)."""

    def test_saas_api_health(self, saas_api_server):
        """Health endpoint returns 200 with status='healthy'."""
        r = requests.get(f"{saas_api_server}/api/v1/health", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "uptime_seconds" in data

    def test_saas_api_status(self, saas_api_server):
        """Status endpoint returns engine info and system state."""
        r = requests.get(f"{saas_api_server}/api/v1/status", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "running"
        assert data["browser_active"] is True
        assert data["available_niches"] == 10
        assert data["available_presets"] == 5

    def test_saas_api_parse_habr(self, saas_api_server):
        """Parse a public Habr article without authentication."""
        r = requests.post(
            f"{saas_api_server}/api/v1/parse",
            json={
                "url": "https://habr.com/ru/articles/700000/",
                "niche": "habr",
                "timeout": 30,
            },
            timeout=60,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["niche"] == "habr"
        assert "title" in data["data"]
        assert data["confidence"] > 0.5

    def test_saas_api_niches(self, saas_api_server):
        """List all available niches."""
        r = requests.get(f"{saas_api_server}/api/v1/niches", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 10
        names = [n["name"] for n in data]
        assert "habr" in names
        assert "vcru" in names
        assert "twitter" in names
        assert "telegram" in names

    def test_saas_api_niche_detail(self, saas_api_server):
        """Get details of a specific niche."""
        r = requests.get(f"{saas_api_server}/api/v1/niches/habr", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "habr"
        assert "title" in data["fields"]
        assert "content" in data["fields"]
        assert "author" in data["fields"]

    def test_saas_api_parse_generic(self, saas_api_server):
        """Parse a page with auto-detected niche (no niche specified).

        Using a news-like URL that should match a known niche pattern.
        """
        r = requests.post(
            f"{saas_api_server}/api/v1/parse",
            json={
                "url": "https://habr.com/ru/news/",
                "timeout": 15,
            },
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        # Should have some data even if niche is auto-detected
        assert "data" in data

    def test_saas_api_auth_presets(self, saas_api_server):
        """List auth presets."""
        r = requests.get(f"{saas_api_server}/api/v1/auth/presets", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 5
        names = [p["name"] for p in data["presets"]]
        assert "habr" in names
        assert "vcru" in names
        assert "twitter" in names
        assert "telegram" in names

    def test_saas_api_auth_sessions_empty(self, saas_api_server):
        """List sessions when none exist."""
        r = requests.get(f"{saas_api_server}/api/v1/auth/sessions", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 4. BROWSERAUTHMANAGER E2E (without real credentials)
# ═══════════════════════════════════════════════════════════════════════════════

class TestBrowserAuthManagerE2E:
    """E2E tests for BrowserAuthManager — no real credentials needed."""

    def test_auth_preset_habr(self):
        """Habr auth preset has correct login_url and selectors."""
        preset = HABR_AUTH_PRESET
        assert preset.platform == "habr"
        assert "habr.com" in preset.login_url
        assert preset.username_selector != ""
        assert preset.password_selector != ""
        assert preset.submit_selector != ""
        assert len(preset.auth_selectors) > 0
        assert preset.captcha_selector != ""  # Habr has captcha detection

    def test_auth_preset_vcru(self):
        """VC.ru auth preset has correct login_url and selectors."""
        preset = VCRU_AUTH_PRESET
        assert preset.platform == "vcru"
        assert "vc.ru" in preset.login_url
        assert preset.username_selector != ""
        assert preset.password_selector != ""
        assert len(preset.auth_selectors) > 0

    def test_auth_preset_registry(self):
        """All expected platforms are registered in AUTH_PRESETS."""
        expected = {"habr", "vcru", "twitter", "x", "telegram"}
        assert set(AUTH_PRESETS.keys()) == expected

    def test_auth_login_invalid_creds_returns_failed(self, saas_api_server):
        """Login with invalid credentials returns FAILED status."""
        r = requests.post(
            f"{saas_api_server}/api/v1/auth/login",
            json={
                "platform": "habr",
                "username": "invalid_e2e@test.com",
                "password": "wrong_password_12345",
            },
            timeout=60,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is False
        assert data["status"] in ("failed", "captcha_required"), (
            f"Expected failed or captcha, got {data['status']}"
        )

    def test_auth_check_not_authenticated(self, saas_api_server):
        """Check auth for a user that never logged in."""
        r = requests.post(
            f"{saas_api_server}/api/v1/auth/check",
            json={
                "platform": "habr",
                "username": "never_logged_in@test.com",
            },
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is False
        assert data["status"] == "not_authenticated"

    def test_auth_login_no_preset(self, saas_api_server):
        """Login with unknown platform returns 422 (validation error)."""
        r = requests.post(
            f"{saas_api_server}/api/v1/auth/login",
            json={
                "platform": "unknown_platform_xyz",
                "username": "user@test.com",
                "password": "pass",
            },
            timeout=10,
        )
        # Unknown platform — the API will try to find a preset and fail,
        # or FastAPI will reject it. Either way, it should not be 200 success.
        assert r.status_code in (200, 422)
        if r.status_code == 200:
            data = r.json()
            assert data["success"] is False

    def test_auth_preset_all_have_login_url(self):
        """All presets must have a valid login_url."""
        for name, preset in AUTH_PRESETS.items():
            assert preset.login_url.startswith("http"), (
                f"{name}: login_url must start with http, got: {preset.login_url}"
            )

    def test_auth_preset_all_have_selectors(self):
        """All presets must have username/password/submit selectors."""
        for name, preset in AUTH_PRESETS.items():
            assert preset.username_selector, f"{name}: missing username_selector"
            assert preset.password_selector, f"{name}: missing password_selector"
            assert preset.submit_selector, f"{name}: missing submit_selector"
