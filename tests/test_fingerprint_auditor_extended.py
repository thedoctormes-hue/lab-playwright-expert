"""
Extended tests for fingerprint_auditor.py — FingerprintIssue, FingerprintReport, FingerprintAuditor.

Covers: dataclasses, audit logic, Severity enum.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from lab_playwright_kit.fingerprint_auditor import (
    FingerprintAuditor,
    FingerprintIssue,
    FingerprintReport,
    Severity,
)


class TestSeverity:
    def test_values(self):
        assert Severity.CRITICAL == "critical"
        assert Severity.WARNING == "warning"
        assert Severity.INFO == "info"


class TestFingerprintIssue:
    def test_defaults(self):
        issue = FingerprintIssue()
        assert issue.check == ""
        assert issue.severity == "warning"
        assert issue.expected == ""
        assert issue.actual == ""
        assert issue.recommendation == ""

    def test_full(self):
        issue = FingerprintIssue(
            check="webgl_vendor",
            severity="critical",
            expected="Google Inc.",
            actual="Mesa",
            recommendation="Use GPU spoofing",
        )
        assert issue.check == "webgl_vendor"
        assert issue.severity == "critical"

    def test_to_dict(self):
        issue = FingerprintIssue(check="canvas", severity="info", expected="noise", actual="clean")
        d = issue.to_dict()
        assert d["check"] == "canvas"
        assert d["severity"] == "info"


class TestFingerprintReport:
    def test_defaults(self):
        report = FingerprintReport()
        assert report.issues == []
        assert report.score == 0
        assert report.checks_passed == 0
        assert report.checks_total == 0
        assert report.timestamp == ""

    def test_pass_rate(self):
        report = FingerprintReport(checks_passed=8, checks_total=10)
        assert report.pass_rate == 80.0

    def test_pass_rate_zero(self):
        report = FingerprintReport(checks_passed=0, checks_total=0)
        assert report.pass_rate == 0.0

    def test_has_critical(self):
        report = FingerprintReport(
            issues=[
                FingerprintIssue(severity="critical"),
                FingerprintIssue(severity="warning"),
            ]
        )
        assert report.has_critical is True

    def test_no_critical(self):
        report = FingerprintReport(
            issues=[
                FingerprintIssue(severity="warning"),
                FingerprintIssue(severity="info"),
            ]
        )
        assert report.has_critical is False

    def test_critical_issues(self):
        report = FingerprintReport(
            issues=[
                FingerprintIssue(severity="critical", check="webgl"),
                FingerprintIssue(severity="warning", check="canvas"),
                FingerprintIssue(severity="critical", check="audio"),
            ]
        )
        assert len(report.critical_issues) == 2

    def test_is_consistent(self):
        report = FingerprintReport(issues=[])
        assert report.is_consistent is True

    def test_is_not_consistent(self):
        report = FingerprintReport(issues=[FingerprintIssue(severity="critical")])
        assert report.is_consistent is False

    def test_warnings(self):
        report = FingerprintReport(
            issues=[
                FingerprintIssue(severity="warning", check="a"),
                FingerprintIssue(severity="critical", check="b"),
                FingerprintIssue(severity="warning", check="c"),
            ]
        )
        assert len(report.warnings) == 2

    def test_to_dict(self):
        report = FingerprintReport(score=85, checks_passed=17, checks_total=20)
        d = report.to_dict()
        assert d["score"] == 85
        assert d["checks_passed"] == 17
        assert d["pass_rate"] == 85.0


class TestFingerprintAuditor:
    def test_init_default(self):
        auditor = FingerprintAuditor()
        assert auditor.strict is False

    def test_init_strict(self):
        auditor = FingerprintAuditor(strict=True)
        assert auditor.strict is True

    def test_ua_platform_map(self):
        assert "Windows" in FingerprintAuditor.UA_PLATFORM_MAP
        assert "MacIntel" in FingerprintAuditor.UA_PLATFORM_MAP

    def test_os_gpu_map(self):
        assert "windows" in FingerprintAuditor.OS_GPU_MAP
        assert "macos" in FingerprintAuditor.OS_GPU_MAP

    @pytest.mark.asyncio
    async def test_audit_page_returns_report(self):
        auditor = FingerprintAuditor()
        mock_page = MagicMock()
        mock_page.evaluate = AsyncMock(return_value={"webgl_vendor": "Google Inc."})
        report = await auditor.audit_page(mock_page)
        assert isinstance(report, FingerprintReport)

    @pytest.mark.asyncio
    async def test_audit_page_with_no_data(self):
        auditor = FingerprintAuditor()
        mock_page = MagicMock()
        mock_page.evaluate = AsyncMock(return_value={})
        report = await auditor.audit_page(mock_page)
        assert report.score >= 0

    @pytest.mark.asyncio
    async def test_audit_page_strict(self):
        auditor = FingerprintAuditor(strict=True)
        mock_page = MagicMock()
        mock_page.evaluate = AsyncMock(return_value={"webgl_vendor": "Google Inc."})
        report = await auditor.audit_page(mock_page)
        assert isinstance(report, FingerprintReport)

    def test_check_ua_platform_consistent(self):
        auditor = FingerprintAuditor()
        report = FingerprintReport()
        data = {"user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "platform": "Win32"}
        auditor._check_ua_platform(data, report)
        # Should not add issue for consistent UA/platform
        assert len(report.issues) == 0

    def test_check_ua_platform_inconsistent(self):
        auditor = FingerprintAuditor()
        report = FingerprintReport()
        data = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "platform": "Linux x86_64",
        }
        auditor._check_ua_platform(data, report)
        assert len(report.issues) > 0

    def test_check_ua_platform_no_data(self):
        auditor = FingerprintAuditor()
        report = FingerprintReport()
        auditor._check_ua_platform({}, report)
        assert len(report.issues) == 0

    def test_check_screen_viewport_consistent(self):
        auditor = FingerprintAuditor()
        report = FingerprintReport()
        data = {
            "screen": {"width": 1920, "height": 1080},
            "viewport": {"width": 1920, "height": 1080},
        }
        auditor._check_screen_viewport(data, report)
        # Viewport <= screen is OK
        assert len(report.issues) == 0

    def test_check_screen_viewport_inconsistent(self):
        auditor = FingerprintAuditor()
        report = FingerprintReport()
        data = {
            "screen": {"width": 1920, "height": 1080},
            "viewport": {"width": 3000, "height": 2000},
        }
        auditor._check_screen_viewport(data, report)
        assert len(report.issues) > 0

    def test_check_timezone_locale_consistent(self):
        auditor = FingerprintAuditor()
        report = FingerprintReport()
        data = {"timezone": "Europe/Moscow", "locale": "ru-RU"}
        auditor._check_timezone_locale(data, report)
        assert len(report.issues) == 0

    def test_check_timezone_locale_inconsistent(self):
        auditor = FingerprintAuditor()
        report = FingerprintReport()
        data = {"timezone": "America/New_York", "locale": "zh-CN"}
        auditor._check_timezone_locale(data, report)
        assert len(report.issues) > 0

    def test_check_touch_consistency(self):
        auditor = FingerprintAuditor()
        report = FingerprintReport()
        data = {"max_touch_points": 0, "platform": "Win32"}
        auditor._check_touch_consistency(data, report)
        assert len(report.issues) == 0

    def test_check_memory_cores(self):
        auditor = FingerprintAuditor()
        report = FingerprintReport()
        data = {"hardware_concurrency": 8, "device_memory": 8}
        auditor._check_memory_cores(data, report)
        assert isinstance(report, FingerprintReport)
