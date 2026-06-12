"""
Тесты для Site Health Monitor.

Покрывают:
- SiteConfig / SiteCheckResult / HealthReport dataclasses
- SiteHealthMonitor.check_site (mocked HTTP)
- HealthReport.to_telegram_message
- default_laboratory_sites
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from lab_playwright_kit.site_health_monitor import (
    SiteConfig,
    SiteCheckResult,
    HealthReport,
    SiteHealthMonitor,
    run_check,
)


# ─── Dataclasses ──────────────────────────────────────────────────────────────

class TestSiteConfig:
    def test_defaults(self):
        site = SiteConfig(url="https://example.com", name="Example")
        assert site.expected_status == 200
        assert site.timeout == 15.0
        assert site.max_load_time == 5.0
        assert site.check_ssl is True
        assert site.ssl_expiry_warning_days == 14

    def test_custom_values(self):
        site = SiteConfig(
            url="https://example.com",
            name="Example",
            expected_status=301,
            timeout=30.0,
            check_ssl=False,
        )
        assert site.expected_status == 301
        assert site.timeout == 30.0
        assert site.check_ssl is False


class TestSiteCheckResult:
    def test_is_healthy(self):
        r = SiteCheckResult(url="https://x.com", name="X", timestamp="2026-01-01", status="ok")
        assert r.is_healthy is True
        assert r.is_down is False

    def test_is_down(self):
        r = SiteCheckResult(url="https://x.com", name="X", timestamp="2026-01-01", status="down")
        assert r.is_down is True
        assert r.is_healthy is False

    def test_is_error(self):
        r = SiteCheckResult(url="https://x.com", name="X", timestamp="2026-01-01", status="error")
        assert r.is_down is True

    def test_to_dict(self):
        r = SiteCheckResult(
            url="https://x.com", name="X", timestamp="2026-01-01",
            status="ok", http_status=200, load_time=1.5,
        )
        d = r.to_dict()
        assert d["status"] == "ok"
        assert d["http_status"] == 200
        assert d["load_time"] == 1.5


class TestHealthReport:
    def test_all_healthy(self):
        report = HealthReport(
            results=[
                SiteCheckResult(url="https://a.com", name="A", timestamp="2026", status="ok"),
                SiteCheckResult(url="https://b.com", name="B", timestamp="2026", status="ok"),
            ],
            total_sites=2, healthy_count=2, degraded_count=0, down_count=0,
        )
        assert report.all_healthy is True
        assert report.has_issues is False

    def test_has_issues(self):
        report = HealthReport(
            results=[
                SiteCheckResult(url="https://a.com", name="A", timestamp="2026", status="ok"),
                SiteCheckResult(url="https://b.com", name="B", timestamp="2026", status="down"),
            ],
            total_sites=2, healthy_count=1, degraded_count=0, down_count=1,
        )
        assert report.all_healthy is False
        assert report.has_issues is True

    def test_to_telegram_message_all_ok(self):
        report = HealthReport(
            results=[
                SiteCheckResult(url="https://a.com", name="Site A", timestamp="2026", status="ok",
                                http_status=200, load_time=1.0, ssl_valid=True),
            ],
            total_sites=1, healthy_count=1, degraded_count=0, down_count=0,
            check_duration=2.0,
        )
        msg = report.to_telegram_message()
        assert "✅" in msg
        assert "Site A" in msg
        assert "1✅" in msg

    def test_to_telegram_message_with_issues(self):
        report = HealthReport(
            results=[
                SiteCheckResult(url="https://a.com", name="Site A", timestamp="2026", status="ok",
                                http_status=200, load_time=1.0, ssl_valid=True),
                SiteCheckResult(url="https://b.com", name="Site B", timestamp="2026", status="down",
                                http_status=500, load_time=0.0, ssl_valid=False,
                                error="Connection refused"),
            ],
            total_sites=2, healthy_count=1, degraded_count=0, down_count=1,
            check_duration=3.0,
        )
        msg = report.to_telegram_message()
        assert "✅" in msg
        assert "❌" in msg
        assert "Site A" in msg
        assert "Site B" in msg
        assert "Connection refused" in msg

    def test_to_dict(self):
        report = HealthReport(
            results=[],
            total_sites=0, healthy_count=0, degraded_count=0, down_count=0,
        )
        d = report.to_dict()
        assert d["total_sites"] == 0
        assert d["all_healthy"] is True


# ─── SiteHealthMonitor ────────────────────────────────────────────────────────

class TestSiteHealthMonitor:
    def test_add_site(self):
        monitor = SiteHealthMonitor()
        site = SiteConfig(url="https://example.com", name="Example")
        monitor.add_site(site)
        assert len(monitor.sites) == 1

    def test_remove_site(self):
        monitor = SiteHealthMonitor()
        monitor.add_site(SiteConfig(url="https://a.com", name="A"))
        monitor.add_site(SiteConfig(url="https://b.com", name="B"))
        monitor.remove_site("https://a.com")
        assert len(monitor.sites) == 1
        assert monitor.sites[0].url == "https://b.com"

    def test_default_laboratory_sites(self):
        sites = SiteHealthMonitor.default_laboratory_sites()
        assert len(sites) >= 2
        urls = [s.url for s in sites]
        assert "https://snablab.shtab-ai.ru" in urls
        assert "https://articles.shtab-ai.ru" in urls

    @pytest.mark.asyncio
    async def test_check_site_ok(self):
        monitor = SiteHealthMonitor()
        site = SiteConfig(
            url="https://example.com",
            name="Example",
            expected_keywords=["Example"],
            check_ssl=False,
        )

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.text = AsyncMock(return_value="<html>Example Domain</html>")

        mock_get_ctx = AsyncMock()
        mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_get_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_get_ctx)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await monitor.check_site(site)

        assert result.status == "ok"
        assert result.http_status == 200
        assert "Example" in result.keywords_found

    @pytest.mark.asyncio
    async def test_check_site_down(self):
        monitor = SiteHealthMonitor()
        site = SiteConfig(url="https://down.example.com", name="Down", check_ssl=False)

        import aiohttp

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(side_effect=aiohttp.ClientError("Connection refused"))

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await monitor.check_site(site)

        assert result.status == "down"
        assert "Connection refused" in result.error

    @pytest.mark.asyncio
    async def test_check_site_timeout(self):
        monitor = SiteHealthMonitor()
        site = SiteConfig(url="https://slow.example.com", name="Slow", timeout=1.0, check_ssl=False)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(side_effect=asyncio.TimeoutError())

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await monitor.check_site(site)

        assert result.status == "down"
        assert "Timeout" in result.error

    @pytest.mark.asyncio
    async def test_check_site_wrong_status(self):
        monitor = SiteHealthMonitor()
        site = SiteConfig(url="https://error.example.com", name="Error", check_ssl=False)

        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.text = AsyncMock(return_value="<html>Internal Server Error</html>")

        mock_get_ctx = AsyncMock()
        mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_get_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_get_ctx)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await monitor.check_site(site)

        assert result.status == "down"
        assert result.http_status == 500

    @pytest.mark.asyncio
    async def test_check_site_slow(self):
        import time as _time

        monitor = SiteHealthMonitor()
        site = SiteConfig(url="https://slow.example.com", name="Slow",
                          max_load_time=0.001, check_ssl=False)

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.text = AsyncMock(return_value="<html>OK</html>")

        mock_get_ctx = AsyncMock()
        mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_get_ctx.__aexit__ = AsyncMock(return_value=False)

        def slow_get(*args, **kwargs):
            _time.sleep(0.05)  # синхронная задержка — имитируем медленный ответ
            return mock_get_ctx

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = slow_get

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await monitor.check_site(site)

        assert result.status == "degraded"

    @pytest.mark.asyncio
    async def test_check_all(self):
        monitor = SiteHealthMonitor()
        monitor.add_site(SiteConfig(url="https://a.com", name="A", check_ssl=False))
        monitor.add_site(SiteConfig(url="https://b.com", name="B", check_ssl=False))

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.text = AsyncMock(return_value="<html>OK</html>")

        mock_get_ctx = AsyncMock()
        mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_get_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_get_ctx)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            report = await monitor.check_all()

        assert report.total_sites == 2
        assert report.healthy_count == 2
        assert report.all_healthy is True

    @pytest.mark.asyncio
    async def test_check_all_with_exception(self):
        monitor = SiteHealthMonitor()
        monitor.add_site(SiteConfig(url="https://a.com", name="A", check_ssl=False))

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(side_effect=Exception("Unexpected error"))

        with patch("aiohttp.ClientSession", return_value=mock_session):
            report = await monitor.check_all()

        assert report.total_sites == 1
        assert report.down_count == 1

    def test_get_history(self):
        monitor = SiteHealthMonitor()
        report = HealthReport()
        monitor._history.append(report)
        history = monitor.get_history()
        assert len(history) == 1


# ─── Telegram Report ──────────────────────────────────────────────────────────

class TestTelegramReport:
    @pytest.mark.asyncio
    async def test_report_to_telegram_skips_if_healthy(self):
        monitor = SiteHealthMonitor()
        report = HealthReport(
            results=[SiteCheckResult(url="https://a.com", name="A", timestamp="2026", status="ok")],
            total_sites=1, healthy_count=1, degraded_count=0, down_count=0,
        )

        result = await monitor.report_to_telegram(report, "fake_token", "fake_chat")
        assert result is True  # Пропускает отправку если всё ок

    @pytest.mark.asyncio
    async def test_report_to_telegram_sends_on_issues(self):
        monitor = SiteHealthMonitor()
        report = HealthReport(
            results=[
                SiteCheckResult(url="https://a.com", name="A", timestamp="2026", status="down",
                                error="500"),
            ],
            total_sites=1, healthy_count=0, degraded_count=0, down_count=1,
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
    async def test_run_check_default_sites(self):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.text = AsyncMock(return_value="<html>OK</html>")

        mock_get_ctx = AsyncMock()
        mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_get_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_get_ctx)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            report = await run_check()

        assert report.total_sites >= 2  # default laboratory sites
