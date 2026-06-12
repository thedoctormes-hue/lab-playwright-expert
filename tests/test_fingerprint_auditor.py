"""
Тесты для FingerprintAuditor — аудит согласованности браузерных отпечатков.
"""
import pytest

from lab_playwright_kit.fingerprint_auditor import (
    FingerprintAuditor,
    FingerprintIssue,
    FingerprintReport,
    Severity,
)


class TestSeverity:
    def test_values(self):
        assert Severity.INFO.value == "info"
        assert Severity.WARNING.value == "warning"
        assert Severity.CRITICAL.value == "critical"


class TestFingerprintIssue:
    def test_create_basic(self):
        issue = FingerprintIssue(check="ua_platform", severity=Severity.CRITICAL, message="test")
        assert issue.check == "ua_platform"
        assert issue.severity == Severity.CRITICAL
        assert issue.expected == ""
        assert issue.actual == ""

    def test_create_full(self):
        issue = FingerprintIssue(check="gpu", severity=Severity.WARNING, message="mismatch", expected="A", actual="B")
        assert issue.expected == "A"
        assert issue.actual == "B"


class TestFingerprintReport:
    def test_default(self):
        r = FingerprintReport()
        assert r.score == 1.0
        assert r.is_consistent is True
        assert r.critical_issues == []
        assert r.warnings == []

    def test_is_consistent_boundary(self):
        assert FingerprintReport(score=0.8).is_consistent is True
        assert FingerprintReport(score=0.79).is_consistent is False

    def test_critical_filter(self):
        r = FingerprintReport(issues=[
            FingerprintIssue("a", Severity.CRITICAL, "c"),
            FingerprintIssue("b", Severity.WARNING, "w"),
        ])
        assert len(r.critical_issues) == 1
        assert len(r.warnings) == 1


class TestFingerprintAuditor:
    def test_init(self):
        assert FingerprintAuditor().strict is False
        assert FingerprintAuditor(strict=True).strict is True

    def test_ua_windows_mismatch(self):
        a = FingerprintAuditor()
        r = FingerprintReport()
        a._check_ua_platform({"userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "platform": "MacIntel"}, r)
        assert any(i.check == "ua_platform" for i in r.critical_issues)

    def test_ua_windows_match(self):
        a = FingerprintAuditor()
        r = FingerprintReport()
        a._check_ua_platform({"userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "platform": "Win32"}, r)
        assert len([i for i in r.issues if i.check == "ua_platform"]) == 0

    def test_gpu_apple_on_non_apple(self):
        a = FingerprintAuditor()
        r = FingerprintReport()
        a._check_gpu_consistency({"userAgent": "Win", "webglVendor": "Apple Inc.", "webglRenderer": "Apple GPU"}, r)
        assert any(i.check == "gpu_platform" for i in r.critical_issues)

    def test_gpu_swiftshader(self):
        a = FingerprintAuditor()
        r = FingerprintReport()
        a._check_gpu_consistency({"userAgent": "Win", "webglVendor": "Google Inc.", "webglRenderer": "SwiftShader"}, r)
        assert any(i.check == "gpu_software" for i in r.warnings)

    def test_gpu_no_vendor(self):
        a = FingerprintAuditor()
        r = FingerprintReport()
        a._check_gpu_consistency({"userAgent": "Win", "webglVendor": ""}, r)
        assert len(r.issues) == 0

    def test_screen_small(self):
        a = FingerprintAuditor()
        r = FingerprintReport()
        a._check_screen_viewport({"screenWidth": 640, "screenHeight": 480, "pixelRatio": 1}, r)
        assert any(i.check == "screen_size" for i in r.warnings)

    def test_screen_normal(self):
        a = FingerprintAuditor()
        r = FingerprintReport()
        a._check_screen_viewport({"screenWidth": 1920, "screenHeight": 1080, "pixelRatio": 1}, r)
        assert len([i for i in r.issues if i.check in ("screen_size", "pixel_ratio")]) == 0

    def test_touch_mobile_no_touch(self):
        a = FingerprintAuditor()
        r = FingerprintReport()
        a._check_touch_consistency({"userAgent": "iPhone", "touchSupport": False, "maxTouchPoints": 0}, r)
        assert any(i.check == "touch_mobile" for i in r.critical_issues)

    def test_cores_zero(self):
        a = FingerprintAuditor()
        r = FingerprintReport()
        a._check_memory_cores({"hardwareConcurrency": 0, "deviceMemory": 8}, r)
        assert any(i.check == "cores_zero" for i in r.warnings)
