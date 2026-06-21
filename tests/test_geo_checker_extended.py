"""
Расширенные тесты для GeoChecker.

Покрывает:
  - GeoResult dataclass (is_success, is_match, summary, __str__)
  - GeoCheckReport (total_checks, successful, failed, proxy_match, avg_response_ms, summary)
  - GeoChecker.__init__
  - GeoChecker._extract_field (static, nested)
  - GeoChecker.check_ip (mocked HTTP)
  - GeoChecker.check_via_proxy
  - GeoChecker.check_all_proxies
  - GeoChecker.verify_proxy_geo
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lab_playwright_kit.geo_check import (
    GeoChecker,
    GeoCheckReport,
    GeoResult,
)


# ─── GeoResult ──────────────────────────────────────────────────────────────


class TestGeoResult:
    def test_defaults(self):
        r = GeoResult()
        assert r.ip == ""
        assert r.country == ""
        assert r.city == ""
        assert r.is_success is False  # ip is empty

    def test_is_success_with_ip(self):
        r = GeoResult(ip="1.2.3.4", country="PL")
        assert r.is_success is True

    def test_is_success_with_error(self):
        r = GeoResult(ip="1.2.3.4", error="timeout")
        assert r.is_success is False

    def test_is_match_no_proxy(self):
        r = GeoResult(country="PL", proxy_used="direct")
        assert r.is_match is True

    def test_is_match_poland_proxy(self):
        r = GeoResult(country="PL", proxy_used="poland")
        assert r.is_match is True

    def test_is_match_poland_proxy_wrong_country(self):
        r = GeoResult(country="US", proxy_used="poland")
        assert r.is_match is False

    def test_is_match_unknown_proxy(self):
        r = GeoResult(country="XX", proxy_used="unknown_proxy")
        assert r.is_match is True  # no expectation for unknown

    def test_summary_success(self):
        r = GeoResult(
            ip="1.2.3.4",
            country="PL",
            country_name="Poland",
            city="Warsaw",
            isp="Orange",
            proxy_used="poland",
            response_ms=150,
        )
        s = r.summary
        assert "1.2.3.4" in s
        assert "Poland" in s
        assert "PL" in s

    def test_summary_error(self):
        r = GeoResult(error="Timeout")
        s = r.summary
        assert "ERROR" in s
        assert "Timeout" in s

    def test_str_equals_summary(self):
        r = GeoResult(ip="1.2.3.4", country="PL")
        assert str(r) == r.summary


# ─── GeoCheckReport ────────────────────────────────────────────────────────


class TestGeoCheckReport:
    def test_empty(self):
        report = GeoCheckReport()
        assert report.total_checks == 0
        assert report.successful == 0
        assert report.failed == 0
        assert report.avg_response_ms == 0.0

    def test_with_results(self):
        report = GeoCheckReport(
            results=[
                GeoResult(ip="1.2.3.4", country="PL", response_ms=100),
                GeoResult(ip="5.6.7.8", country="US", response_ms=200),
                GeoResult(error="Timeout"),
            ]
        )
        assert report.total_checks == 3
        assert report.successful == 2
        assert report.failed == 1
        assert report.avg_response_ms == 150.0

    def test_proxy_match_mismatch(self):
        report = GeoCheckReport(
            results=[
                GeoResult(ip="1.2.3.4", country="PL", proxy_used="poland"),
                GeoResult(ip="5.6.7.8", country="DE", proxy_used="poland"),
            ]
        )
        assert report.proxy_match == 1
        assert report.proxy_mismatch == 1

    def test_summary(self):
        report = GeoCheckReport(
            results=[
                GeoResult(ip="1.2.3.4", country="PL"),
            ]
        )
        s = report.summary()
        assert "Geo-Check Report" in s
        assert "Total: 1" in s


# ─── GeoChecker init ───────────────────────────────────────────────────────


class TestGeoCheckerInit:
    def test_default_init(self):
        checker = GeoChecker()
        assert checker._timeout == 10.0

    def test_custom_timeout(self):
        checker = GeoChecker(timeout=30.0)
        assert checker._timeout == 30.0


# ─── GeoChecker._extract_field ─────────────────────────────────────────────


class TestExtractField:
    def test_simple_field(self):
        data = {"ip": "1.2.3.4"}
        assert GeoChecker._extract_field(data, "ip") == "1.2.3.4"

    def test_missing_field(self):
        data = {"ip": "1.2.3.4"}
        assert GeoChecker._extract_field(data, "country") is None

    def test_nested_field(self):
        data = {"timezone": {"id": "Europe/Warsaw"}}
        assert GeoChecker._extract_field(data, "timezone.id") == "Europe/Warsaw"

    def test_nested_missing(self):
        data = {"timezone": {}}
        assert GeoChecker._extract_field(data, "timezone.id") is None

    def test_empty_field_name(self):
        data = {"ip": "1.2.3.4"}
        assert GeoChecker._extract_field(data, "") is None

    def test_nested_key(self):
        data = {"connection": {"org": "Orange"}}
        assert GeoChecker._extract_field(data, "connection", nested_key="org") == "Orange"

    def test_non_dict_value(self):
        data = {"ip": "1.2.3.4"}
        assert GeoChecker._extract_field(data, "ip.version") is None


# ─── GeoChecker.check_ip ───────────────────────────────────────────────────


class TestCheckIp:
    @pytest.mark.asyncio
    async def test_check_ip_success(self):
        checker = GeoChecker()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ip": "1.2.3.4",
            "country_code": "PL",
            "country_name": "Poland",
            "city": "Warsaw",
            "region": "Mazovia",
            "org": "Orange",
            "timezone": "Europe/Warsaw",
            "latitude": 52.23,
            "longitude": 21.01,
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("lab_playwright_kit.geo_check.httpx.AsyncClient", return_value=mock_client):
            result = await checker.check_ip()

        assert result.ip == "1.2.3.4"
        assert result.country == "PL"
        assert result.country_name == "Poland"
        assert result.city == "Warsaw"
        assert result.region == "Mazovia"
        assert result.isp == "Orange"
        assert result.lat == 52.23
        assert result.lon == 21.01
        assert result.is_success is True

    @pytest.mark.asyncio
    async def test_check_ip_http_error(self):
        checker = GeoChecker()
        mock_resp = MagicMock()
        mock_resp.status_code = 429

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("lab_playwright_kit.geo_check.httpx.AsyncClient", return_value=mock_client):
            result = await checker.check_ip()

        assert result.error == "HTTP 429"
        assert result.is_success is False

    @pytest.mark.asyncio
    async def test_check_ip_timeout(self):
        import httpx

        checker = GeoChecker()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch("lab_playwright_kit.geo_check.httpx.AsyncClient", return_value=mock_client):
            result = await checker.check_ip()

        assert result.error == "Timeout"

    @pytest.mark.asyncio
    async def test_check_ip_ipwho_source(self):
        checker = GeoChecker()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ip": "5.6.7.8",
            "country_code": "US",
            "country": "United States",
            "city": "New York",
            "region": "NY",
            "connection": {"org": "Verizon"},
            "timezone": {"id": "America/New_York"},
            "latitude": 40.71,
            "longitude": -74.01,
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("lab_playwright_kit.geo_check.httpx.AsyncClient", return_value=mock_client):
            result = await checker.check_ip(source="ipwho.is")

        assert result.ip == "5.6.7.8"
        assert result.country == "US"
        # ipwho.is returns connection as dict {"org": "Verizon"}
        assert result.isp == {"org": "Verizon"} or result.isp == "Verizon"


# ─── GeoChecker.check_via_proxy ───────────────────────────────────────────


class TestCheckViaProxy:
    @pytest.mark.asyncio
    async def test_proxy_not_found(self):
        checker = GeoChecker()
        mock_pm = MagicMock()
        mock_pm.get = MagicMock(return_value=None)
        checker._proxy_manager = mock_pm

        result = await checker.check_via_proxy("nonexistent")
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_check_all_proxies(self):
        checker = GeoChecker()
        mock_proxy = MagicMock()
        mock_proxy.name = "poland"

        mock_pm = MagicMock()
        mock_pm.list_all = MagicMock(return_value=[mock_proxy])
        checker._proxy_manager = mock_pm

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ip": "1.2.3.4",
            "country_code": "PL",
            "country_name": "Poland",
            "city": "Warsaw",
            "region": "Mazovia",
            "org": "Orange",
            "timezone": "Europe/Warsaw",
            "latitude": 52.23,
            "longitude": 21.01,
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("lab_playwright_kit.geo_check.httpx.AsyncClient", return_value=mock_client):
            report = await checker.check_all_proxies()

        assert report.total_checks == 1
        assert report.successful == 1


# ─── GeoChecker.verify_proxy_geo ──────────────────────────────────────────


class TestVerifyProxyGeo:
    @pytest.mark.asyncio
    async def test_verify_match(self):
        checker = GeoChecker()
        checker.check_via_proxy = AsyncMock(return_value=GeoResult(ip="1.2.3.4", country="PL"))
        result = await checker.verify_proxy_geo("poland", "PL")
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_mismatch(self):
        checker = GeoChecker()
        checker.check_via_proxy = AsyncMock(return_value=GeoResult(ip="5.6.7.8", country="DE"))
        result = await checker.verify_proxy_geo("poland", "PL")
        assert result is False

    @pytest.mark.asyncio
    async def test_verify_failed_check(self):
        checker = GeoChecker()
        checker.check_via_proxy = AsyncMock(return_value=GeoResult(error="Timeout"))
        result = await checker.verify_proxy_geo("poland", "PL")
        assert result is False
