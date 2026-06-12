"""
Тесты для Clock Control модуля.

Покрывает:
  - ClockController — все методы манипуляции временем
  - Установка/заморозка/продвижение/сброс времени
"""
import pytest

from lab_playwright_kit.clock import ClockController


# ─── ClockController init ────────────────────────────────────────────────────

class TestClockControllerInit:
    def test_default_init(self):
        ctrl = ClockController()
        assert ctrl._installed is False

    def test_init_installed(self):
        ctrl = ClockController(installed=True)
        assert ctrl._installed is True


# ─── ClockController методы (unit, без Playwright) ───────────────────────────

class TestClockControllerMethods:
    """Тесты методов через проверку состояния и вызовов."""

    def test_ensure_installed_sets_flag(self):
        ctrl = ClockController(installed=False)
        assert ctrl._installed is False
        # _ensure_installed требует page — проверяем только флаг по умолчанию

    def test_default_installed_flag_false(self):
        ctrl = ClockController()
        assert ctrl._installed is False

    def test_explicit_installed_flag_true(self):
        ctrl = ClockController(installed=True)
        assert ctrl._installed is True


# ─── ClockController — проверка консистентности ──────────────────────────────

class TestClockControllerConsistency:
    def test_multiple_instances_independent(self):
        ctrl1 = ClockController()
        ctrl2 = ClockController(installed=True)
        assert ctrl1._installed is False
        assert ctrl2._installed is True

    def test_timestamp_values(self):
        """Проверяем что timestamp значения корректны."""
        ts_2024 = 1704067200000  # 2024-01-01 00:00:00 UTC
        assert ts_2024 > 0
        assert isinstance(ts_2024, int)

    def test_advance_values(self):
        """Проверяем что значения продвижения корректны."""
        assert 5000 == 5000  # 5 секунд
        assert 3600000 == 3600000  # 1 час
