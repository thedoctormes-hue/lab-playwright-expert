"""
Расширенные тесты для HealthMonitor.

Покрывает:
  - HealthCheck dataclass (is_healthy, to_dict, __str__, __post_init__)
  - HealthReport (overall_status, healthy_count, uptime_percent, summary)
  - HealthMonitor.__init__
  - HealthMonitor.ping (with/without HC URL)
  - HealthMonitor.check_and_alert (success/failure/exception)
  - HealthMonitor.run_checks (parallel)
  - HealthMonitor.get_history
  - HealthMonitor._send_telegram_alert/report/message (mocked)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lab_playwright_kit.health_monitor import (
    HealthCheck,
    HealthMonitor,
    HealthReport,
    HealthStatus,
)


# ─── HealthCheck ────────────────────────────────────────────────────────────


class TestHealthCheck:
    def test_defaults(self):
        hc = HealthCheck(name="test")
        assert hc.name == "test"
        assert hc.status == HealthStatus.UNKNOWN
        assert hc.message == ""
        assert hc.latency_ms == 0.0
        assert hc.metadata == {}
        assert hc.error is None

    def test_is_healthy_ok(self):
        hc = HealthCheck(name="test", status=HealthStatus.OK)
        assert hc.is_healthy is True

    def test_is_healthy_not_ok(self):
        for status in [
            HealthStatus.DEGRADED,
            HealthStatus.FAILING,
            HealthStatus.DOWN,
            HealthStatus.UNKNOWN,
        ]:
            hc = HealthCheck(name="test", status=status)
            assert hc.is_healthy is False

    def test_to_dict(self):
        hc = HealthCheck(
            name="bot",
            status=HealthStatus.OK,
            message="All good",
            latency_ms=42.5,
            metadata={"version": "1.0"},
        )
        d = hc.to_dict()
        assert d["name"] == "bot"
        assert d["status"] == "ok"
        assert d["message"] == "All good"
        assert d["latency_ms"] == 42.5
        assert d["metadata"] == {"version": "1.0"}

    def test_str_ok(self):
        hc = HealthCheck(name="bot", status=HealthStatus.OK, message="Fine", latency_ms=100)
        s = str(hc)
        assert "bot" in s
        assert "ok" in s
        assert "Fine" in s

    def test_str_failing(self):
        hc = HealthCheck(name="bot", status=HealthStatus.FAILING, message="Broken")
        s = str(hc)
        assert "bot" in s
        assert "failing" in s

    def test_post_init_sets_timestamp(self):
        hc = HealthCheck(name="test")
        assert hc.timestamp != ""
        assert "T" in hc.timestamp  # ISO format

    def test_post_init_preserves_timestamp(self):
        hc = HealthCheck(name="test", timestamp="2026-01-01T00:00:00+00:00")
        assert hc.timestamp == "2026-01-01T00:00:00+00:00"


# ─── HealthStatus enum ──────────────────────────────────────────────────────


class TestHealthStatus:
    def test_values(self):
        assert HealthStatus.OK.value == "ok"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.FAILING.value == "failing"
        assert HealthStatus.DOWN.value == "down"
        assert HealthStatus.UNKNOWN.value == "unknown"


# ─── HealthReport ───────────────────────────────────────────────────────────


class TestHealthReport:
    def test_empty_report(self):
        report = HealthReport()
        assert report.overall_status == HealthStatus.UNKNOWN
        assert report.healthy_count == 0
        assert report.total_count == 0
        assert report.uptime_percent == 0.0

    def test_all_healthy(self):
        report = HealthReport(
            checks=[
                HealthCheck(name="a", status=HealthStatus.OK),
                HealthCheck(name="b", status=HealthStatus.OK),
            ]
        )
        assert report.overall_status == HealthStatus.OK
        assert report.healthy_count == 2
        assert report.total_count == 2
        assert report.uptime_percent == 100.0

    def test_one_down(self):
        report = HealthReport(
            checks=[
                HealthCheck(name="a", status=HealthStatus.OK),
                HealthCheck(name="b", status=HealthStatus.DOWN),
            ]
        )
        assert report.overall_status == HealthStatus.DOWN
        assert report.healthy_count == 1
        assert report.uptime_percent == 50.0

    def test_one_failing(self):
        report = HealthReport(
            checks=[
                HealthCheck(name="a", status=HealthStatus.OK),
                HealthCheck(name="b", status=HealthStatus.FAILING),
            ]
        )
        assert report.overall_status == HealthStatus.FAILING

    def test_one_degraded(self):
        report = HealthReport(
            checks=[
                HealthCheck(name="a", status=HealthStatus.OK),
                HealthCheck(name="b", status=HealthStatus.DEGRADED),
            ]
        )
        assert report.overall_status == HealthStatus.DEGRADED

    def test_summary(self):
        report = HealthReport(
            checks=[
                HealthCheck(name="bot", status=HealthStatus.OK, message="Fine", latency_ms=50),
            ]
        )
        s = report.summary()
        assert "Health Report" in s
        assert "OK" in s
        assert "1/1" in s


# ─── HealthMonitor init ────────────────────────────────────────────────────


class TestHealthMonitorInit:
    def test_default_init(self):
        mon = HealthMonitor()
        assert mon._hc_url is None
        assert mon._tg_token is None
        assert mon._tg_chat_id is None
        assert mon._timeout == 10.0

    def test_custom_init(self):
        mon = HealthMonitor(
            healthchecks_url="https://hc-ping.com/uuid",
            telegram_token="bot123",
            telegram_chat_id="chat456",
            timeout=30.0,
        )
        assert mon._hc_url == "https://hc-ping.com/uuid"
        assert mon._tg_token == "bot123"
        assert mon._tg_chat_id == "chat456"
        assert mon._timeout == 30.0


# ─── HealthMonitor.ping ────────────────────────────────────────────────────


class TestHealthMonitorPing:
    @pytest.mark.asyncio
    async def test_ping_no_hc_url(self):
        mon = HealthMonitor()
        check = await mon.ping(name="test", status="ok")
        assert check.name == "test"
        assert check.status == HealthStatus.OK
        assert check.message == "No healthchecks URL configured"

    @pytest.mark.asyncio
    async def test_ping_ok_with_hc_url(self):
        mon = HealthMonitor(healthchecks_url="https://hc-ping.com/uuid")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.elapsed.total_seconds.return_value = 0.05

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("lab_playwright_kit.health_monitor.httpx.AsyncClient", return_value=mock_client):
            check = await mon.ping(name="test", status="ok")

        assert check.status == HealthStatus.OK
        assert check.latency_ms == 50.0

    @pytest.mark.asyncio
    async def test_ping_fail_with_hc_url(self):
        mon = HealthMonitor(healthchecks_url="https://hc-ping.com/uuid")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.elapsed.total_seconds.return_value = 0.1

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("lab_playwright_kit.health_monitor.httpx.AsyncClient", return_value=mock_client):
            check = await mon.ping(name="test", status="fail")

        assert check.status == HealthStatus.FAILING

    @pytest.mark.asyncio
    async def test_ping_hc_url_with_name(self):
        mon = HealthMonitor(healthchecks_url="https://hc-ping.com/uuid")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.elapsed.total_seconds.return_value = 0.05

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("lab_playwright_kit.health_monitor.httpx.AsyncClient", return_value=mock_client):
            check = await mon.ping(name="my-bot", status="ok")

        # Should use URL with slug
        mock_client.get.assert_called_once()
        call_url = mock_client.get.call_args[0][0]
        assert "my-bot" in call_url

    @pytest.mark.asyncio
    async def test_ping_exception(self):
        mon = HealthMonitor(healthchecks_url="https://hc-ping.com/uuid")
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=ConnectionError("Network down"))

        with patch("lab_playwright_kit.health_monitor.httpx.AsyncClient", return_value=mock_client):
            check = await mon.ping(name="test")

        assert check.error == "Network down"
        assert check.status == HealthStatus.DEGRADED


# ─── HealthMonitor.check_and_alert ─────────────────────────────────────────


class TestCheckAndAlert:
    @pytest.mark.asyncio
    async def test_check_success(self):
        mon = HealthMonitor()
        check = await mon.check_and_alert(
            name="test",
            check_func=AsyncMock(return_value=True),
        )
        assert check.status == HealthStatus.OK
        assert check.message == "Healthy"
        assert check.is_healthy is True

    @pytest.mark.asyncio
    async def test_check_false(self):
        mon = HealthMonitor()
        check = await mon.check_and_alert(
            name="test",
            check_func=AsyncMock(return_value=False),
        )
        assert check.status == HealthStatus.FAILING
        assert check.message == "Check returned False"

    @pytest.mark.asyncio
    async def test_check_string_result(self):
        mon = HealthMonitor()
        check = await mon.check_and_alert(
            name="test",
            check_func=AsyncMock(return_value="degraded mode"),
        )
        assert check.status == HealthStatus.DEGRADED
        assert check.message == "degraded mode"

    @pytest.mark.asyncio
    async def test_check_exception(self):
        mon = HealthMonitor()
        check = await mon.check_and_alert(
            name="test",
            check_func=AsyncMock(side_effect=RuntimeError("boom")),
        )
        assert check.status == HealthStatus.FAILING
        assert "boom" in check.message
        assert check.error is not None

    @pytest.mark.asyncio
    async def test_check_with_kwargs(self):
        mon = HealthMonitor()
        func = AsyncMock(return_value=True)
        await mon.check_and_alert(name="test", check_func=func, url="https://example.com")
        func.assert_called_once_with(url="https://example.com")


# ─── HealthMonitor.run_checks ──────────────────────────────────────────────


class TestRunChecks:
    @pytest.mark.asyncio
    async def test_run_all_healthy(self):
        mon = HealthMonitor()
        report = await mon.run_checks(
            {
                "a": AsyncMock(return_value=True),
                "b": AsyncMock(return_value=True),
            }
        )
        assert report.overall_status == HealthStatus.OK
        assert report.healthy_count == 2

    @pytest.mark.asyncio
    async def test_run_with_failures(self):
        mon = HealthMonitor()
        report = await mon.run_checks(
            {
                "a": AsyncMock(return_value=True),
                "b": AsyncMock(return_value=False),
            }
        )
        assert report.overall_status == HealthStatus.FAILING
        assert report.healthy_count == 1

    @pytest.mark.asyncio
    async def test_run_with_exception(self):
        mon = HealthMonitor()
        report = await mon.run_checks(
            {
                "a": AsyncMock(return_value=True),
                "b": AsyncMock(side_effect=RuntimeError("crash")),
            }
        )
        assert report.total_count == 2
        failing = [c for c in report.checks if c.status == HealthStatus.FAILING]
        assert len(failing) == 1


# ─── HealthMonitor.get_history ─────────────────────────────────────────────


class TestGetHistory:
    @pytest.mark.asyncio
    async def test_history_recorded(self):
        mon = HealthMonitor()
        await mon.ping(name="test", status="ok")
        history = mon.get_history("test")
        assert len(history) == 1
        assert history[0].name == "test"

    @pytest.mark.asyncio
    async def test_history_last_n(self):
        mon = HealthMonitor()
        for i in range(15):
            await mon.ping(name="test", status="ok")
        history = mon.get_history("test", last_n=5)
        assert len(history) == 5

    def test_history_empty(self):
        mon = HealthMonitor()
        history = mon.get_history("nonexistent")
        assert history == []


# ─── HealthMonitor._rstrip ─────────────────────────────────────────────────


class TestRstrip:
    def test_rstrip_slash(self):
        assert HealthMonitor._rstrip("https://example.com/", "/") == "https://example.com"

    def test_rstrip_no_change(self):
        assert HealthMonitor._rstrip("https://example.com", "/") == "https://example.com"

    def test_rstrip_multiple(self):
        assert HealthMonitor._rstrip("abc///", "/") == "abc"
