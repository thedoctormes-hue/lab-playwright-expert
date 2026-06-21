"""
Extended tests for vpn_monitor.py — VPNMonitor, VPNServer, VPNCheckResult.

Covers: dataclasses, VPNMonitor methods (mocked aiohttp), report generation.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lab_playwright_kit.vpn_monitor import (
    DEFAULT_MAX_LOAD_TIME,
    DEFAULT_TIMEOUT,
    SiteCheck,
    VPNCheckResult,
    VPNMonitor,
    VPNMonitorReport,
    VPNServer,
    run_check,
)


# ─── VPNServer Tests ─────────────────────────────────────────────────────────


class TestVPNServer:
    def test_defaults(self):
        server = VPNServer(name="test", proxy_url="socks5://127.0.0.1:10808")
        assert server.name == "test"
        assert server.proxy_url == "socks5://127.0.0.1:10808"
        assert server.country == ""
        assert server.expected_ip == ""
        assert server.description == ""
        assert server.timeout == DEFAULT_TIMEOUT
        assert server.max_load_time == DEFAULT_MAX_LOAD_TIME
        assert len(server.test_sites) == 5  # first 5 from DEFAULT_TEST_SITES

    def test_full(self):
        server = VPNServer(
            name="poland",
            proxy_url="socks5://127.0.0.1:10808",
            country="PL",
            expected_ip="1.2.3.4",
            description="Poland VPN",
            timeout=30.0,
            max_load_time=5.0,
        )
        assert server.country == "PL"
        assert server.expected_ip == "1.2.3.4"
        assert server.timeout == 30.0
        assert server.max_load_time == 5.0

    def test_is_direct(self):
        server = VPNServer(name="direct", proxy_url=None)
        assert server.is_direct is True

    def test_is_not_direct(self):
        server = VPNServer(name="vpn", proxy_url="socks5://127.0.0.1:10808")
        assert server.is_direct is False

    def test_custom_test_sites(self):
        sites = ["https://google.com", "https://github.com"]
        server = VPNServer(name="test", proxy_url=None, test_sites=sites)
        assert server.test_sites == sites


# ─── SiteCheck Tests ─────────────────────────────────────────────────────────


class TestSiteCheck:
    def test_defaults(self):
        check = SiteCheck(url="https://example.com")
        assert check.url == "https://example.com"
        assert check.status == "ok"
        assert check.http_status == 0
        assert check.load_time == 0.0
        assert check.error == ""

    def test_down(self):
        check = SiteCheck(
            url="https://example.com", status="down", http_status=500, error="Server Error"
        )
        assert check.status == "down"
        assert check.http_status == 500

    def test_slow(self):
        check = SiteCheck(url="https://example.com", status="slow", load_time=15.0)
        assert check.status == "slow"
        assert check.load_time == 15.0


# ─── VPNCheckResult Tests ────────────────────────────────────────────────────


class TestVPNCheckResult:
    def test_defaults(self):
        result = VPNCheckResult(server_name="test", country="US", timestamp="2026-01-01")
        assert result.server_name == "test"
        assert result.country == "US"
        assert result.status == "ok"
        assert result.exit_ip == ""
        assert result.expected_ip == ""
        assert result.ip_match is True
        assert result.sites == []
        assert result.avg_load_time == 0.0
        assert result.error == ""

    def test_is_healthy(self):
        result = VPNCheckResult(server_name="test", country="US", timestamp="", status="ok")
        assert result.is_healthy is True

    def test_is_not_healthy(self):
        for status in ("degraded", "down", "error"):
            result = VPNCheckResult(server_name="test", country="US", timestamp="", status=status)
            assert result.is_healthy is False

    def test_is_down(self):
        for status in ("down", "error"):
            result = VPNCheckResult(server_name="test", country="US", timestamp="", status=status)
            assert result.is_down is True

    def test_is_not_down(self):
        for status in ("ok", "degraded"):
            result = VPNCheckResult(server_name="test", country="US", timestamp="", status=status)
            assert result.is_down is False

    def test_sites_ok(self):
        sites = [
            SiteCheck(url="https://a.com", status="ok"),
            SiteCheck(url="https://b.com", status="down"),
            SiteCheck(url="https://c.com", status="ok"),
        ]
        result = VPNCheckResult(server_name="test", country="US", timestamp="", sites=sites)
        assert result.sites_ok == 2
        assert result.sites_total == 3

    def test_sites_ok_empty(self):
        result = VPNCheckResult(server_name="test", country="US", timestamp="")
        assert result.sites_ok == 0
        assert result.sites_total == 0

    def test_to_dict(self):
        result = VPNCheckResult(
            server_name="test",
            country="US",
            status="ok",
            exit_ip="1.2.3.4",
            ip_match=True,
            avg_load_time=1.5,
        )
        d = result.to_dict()
        assert d["server_name"] == "test"
        assert d["status"] == "ok"
        assert d["exit_ip"] == "1.2.3.4"


# ─── VPNMonitorReport Tests ──────────────────────────────────────────────────


class TestVPNMonitorReport:
    def test_defaults(self):
        report = VPNMonitorReport(
            results=[],
            total_servers=0,
            healthy_count=0,
            degraded_count=0,
            down_count=0,
            check_duration=0,
        )
        assert report.all_healthy is True
        assert report.has_issues is False

    def test_all_healthy(self):
        report = VPNMonitorReport(
            results=[],
            total_servers=3,
            healthy_count=3,
            degraded_count=0,
            down_count=0,
            check_duration=1.0,
        )
        assert report.all_healthy is True
        assert report.has_issues is False

    def test_has_issues(self):
        report = VPNMonitorReport(
            results=[],
            total_servers=3,
            healthy_count=1,
            degraded_count=1,
            down_count=1,
            check_duration=1.0,
        )
        assert report.all_healthy is False
        assert report.has_issues is True

    def test_has_issues_degraded(self):
        report = VPNMonitorReport(
            results=[],
            total_servers=2,
            healthy_count=1,
            degraded_count=1,
            down_count=0,
            check_duration=1.0,
        )
        assert report.has_issues is True

    def test_has_issues_down(self):
        report = VPNMonitorReport(
            results=[],
            total_servers=2,
            healthy_count=1,
            degraded_count=0,
            down_count=1,
            check_duration=1.0,
        )
        assert report.has_issues is True

    def test_to_telegram_message(self):
        r = VPNCheckResult(
            server_name="poland",
            country="PL",
            timestamp="",
            status="ok",
            exit_ip="1.2.3.4",
            ip_match=True,
            avg_load_time=0.5,
        )
        report = VPNMonitorReport(
            results=[r],
            total_servers=1,
            healthy_count=1,
            degraded_count=0,
            down_count=0,
            check_duration=2.0,
        )
        msg = report.to_telegram_message()
        assert "VPN Monitor Report" in msg
        assert "poland" in msg
        assert "PL" in msg

    def test_to_telegram_message_with_degraded(self):
        r = VPNCheckResult(
            server_name="test", country="US", timestamp="", status="degraded", exit_ip=""
        )
        report = VPNMonitorReport(
            results=[r],
            total_servers=1,
            healthy_count=0,
            degraded_count=1,
            down_count=0,
            check_duration=1.0,
        )
        msg = report.to_telegram_message()
        assert "⚠️" in msg

    def test_to_telegram_message_with_down(self):
        r = VPNCheckResult(
            server_name="test",
            country="US",
            timestamp="",
            status="down",
            exit_ip="",
            error="timeout",
        )
        report = VPNMonitorReport(
            results=[r],
            total_servers=1,
            healthy_count=0,
            degraded_count=0,
            down_count=1,
            check_duration=1.0,
        )
        msg = report.to_telegram_message()
        assert "❌" in msg

    def test_to_dict(self):
        report = VPNMonitorReport(
            results=[],
            total_servers=2,
            healthy_count=2,
            degraded_count=0,
            down_count=0,
            check_duration=1.0,
        )
        d = report.to_dict()
        assert d["total_servers"] == 2
        assert d["healthy_count"] == 2
        assert d["all_healthy"] is True


# ─── VPNMonitor Tests ────────────────────────────────────────────────────────


class TestVPNMonitor:
    def test_init(self):
        monitor = VPNMonitor()
        assert monitor.servers == []
        assert monitor.get_history() == []

    def test_add_server(self):
        monitor = VPNMonitor()
        server = VPNServer(name="test", proxy_url="socks5://127.0.0.1:10808")
        monitor.add_server(server)
        assert len(monitor.servers) == 1

    def test_remove_server(self):
        monitor = VPNMonitor()
        monitor.add_server(VPNServer(name="keep", proxy_url=None))
        monitor.add_server(VPNServer(name="remove", proxy_url=None))
        monitor.remove_server("remove")
        assert len(monitor.servers) == 1
        assert monitor.servers[0].name == "keep"

    def test_remove_nonexistent(self):
        monitor = VPNMonitor()
        monitor.add_server(VPNServer(name="test", proxy_url=None))
        monitor.remove_server("nonexistent")
        assert len(monitor.servers) == 1

    @pytest.mark.asyncio
    async def test_check_server_success(self):
        monitor = VPNMonitor()
        server = VPNServer(name="direct", proxy_url=None, test_sites=["https://example.com"])

        with patch("lab_playwright_kit.vpn_monitor.aiohttp.ClientSession") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            # Mock IP check response
            mock_ip_resp = MagicMock()
            mock_ip_resp.status = 200
            mock_ip_resp.json = AsyncMock(return_value={"ip": "1.2.3.4"})

            # Mock site check response
            mock_site_resp = MagicMock()
            mock_site_resp.status = 200
            mock_site_resp.text = AsyncMock(return_value="<html>OK</html>")

            mock_session.get = MagicMock()
            mock_session.get.side_effect = [mock_ip_resp, mock_site_resp]
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            # Need to properly mock the context manager chain
            mock_cm = MagicMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            mock_session_cls.return_value = mock_cm

            result = await monitor.check_server(server)
            assert result.server_name == "direct"

    def test_from_vpn_manager(self):
        mock_manager = MagicMock()
        mock_proxy = MagicMock()
        mock_proxy.name = "test"
        mock_proxy.server = "socks5://127.0.0.1:10808"
        mock_proxy.country = "PL"
        mock_proxy.exit_ip = "1.2.3.4"
        mock_proxy.description = "Test"
        mock_manager.proxies = [mock_proxy]

        monitor = VPNMonitor.from_vpn_manager(mock_manager)
        assert len(monitor.servers) == 1
        assert monitor.servers[0].name == "test"

    def test_default_laboratory_servers(self):
        servers = VPNMonitor.default_laboratory_servers()
        assert len(servers) >= 2
        names = [s.name for s in servers]
        assert "poland" in names
        assert "florida" in names

    @pytest.mark.asyncio
    async def test_check_all_empty(self):
        monitor = VPNMonitor()
        report = await monitor.check_all()
        assert report.total_servers == 0
        assert report.all_healthy is True

    @pytest.mark.asyncio
    async def test_report_to_telegram_healthy(self):
        monitor = VPNMonitor()
        report = VPNMonitorReport(
            results=[],
            total_servers=0,
            healthy_count=0,
            degraded_count=0,
            down_count=0,
            check_duration=0,
        )
        result = await monitor.report_to_telegram(report, "token", "chat")
        assert result is True  # skipped because all healthy

    def test_get_history(self):
        monitor = VPNMonitor()
        # Manually add a report
        report = VPNMonitorReport(
            results=[],
            total_servers=0,
            healthy_count=0,
            degraded_count=0,
            down_count=0,
            check_duration=0,
        )
        monitor._history.append(report)
        assert len(monitor.get_history()) == 1


# ─── run_check Tests ─────────────────────────────────────────────────────────


class TestRunCheck:
    @pytest.mark.asyncio
    async def test_run_check_with_defaults(self):
        """run_check with default servers should return a report."""
        with patch.object(VPNMonitor, "check_all", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = VPNMonitorReport(
                results=[],
                total_servers=0,
                healthy_count=0,
                degraded_count=0,
                down_count=0,
                check_duration=0,
            )
            report = await run_check()
            assert isinstance(report, VPNMonitorReport)

    @pytest.mark.asyncio
    async def test_run_check_with_custom_servers(self):
        servers = [VPNServer(name="test", proxy_url=None)]
        with patch.object(VPNMonitor, "check_all", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = VPNMonitorReport(
                results=[],
                total_servers=1,
                healthy_count=1,
                degraded_count=0,
                down_count=0,
                check_duration=0,
            )
            report = await run_check(servers=servers)
            assert report.total_servers == 1
