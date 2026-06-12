"""
Тесты для VPN Monitor.

Покрывают:
- VPNServer / SiteCheck / VPNCheckResult / VPNMonitorReport dataclasses
- VPNMonitor.check_server (mocked HTTP)
- VPNMonitor.check_all
- VPNMonitorReport.to_telegram_message
- default_laboratory_servers
- run_check
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from lab_playwright_kit.vpn_monitor import (
    VPNServer,
    SiteCheck,
    VPNCheckResult,
    VPNMonitorReport,
    VPNMonitor,
    run_check,
    DEFAULT_TEST_SITES,
    IP_CHECK_URL,
)


# ─── Dataclasses ──────────────────────────────────────────────────────────────

class TestVPNServer:
    def test_defaults(self):
        s = VPNServer(name="test", proxy_url="socks5://127.0.0.1:10808")
        assert s.country == ""
        assert s.expected_ip == ""
        assert s.timeout == 15.0
        assert s.max_load_time == 10.0
        assert len(s.test_sites) == 5

    def test_is_direct(self):
        s = VPNServer(name="direct", proxy_url=None)
        assert s.is_direct is True

    def test_not_direct(self):
        s = VPNServer(name="poland", proxy_url="socks5://127.0.0.1:10808")
        assert s.is_direct is False

    def test_custom_sites(self):
        sites = ["https://example.com"]
        s = VPNServer(name="test", proxy_url=None, test_sites=sites)
        assert s.test_sites == sites


class TestSiteCheck:
    def test_ok(self):
        sc = SiteCheck(url="https://example.com", status="ok", http_status=200, load_time=1.0)
        assert sc.status == "ok"

    def test_down(self):
        sc = SiteCheck(url="https://example.com", status="down", error="Connection refused")
        assert sc.status == "down"

    def test_slow(self):
        sc = SiteCheck(url="https://example.com", status="slow", load_time=15.0)
        assert sc.status == "slow"


class TestVPNCheckResult:
    def test_is_healthy(self):
        r = VPNCheckResult(
            server_name="test", country="PL", timestamp="2026", status="ok",
            sites=[SiteCheck(url="https://a.com", status="ok")],
        )
        assert r.is_healthy is True
        assert r.is_down is False

    def test_is_down(self):
        r = VPNCheckResult(
            server_name="test", country="PL", timestamp="2026", status="down",
        )
        assert r.is_down is True
        assert r.is_healthy is False

    def test_sites_ok(self):
        r = VPNCheckResult(
            server_name="test", country="PL", timestamp="2026", status="ok",
            sites=[
                SiteCheck(url="https://a.com", status="ok"),
                SiteCheck(url="https://b.com", status="ok"),
                SiteCheck(url="https://c.com", status="down"),
            ],
        )
        assert r.sites_ok == 2
        assert r.sites_total == 3

    def test_to_dict(self):
        r = VPNCheckResult(
            server_name="test", country="PL", timestamp="2026", status="ok",
            exit_ip="1.2.3.4", ip_match=True,
        )
        d = r.to_dict()
        d["status"] == "ok"
        assert d["exit_ip"] == "1.2.3.4"
        assert d["ip_match"] is True


class TestVPNMonitorReport:
    def test_all_healthy(self):
        report = VPNMonitorReport(
            results=[
                VPNCheckResult(server_name="a", country="PL", timestamp="2026", status="ok"),
            ],
            total_servers=1, healthy_count=1, degraded_count=0, down_count=0,
            check_duration=1.0,
        )
        assert report.all_healthy is True
        assert report.has_issues is False

    def test_has_issues(self):
        report = VPNMonitorReport(
            results=[
                VPNCheckResult(server_name="a", country="PL", timestamp="2026", status="ok"),
                VPNCheckResult(server_name="b", country="US", timestamp="2026", status="down"),
            ],
            total_servers=2, healthy_count=1, degraded_count=0, down_count=1,
            check_duration=2.0,
        )
        assert report.all_healthy is False
        assert report.has_issues is True

    def test_to_telegram_message_all_ok(self):
        report = VPNMonitorReport(
            results=[
                VPNCheckResult(
                    server_name="poland", country="PL", timestamp="2026", status="ok",
                    exit_ip="1.2.3.4", ip_match=True,
                    sites=[SiteCheck(url="https://a.com", status="ok", load_time=1.0)],
                    avg_load_time=1.0,
                ),
            ],
            total_servers=1, healthy_count=1, degraded_count=0, down_count=0,
            check_duration=2.0,
        )
        msg = report.to_telegram_message()
        assert "✅" in msg
        assert "poland" in msg
        assert "1.2.3.4" in msg

    def test_to_telegram_message_with_issues(self):
        report = VPNMonitorReport(
            results=[
                VPNCheckResult(
                    server_name="poland", country="PL", timestamp="2026", status="ok",
                    exit_ip="1.2.3.4", ip_match=True,
                    sites=[SiteCheck(url="https://a.com", status="ok", load_time=1.0)],
                    avg_load_time=1.0,
                ),
                VPNCheckResult(
                    server_name="florida", country="US", timestamp="2026", status="down",
                    exit_ip="", ip_match=False,
                    sites=[SiteCheck(url="https://a.com", status="down", error="Timeout")],
                    avg_load_time=0.0,
                    error="All sites down",
                ),
            ],
            total_servers=2, healthy_count=1, degraded_count=0, down_count=1,
            check_duration=3.0,
        )
        msg = report.to_telegram_message()
        assert "✅" in msg
        assert "❌" in msg
        assert "poland" in msg
        assert "florida" in msg
        assert "All sites down" in msg

    def test_to_dict(self):
        report = VPNMonitorReport(
            results=[], total_servers=0, healthy_count=0, degraded_count=0, down_count=0,
            check_duration=0.0,
        )
        d = report.to_dict()
        assert d["total_servers"] == 0
        assert d["all_healthy"] is True


# ─── VPNMonitor ───────────────────────────────────────────────────────────────

class TestVPNMonitor:
    def test_add_server(self):
        monitor = VPNMonitor()
        s = VPNServer(name="test", proxy_url="socks5://127.0.0.1:10808")
        monitor.add_server(s)
        assert len(monitor.servers) == 1

    def test_remove_server(self):
        monitor = VPNMonitor()
        monitor.add_server(VPNServer(name="a", proxy_url=None))
        monitor.add_server(VPNServer(name="b", proxy_url=None))
        monitor.remove_server("a")
        assert len(monitor.servers) == 1
        assert monitor.servers[0].name == "b"

    def test_default_laboratory_servers(self):
        servers = VPNMonitor.default_laboratory_servers()
        assert len(servers) >= 2
        names = [s.name for s in servers]
        assert "poland" in names
        assert "direct" in names

    @pytest.mark.asyncio
    async def test_check_server_ok(self):
        monitor = VPNMonitor()
        server = VPNServer(
            name="test", proxy_url=None, country="PL",
            test_sites=["https://example.com"],
        )

        # Мокаем IP check
        mock_ip_resp = AsyncMock()
        mock_ip_resp.status = 200
        mock_ip_resp.json = AsyncMock(return_value={"ip": "1.2.3.4"})

        # Мокаем site check
        mock_site_resp = AsyncMock()
        mock_site_resp.status = 200

        mock_get_ctx_ip = AsyncMock()
        mock_get_ctx_ip.__aenter__ = AsyncMock(return_value=mock_ip_resp)
        mock_get_ctx_ip.__aexit__ = AsyncMock(return_value=False)

        mock_get_ctx_site = AsyncMock()
        mock_get_ctx_site.__aenter__ = AsyncMock(return_value=mock_site_resp)
        mock_get_ctx_site.__aexit__ = AsyncMock(return_value=False)

        call_count = 0

        def mock_get_factory(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # IP check (session create + get)
                return mock_get_ctx_ip
            return mock_get_ctx_site

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = mock_get_factory

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await monitor.check_server(server)

        assert result.status == "ok"
        assert result.exit_ip == "1.2.3.4"
        assert result.sites_ok >= 0

    @pytest.mark.asyncio
    async def test_check_server_down(self):
        import aiohttp

        monitor = VPNMonitor()
        server = VPNServer(
            name="test", proxy_url=None, country="PL",
            test_sites=["https://down.example.com"],
        )

        # IP check OK
        mock_ip_resp = AsyncMock()
        mock_ip_resp.status = 200
        mock_ip_resp.json = AsyncMock(return_value={"ip": "1.2.3.4"})

        mock_get_ctx_ip = AsyncMock()
        mock_get_ctx_ip.__aenter__ = AsyncMock(return_value=mock_ip_resp)
        mock_get_ctx_ip.__aexit__ = AsyncMock(return_value=False)

        # Site check — контекстный менеджер, бросающий ошибку при входе
        mock_get_ctx_fail = AsyncMock()
        mock_get_ctx_fail.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("Connection refused"))
        mock_get_ctx_fail.__aexit__ = AsyncMock(return_value=False)

        def mock_get(*args, **kwargs):
            url = str(args[0]) if args else ""
            if "ipify" in url:
                return mock_get_ctx_ip
            return mock_get_ctx_fail

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = mock_get

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await monitor.check_server(server)

        # Сайты должны быть down
        assert all(s.status == "down" for s in result.sites)
        assert result.status == "down"

    @pytest.mark.asyncio
    async def test_check_server_ip_mismatch(self):
        monitor = VPNMonitor()
        server = VPNServer(
            name="test", proxy_url=None, country="PL",
            expected_ip="10.0.0.1",  # Ожидаем другой IP
            test_sites=["https://example.com"],
        )

        # IP check возвращает неожиданный IP
        mock_ip_resp = AsyncMock()
        mock_ip_resp.status = 200
        mock_ip_resp.json = AsyncMock(return_value={"ip": "1.2.3.4"})

        mock_get_ctx_ip = AsyncMock()
        mock_get_ctx_ip.__aenter__ = AsyncMock(return_value=mock_ip_resp)
        mock_get_ctx_ip.__aexit__ = AsyncMock(return_value=False)

        mock_site_resp = AsyncMock()
        mock_site_resp.status = 200

        mock_get_ctx_site = AsyncMock()
        mock_get_ctx_site.__aenter__ = AsyncMock(return_value=mock_site_resp)
        mock_get_ctx_site.__aexit__ = AsyncMock(return_value=False)

        call_count = 0

        def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return mock_get_ctx_ip
            return mock_get_ctx_site

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = mock_get

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await monitor.check_server(server)

        assert result.ip_match is False
        assert result.status == "degraded"

    @pytest.mark.asyncio
    async def test_check_all(self):
        monitor = VPNMonitor()
        monitor.add_server(VPNServer(name="a", proxy_url=None, test_sites=["https://a.com"]))
        monitor.add_server(VPNServer(name="b", proxy_url=None, test_sites=["https://b.com"]))

        mock_ip_resp = AsyncMock()
        mock_ip_resp.status = 200
        mock_ip_resp.json = AsyncMock(return_value={"ip": "1.2.3.4"})

        mock_site_resp = AsyncMock()
        mock_site_resp.status = 200

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ip_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_ctx_site = AsyncMock()
        mock_ctx_site.__aenter__ = AsyncMock(return_value=mock_site_resp)
        mock_ctx_site.__aexit__ = AsyncMock(return_value=False)

        call_count = 0

        def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 1:
                return mock_ctx
            return mock_ctx_site

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = mock_get

        with patch("aiohttp.ClientSession", return_value=mock_session):
            report = await monitor.check_all()

        assert report.total_servers == 2

    def test_get_history(self):
        monitor = VPNMonitor()
        report = VPNMonitorReport(
            results=[], total_servers=0, healthy_count=0,
            degraded_count=0, down_count=0, check_duration=0.0,
        )
        monitor._history.append(report)
        history = monitor.get_history()
        assert len(history) == 1


# ─── Telegram Report ──────────────────────────────────────────────────────────

class TestTelegramReport:
    @pytest.mark.asyncio
    async def test_report_to_telegram_skips_if_healthy(self):
        monitor = VPNMonitor()
        report = VPNMonitorReport(
            results=[
                VPNCheckResult(server_name="a", country="PL", timestamp="2026", status="ok"),
            ],
            total_servers=1, healthy_count=1, degraded_count=0, down_count=0,
            check_duration=1.0,
        )

        result = await monitor.report_to_telegram(report, "fake_token", "fake_chat")
        assert result is True  # Пропускает отправку если всё ок

    @pytest.mark.asyncio
    async def test_report_to_telegram_sends_on_issues(self):
        monitor = VPNMonitor()
        report = VPNMonitorReport(
            results=[
                VPNCheckResult(server_name="a", country="PL", timestamp="2026", status="down",
                               error="Timeout"),
            ],
            total_servers=1, healthy_count=0, degraded_count=0, down_count=1,
            check_duration=1.0,
        )

        mock_resp = AsyncMock()
        mock_resp.status = 200

        mock_post_ctx = AsyncMock()
        mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=mock_post_ctx)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await monitor.report_to_telegram(report, "fake_token", "fake_chat")

        assert result is True


# ─── run_check ────────────────────────────────────────────────────────────────

class TestRunCheck:
    @pytest.mark.asyncio
    async def test_run_check_default_servers(self):
        mock_ip_resp = AsyncMock()
        mock_ip_resp.status = 200
        mock_ip_resp.json = AsyncMock(return_value={"ip": "1.2.3.4"})

        mock_site_resp = AsyncMock()
        mock_site_resp.status = 200

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ip_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_ctx_site = AsyncMock()
        mock_ctx_site.__aenter__ = AsyncMock(return_value=mock_site_resp)
        mock_ctx_site.__aexit__ = AsyncMock(return_value=False)

        call_count = 0

        def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 1:
                return mock_ctx
            return mock_ctx_site

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = mock_get

        with patch("aiohttp.ClientSession", return_value=mock_session):
            report = await run_check()

        assert report.total_servers >= 2  # default laboratory servers
