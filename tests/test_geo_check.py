"""
Тесты для Geo-Check модуля.

Проверяет определение геолокации через разные прокси.
"""
from __future__ import annotations

import pytest

from lab_playwright_kit.geo_check import (
    GeoCheckReport,
    GeoChecker,
    GeoResult,
)


class TestGeoResult:
    """Тесты GeoResult dataclass."""

    def test_default_values(self):
        r = GeoResult()
        assert r.ip == ""
        assert r.country == ""
        assert r.is_success is False
        assert r.is_match is True  # direct = match

    def test_is_success_with_ip(self):
        r = GeoResult(ip="1.2.3.4", country="PL")
        assert r.is_success is True

    def test_is_success_with_error(self):
        r = GeoResult(error="timeout")
        assert r.is_success is False

    def test_is_match_proxy_poland(self):
        r = GeoResult(country="PL", proxy_used="poland")
        assert r.is_match is True

    def test_is_match_proxy_poland_wrong_country(self):
        r = GeoResult(country="US", proxy_used="poland")
        assert r.is_match is False

    def test_is_match_proxy_florida(self):
        r = GeoResult(country="US", proxy_used="florida")
        assert r.is_match is True

    def test_is_match_direct(self):
        r = GeoResult(country="RU", proxy_used="direct")
        assert r.is_match is True

    def test_summary_success(self):
        r = GeoResult(
            ip="1.2.3.4",
            country="PL",
            country_name="Poland",
            city="Warsaw",
            isp="Hetzner",
            proxy_used="poland",
            response_ms=150.0,
        )
        s = r.summary
        assert "✅" in s
        assert "Poland" in s
        assert "1.2.3.4" in s

    def test_summary_error(self):
        r = GeoResult(error="Connection refused")
        s = r.summary
        assert "❌" in s
        assert "Connection refused" in s


class TestGeoCheckReport:
    """Тесты GeoCheckReport."""

    def test_empty_report(self):
        report = GeoCheckReport()
        assert report.total_checks == 0
        assert report.successful == 0
        assert report.failed == 0

    def test_report_stats(self):
        report = GeoCheckReport(
            results=[
                GeoResult(ip="1.2.3.4", country="PL", proxy_used="poland"),
                GeoResult(ip="5.6.7.8", country="US", proxy_used="florida"),
                GeoResult(error="timeout"),
            ]
        )
        assert report.total_checks == 3
        assert report.successful == 2
        assert report.failed == 1
        assert report.proxy_match == 2
        assert report.proxy_mismatch == 0

    def test_report_mismatch(self):
        report = GeoCheckReport(
            results=[
                GeoResult(ip="1.2.3.4", country="US", proxy_used="poland"),  # mismatch
                GeoResult(ip="5.6.7.8", country="PL", proxy_used="florida"),  # mismatch
            ]
        )
        assert report.proxy_match == 0
        assert report.proxy_mismatch == 2

    def test_report_summary(self):
        report = GeoCheckReport(
            results=[
                GeoResult(ip="1.2.3.4", country="PL", proxy_used="poland"),
            ]
        )
        s = report.summary()
        assert "Total: 1" in s
        assert "OK: 1" in s


class TestGeoChecker:
    """Тесты GeoChecker."""

    def test_init_default(self):
        checker = GeoChecker()
        assert checker._timeout == 10.0
        assert checker._proxy_manager is not None

    def test_init_custom(self):
        checker = GeoChecker(timeout=5.0)
        assert checker._timeout == 5.0

    def test_extract_field_simple(self):
        data = {"ip": "1.2.3.4", "country": "PL"}
        assert GeoChecker._extract_field(data, "ip") == "1.2.3.4"
        assert GeoChecker._extract_field(data, "country") == "PL"

    def test_extract_field_nested(self):
        data = {"timezone": {"id": "Europe/Moscow"}}
        assert GeoChecker._extract_field(data, "timezone.id") == "Europe/Moscow"

    def test_extract_field_missing(self):
        data = {"ip": "1.2.3.4"}
        assert GeoChecker._extract_field(data, "missing") is None

    def test_extract_field_empty_string(self):
        data = {"ip": "1.2.3.4"}
        assert GeoChecker._extract_field(data, "") is None

    def test_extract_field_nested_with_key(self):
        data = {"connection": {"org": "Hetzner"}}
        assert GeoChecker._extract_field(data, "connection", nested_key="org") == "Hetzner"
