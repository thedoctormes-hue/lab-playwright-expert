"""
Расширенные тесты для ClockController.

Покрывает:
  - ClockController.__init__ — installed флаг
  - Все методы требуют page (async) — проверяем что они вызываются
  - Проверяем что _ensure_installed устанавливает флаг
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from lab_playwright_kit.clock import ClockController


# ─── Инициализация ───────────────────────────────────────────────────────


class TestClockControllerInit:
    def test_default_not_installed(self):
        cc = ClockController()
        assert cc._installed is False

    def test_installed_true(self):
        cc = ClockController(installed=True)
        assert cc._installed is True


# ─── _ensure_installed ───────────────────────────────────────────────────


class TestEnsureInstalled:
    @pytest.mark.asyncio
    async def test_installs_when_not_installed(self):
        cc = ClockController(installed=False)
        mock_page = MagicMock()
        mock_page.clock.install = AsyncMock()

        await cc._ensure_installed(mock_page)

        mock_page.clock.install.assert_called_once()
        assert cc._installed is True

    @pytest.mark.asyncio
    async def test_skips_when_already_installed(self):
        cc = ClockController(installed=True)
        mock_page = MagicMock()
        mock_page.clock.install = AsyncMock()

        await cc._ensure_installed(mock_page)

        mock_page.clock.install.assert_not_called()
        assert cc._installed is True


# ─── freeze ──────────────────────────────────────────────────────────────


class TestFreeze:
    @pytest.mark.asyncio
    async def test_freeze_calls_install_and_freeze(self):
        cc = ClockController(installed=True)
        mock_page = MagicMock()
        mock_page.clock.install = AsyncMock()
        mock_page.clock.freeze = AsyncMock()

        await cc.freeze(mock_page, 1700000000000)

        mock_page.clock.freeze.assert_called_once_with(1700000000000)

    @pytest.mark.asyncio
    async def test_freeze_with_zero_timestamp(self):
        cc = ClockController(installed=True)
        mock_page = MagicMock()
        mock_page.clock.freeze = AsyncMock()

        await cc.freeze(mock_page, 0)

        mock_page.clock.freeze.assert_called_once_with(0)


# ─── advance ─────────────────────────────────────────────────────────────


class TestAdvance:
    @pytest.mark.asyncio
    async def test_advance_calls_run_for(self):
        cc = ClockController(installed=True)
        mock_page = MagicMock()
        mock_page.clock.run_for = AsyncMock()

        await cc.advance(mock_page, 5000)

        mock_page.clock.run_for.assert_called_once_with(5000)

    @pytest.mark.asyncio
    async def test_advance_zero_ms(self):
        cc = ClockController(installed=True)
        mock_page = MagicMock()
        mock_page.clock.run_for = AsyncMock()

        await cc.advance(mock_page, 0)

        mock_page.clock.run_for.assert_called_once_with(0)


# ─── set_fixed ───────────────────────────────────────────────────────────


class testSetFixed:
    @pytest.mark.asyncio
    async def test_set_fixed_calls_set_fixed_time(self):
        cc = ClockController(installed=True)
        mock_page = MagicMock()
        mock_page.clock.set_fixed_time = AsyncMock()

        await cc.set_fixed(mock_page, 1704067200000)

        mock_page.clock.set_fixed_time.assert_called_once_with(1704067200000)


# ─── reset ──────────────────────────────────────────────────────────────


class TestReset:
    @pytest.mark.asyncio
    async def test_reset_calls_resume(self):
        cc = ClockController(installed=True)
        mock_page = MagicMock()
        mock_page.clock.resume = AsyncMock()

        await cc.reset(mock_page)

        mock_page.clock.resume.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_does_not_call_install(self):
        cc = ClockController(installed=False)
        mock_page = MagicMock()
        mock_page.clock.resume = AsyncMock()
        mock_page.clock.install = AsyncMock()

        await cc.reset(mock_page)

        mock_page.clock.install.assert_not_called()


# ─── fast_forward ────────────────────────────────────────────────────────


class TestFastForward:
    @pytest.mark.asyncio
    async def test_fast_forward_calls_run_for(self):
        cc = ClockController(installed=True)
        mock_page = MagicMock()
        mock_page.clock.fast_forward = AsyncMock()

        await cc.fast_forward(mock_page, 10000)

        mock_page.clock.fast_forward.assert_called_once_with(10000)


# ─── run_for ─────────────────────────────────────────────────────────────


class TestRunFor:
    @pytest.mark.asyncio
    async def test_run_for_calls_clock_run_for(self):
        cc = ClockController(installed=True)
        mock_page = MagicMock()
        mock_page.clock.run_for = AsyncMock()

        await cc.run_for(mock_page, 3000)

        mock_page.clock.run_for.assert_called_once_with(3000)
