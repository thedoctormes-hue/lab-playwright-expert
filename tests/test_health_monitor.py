"""
Тесты для Health Monitor модуля.

Проверяет мониторинг здоровья и алерты.
"""
from __future__ import annotations

import pytest

from lab_playwright_kit.health_monitor import (
    HealthCheck,
    HealthMonitor,
    HealthReport,
    HealthStatus,
)


class TestHealthStatus:
    """Тесты HealthStatus enum."""

    def test_values(self):
        assert HealthStatus.OK.value == "ok"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.FAILING.value == "failing"
        assert HealthStatus.DOWN.value == "down"
        assert HealthStatus.UNKNOWN.value == "unknown"


class TestHealthCheck:
    """Тесты HealthCheck dataclass."""

    def test_default_values(self):
        c = HealthCheck(name="test")
        assert c.name == "test"
        assert c.status == HealthStatus.UNKNOWN
        assert c.message == ""
        assert c.latency_ms == 0.0
        assert c.error is None
        assert c.timestamp != ""

    def test_is_healthy_ok(self):
        c = HealthCheck(name="test", status=HealthStatus.OK)
        assert c.is_healthy is True

    def test_is_healthy_failing(self):
        c = HealthCheck(name="test", status=HealthStatus.FAILING)
        assert c.is_healthy is False

    def test_to_dict(self):
        c = HealthCheck(name="test", status=HealthStatus.OK, message="fine")
        d = c.to_dict()
        assert d["name"] == "test"
        assert d["status"] == "ok"
        assert d["message"] == "fine"

    def test_str_ok(self):
        c = HealthCheck(name="bot", status=HealthStatus.OK, message="fine", latency_ms=50.0)
        s = str(c)
        assert "✅" in s
        assert "bot" in s
        assert "ok" in s

    def test_str_failing(self):
        c = HealthCheck(name="bot", status=HealthStatus.FAILING, message="error", latency_ms=0.0)
        s = str(c)
        assert "🔴" in s


class TestHealthReport:
    """Тесты HealthReport."""

    def test_empty_report(self):
        r = HealthReport()
        assert r.total_count == 0
        assert r.healthy_count == 0
        assert r.overall_status == HealthStatus.UNKNOWN
        assert r.uptime_percent == 0.0

    def test_all_healthy(self):
        r = HealthReport(checks=[
            HealthCheck(name="a", status=HealthStatus.OK),
            HealthCheck(name="b", status=HealthStatus.OK),
        ])
        assert r.overall_status == HealthStatus.OK
        assert r.healthy_count == 2
        assert r.uptime_percent == 100.0

    def test_one_failing(self):
        r = HealthReport(checks=[
            HealthCheck(name="a", status=HealthStatus.OK),
            HealthCheck(name="b", status=HealthStatus.FAILING),
        ])
        assert r.overall_status == HealthStatus.FAILING
        assert r.healthy_count == 1
        assert r.uptime_percent == 50.0

    def test_one_down(self):
        r = HealthReport(checks=[
            HealthCheck(name="a", status=HealthStatus.OK),
            HealthCheck(name="b", status=HealthStatus.DOWN),
        ])
        assert r.overall_status == HealthStatus.DOWN

    def test_degraded(self):
        r = HealthReport(checks=[
            HealthCheck(name="a", status=HealthStatus.OK),
            HealthCheck(name="b", status=HealthStatus.DEGRADED),
        ])
        assert r.overall_status == HealthStatus.DEGRADED

    def test_summary(self):
        r = HealthReport(checks=[
            HealthCheck(name="a", status=HealthStatus.OK, message="fine"),
        ])
        s = r.summary()
        assert "OK" in s
        assert "Healthy: 1/1" in s


class TestHealthMonitor:
    """Тесты HealthMonitor."""

    def test_init_default(self):
        m = HealthMonitor()
        assert m._hc_url is None
        assert m._tg_token is None

    def test_init_with_urls(self):
        m = HealthMonitor(
            healthchecks_url="https://hc-ping.com/test",
            telegram_token="123:abc",
            telegram_chat_id="456",
        )
        assert m._hc_url == "https://hc-ping.com/test"
        assert m._tg_token == "123:abc"
        assert m._tg_chat_id == "456"

    def test_ping_no_url(self):
        """Ping без healthchecks URL — просто возвращает результат."""
        import asyncio
        m = HealthMonitor()
        result = asyncio.run(m.ping("test", "ok"))
        assert result.name == "test"
        assert result.status == HealthStatus.OK
        assert "No healthchecks URL" in result.message

    def test_record_check(self):
        m = HealthMonitor()
        c = HealthCheck(name="test", status=HealthStatus.OK)
        m._record_check(c)
        history = m.get_history("test")
        assert len(history) == 1
        assert history[0].name == "test"

    def test_history_limit(self):
        m = HealthMonitor()
        for i in range(105):
            m._record_check(HealthCheck(name="test", status=HealthStatus.OK))
        # get_history без last_n возвращает все (до 100 из-за лимита в _record_check)
        history = m.get_history("test")
        assert len(history) <= 100  # max 100 из-за лимита в _record_check

    def test_history_last_n(self):
        m = HealthMonitor()
        for i in range(10):
            m._record_check(HealthCheck(name="test", status=HealthStatus.OK))
        history = m.get_history("test", last_n=3)
        assert len(history) == 3

    def test_history_unknown(self):
        m = HealthMonitor()
        history = m.get_history("nonexistent")
        assert len(history) == 0

    def test_rstrip(self):
        assert HealthMonitor._rstrip("test///", "/") == "test"
        assert HealthMonitor._rstrip("test", "/") == "test"
        assert HealthMonitor._rstrip("", "/") == ""
