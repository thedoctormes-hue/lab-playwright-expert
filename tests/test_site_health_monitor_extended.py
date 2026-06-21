"""
Extended tests for site_health_monitor.py — SiteConfig, SiteCheckResult, HealthReport, SiteHealthMonitor.
"""

from unittest.mock import AsyncMock, patch

import pytest

from lab_playwright_kit.site_health_monitor import (
    HealthReport,
    SiteCheckResult,
    SiteConfig,
    SiteHealthMonitor,
    run_check,
)


class TestSiteConfig:
    def test_defaults(self):
        config = SiteConfig(url="https://example.com")
        assert config.url == "https://example.com"
        assert config.name == ""
        assert config.expected_status == 200
        assert config.expected_keywords == []
        assert config.timeout == 10.0
        assert config.max_load_time == 5.0
        assert config.check_ssl is True
        assert config.ssl_expiry_warning_days == 14

    def test_full(self):
        config = SiteConfig(
            url="https://example.com",
            name="Example",
            expected_status=200,
            expected_keywords=["Welcome", "Login"],
            timeout=15.0,
            max_load_time=3.0,
            check_ssl=False,
            ssl_expiry_warning_days=30,
        )
        assert config.name == "Example"
        assert config.timeout == 15.0
        assert config.check_ssl is False
        assert config.ssl_expiry_warning_days == 30


class TestSiteCheckResult:
    def test_defaults(self):
        result = SiteCheckResult(url="https://example.com")
        assert result.url == "https://example.com"
        assert result.name == ""
        assert result.status == "ok"
        assert result.http_status == 200
        assert result.load_time == 0.0
        assert result.ssl_valid is True
        assert result.ssl_expiry_days == -1
        assert result.keywords_found == []
        assert result.keywords_missing == []
        assert result.error == ""

    def test_is_healthy(self):
        result = SiteCheckResult(url="https://example.com", status="ok")
        assert result.is_healthy is True

    def test_is_not_healthy(self):
        for s in ("down", "degraded", "error"):
            result = SiteCheckResult(url="https://example.com", status=s)
            assert result.is_healthy is False

    def test_to_dict(self):
        result = SiteCheckResult(
            url="https://example.com", status="ok", http_status=200, load_time=0.5
        )
        d = result.to_dict()
        assert d["url"] == "https://example.com"
        assert d["status"] == "ok"


class TestHealthReport:
    def test_defaults(self):
        report = HealthReport()
        assert report.results == []
        assert report.total_sites == 0
        assert report.healthy_count == 0
        assert report.degraded_count == 0
        assert report.down_count == 0
        assert report.check_duration == 0.0
        assert report.all_healthy is True

    def test_all_healthy(self):
        report = HealthReport(
            results=[SiteCheckResult(url="https://a.com", status="ok")],
            total_sites=1,
            healthy_count=1,
            degraded_count=0,
            down_count=0,
        )
        assert report.all_healthy is True

    def test_has_issues(self):
        report = HealthReport(
            results=[
                SiteCheckResult(url="https://a.com", status="ok"),
                SiteCheckResult(url="https://b.com", status="down"),
            ],
            total_sites=2,
            healthy_count=1,
            degraded_count=0,
            down_count=1,
        )
        assert report.all_healthy is False

    def test_to_dict(self):
        report = HealthReport(
            total_sites=2, healthy_count=1, degraded_count=1, down_count=0, check_duration=3.0
        )
        d = report.to_dict()
        assert d["total_sites"] == 2
        assert d["healthy_count"] == 1
        assert d["all_healthy"] is False


class TestSiteHealthMonitor:
    def test_init(self):
        monitor = SiteHealthMonitor()
        assert monitor.sites == []
        assert monitor.get_history() == []

    def test_add_site(self):
        monitor = SiteHealthMonitor()
        config = SiteConfig(url="https://example.com")
        monitor.add_site(config)
        assert len(monitor.sites) == 1

    def test_remove_site(self):
        monitor = SiteHealthMonitor()
        monitor.add_site(SiteConfig(url="https://keep.com"))
        monitor.add_site(SiteConfig(url="https://remove.com"))
        monitor.remove_site("https://remove.com")
        assert len(monitor.sites) == 1
        assert monitor.sites[0].url == "https://keep.com"

    def test_remove_nonexistent(self):
        monitor = SiteHealthMonitor()
        monitor.add_site(SiteConfig(url="https://test.com"))
        monitor.remove_site("https://nonexistent.com")
        assert len(monitor.sites) == 1

    @pytest.mark.asyncio
    async def test_check_all_empty(self):
        monitor = SiteHealthMonitor()
        report = await monitor.check_all()
        assert report.total_sites == 0
        assert report.all_healthy is True

    @pytest.mark.asyncio
    async def test_check_all_with_sites(self):
        monitor = SiteHealthMonitor()
        monitor.add_site(SiteConfig(url="https://example.com"))
        with patch.object(monitor, "check_site", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = SiteCheckResult(url="https://example.com", status="ok")
            report = await monitor.check_all()
            assert report.total_sites == 1

    def test_get_history(self):
        monitor = SiteHealthMonitor()
        report = HealthReport()
        monitor._history.append(report)
        assert len(monitor.get_history()) == 1

    def test_default_laboratory_sites(self):
        sites = SiteHealthMonitor.default_laboratory_sites()
        assert len(sites) >= 1
        urls = [s.url for s in sites]
        assert any("example.com" in u for u in urls)


class TestRunCheck:
    @pytest.mark.asyncio
    async def test_run_check_with_defaults(self):
        with patch.object(SiteHealthMonitor, "check_all", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = HealthReport()
            report = await run_check()
            assert isinstance(report, HealthReport)
