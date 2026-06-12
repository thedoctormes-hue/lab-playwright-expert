"""
Тесты для browser.py — BrowserManager.

Покрывает:
  - BrowserManager: инициализация, start/stop, new_page, goto, properties
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from lab_playwright_kit.browser import BrowserManager


# ─── BrowserManager ──────────────────────────────────────────────────────────

class TestBrowserManagerInit:
    """Тесты инициализации."""

    def test_default_init(self):
        mgr = BrowserManager()
        assert mgr.headless is True
        assert mgr.browser_type == "chromium"
        assert mgr.user_agent is None
        assert mgr.proxy is None
        assert mgr.profile_dir is None
        assert mgr.timeout == 30000
        assert mgr.viewport == {"width": 1920, "height": 1080}

    def test_custom_init(self):
        mgr = BrowserManager(
            headless=False,
            browser_type="firefox",
            user_agent="Custom/1.0",
            proxy={"server": "socks5://127.0.0.1:1080"},
            profile_dir="/tmp/profile",
            timeout=60000,
            viewport={"width": 1280, "height": 720},
        )
        assert mgr.headless is False
        assert mgr.browser_type == "firefox"
        assert mgr.user_agent == "Custom/1.0"
        assert mgr.proxy == {"server": "socks5://127.0.0.1:1080"}
        assert mgr.profile_dir == "/tmp/profile"
        assert mgr.timeout == 60000
        assert mgr.viewport == {"width": 1280, "height": 720}

    def test_default_viewport(self):
        """Viewport по умолчанию — 1920x1080."""
        mgr = BrowserManager()
        assert mgr.viewport["width"] == 1920
        assert mgr.viewport["height"] == 1080

    def test_initial_state(self):
        """До start() — всё None/False."""
        mgr = BrowserManager()
        assert mgr._playwright is None
        assert mgr._browser is None
        assert mgr._context is None
        assert mgr._closed is False


class TestBrowserManagerProperties:
    """Тесты свойств."""

    def test_context_raises_before_start(self):
        """context до start() — RuntimeError."""
        mgr = BrowserManager()
        with pytest.raises(RuntimeError, match="Browser not started"):
            _ = mgr.context

    def test_browser_raises_before_start(self):
        """browser до start() — RuntimeError."""
        mgr = BrowserManager()
        with pytest.raises(RuntimeError, match="Browser not started"):
            _ = mgr.browser


class TestBrowserManagerStartStop:
    """Тесты start() и stop()."""

    @pytest.mark.asyncio
    async def test_start(self):
        """start() инициализирует playwright, browser, context."""
        mgr = BrowserManager()
        with patch("lab_playwright_kit.browser.async_playwright") as mock_pw:
            mock_playwright = AsyncMock()
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_chromium = AsyncMock()
            mock_chromium.launch = AsyncMock(return_value=mock_browser)
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_playwright.chromium = mock_chromium
            mock_pw.return_value.start = AsyncMock(return_value=mock_playwright)

            await mgr.start()

            assert mgr._playwright is not None
            assert mgr._browser is not None
            assert mgr._context is not None
            assert mgr._closed is False

    @pytest.mark.asyncio
    async def test_stop(self):
        """stop() закрывает context, browser, playwright."""
        mgr = BrowserManager()
        mock_context = AsyncMock()
        mock_browser = AsyncMock()
        mock_playwright = AsyncMock()
        mgr._context = mock_context
        mgr._browser = mock_browser
        mgr._playwright = mock_playwright

        await mgr.stop()

        mock_context.close.assert_called_once()
        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()
        assert mgr._closed is True

    @pytest.mark.asyncio
    async def test_stop_idempotent(self):
        """stop() идемпотентный — повторный вызов не падает."""
        mgr = BrowserManager()
        mgr._closed = True
        await mgr.stop()  # Не должно падать

    @pytest.mark.asyncio
    async def test_stop_handles_exceptions(self):
        """stop() подавляет исключения при закрытии."""
        mgr = BrowserManager()
        mock_context = AsyncMock()
        mock_context.close = AsyncMock(side_effect=Exception("already closed"))
        mock_browser = AsyncMock()
        mock_browser.close = AsyncMock(side_effect=Exception("already closed"))
        mock_playwright = AsyncMock()
        mock_playwright.stop = AsyncMock(side_effect=Exception("already stopped"))
        mgr._context = mock_context
        mgr._browser = mock_browser
        mgr._playwright = mock_playwright

        await mgr.stop()  # Не должно падать
        assert mgr._closed is True


class TestBrowserManagerNewPage:
    """Тесты new_page()."""

    @pytest.mark.asyncio
    async def test_new_page(self):
        """new_page() создаёт страницу через context."""
        mgr = BrowserManager()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mgr._context = mock_context

        page = await mgr.new_page()
        assert page is mock_page
        mock_context.new_page.assert_called_once()


class TestBrowserManagerGoto:
    """Тесты goto()."""

    @pytest.mark.asyncio
    async def test_goto(self):
        """goto() создаёт страницу и навигирует."""
        mgr = BrowserManager()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mgr._context = mock_context

        page = await mgr.goto("https://example.com")
        assert page is mock_page
        mock_page.goto.assert_called_once_with("https://example.com", wait_until="domcontentloaded")

    @pytest.mark.asyncio
    async def test_goto_custom_wait(self):
        """goto() с кастомным wait_until."""
        mgr = BrowserManager()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mgr._context = mock_context

        await mgr.goto("https://example.com", wait_until="networkidle")
        mock_page.goto.assert_called_once_with("https://example.com", wait_until="networkidle")


class TestBrowserManagerContextManager:
    """Тесты async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """async with — start + stop."""
        mgr = BrowserManager()
        with patch.object(mgr, "start", new_callable=AsyncMock) as mock_start:
            with patch.object(mgr, "stop", new_callable=AsyncMock) as mock_stop:
                async with mgr as m:
                    assert m is mgr
                    mock_start.assert_called_once()
                mock_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_exception(self):
        """async with — stop вызывается даже при исключении."""
        mgr = BrowserManager()
        with patch.object(mgr, "start", new_callable=AsyncMock):
            with patch.object(mgr, "stop", new_callable=AsyncMock) as mock_stop:
                with pytest.raises(ValueError):
                    async with mgr:
                        raise ValueError("test")
                mock_stop.assert_called_once()


class TestBrowserManagerPersistentContext:
    """Тесты persistent context (profile_dir)."""

    @pytest.mark.asyncio
    async def test_start_with_profile(self):
        """start() с profile_dir — persistent context."""
        mgr = BrowserManager(profile_dir="/tmp/profile")
        with patch("lab_playwright_kit.browser.async_playwright") as mock_pw:
            mock_playwright = AsyncMock()
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_chromium = AsyncMock()
            mock_chromium.launch_persistent_context = AsyncMock(return_value=mock_context)
            mock_context.browser = mock_browser
            mock_playwright.chromium = mock_chromium
            mock_pw.return_value.start = AsyncMock(return_value=mock_playwright)

            await mgr.start()

            mock_chromium.launch_persistent_context.assert_called_once()
            assert mgr._context is mock_context
            assert mgr._browser is mock_browser
