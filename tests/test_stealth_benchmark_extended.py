"""
Расширенные тесты для StealthBenchmark.

Покрывает:
  - BenchmarkTestResult dataclass
  - BenchmarkResult (summary, passed_names, failed_names)
  - StealthBenchmark.__init__
"""

from __future__ import annotations

from lab_playwright_kit.stealth import StealthConfig
from lab_playwright_kit.stealth_benchmark import (
    BenchmarkResult,
    BenchmarkTestResult,
    StealthBenchmark,
)


# ─── BenchmarkTestResult ───────────────────────────────────────────────────


class TestBenchmarkTestResult:
    def test_defaults(self):
        r = BenchmarkTestResult(name="webdriver", passed=True)
        assert r.name == "webdriver"
        assert r.passed is True
        assert r.value == ""
        assert r.expected == ""

    def test_all_fields(self):
        r = BenchmarkTestResult(
            name="plugins",
            passed=False,
            value="0",
            expected="3",
        )
        assert r.name == "plugins"
        assert r.passed is False
        assert r.value == "0"
        assert r.expected == "3"


# ─── BenchmarkResult ───────────────────────────────────────────────────────


class TestBenchmarkResult:
    def test_defaults(self):
        r = BenchmarkResult()
        assert r.score == 0
        assert r.passed == 0
        assert r.failed == 0
        assert r.total == 0
        assert r.details == []
        assert r.duration_ms == 0.0
        assert r.url == ""
        assert r.error is None

    def test_summary_ok(self):
        r = BenchmarkResult(score=78, passed=15, failed=3, total=18, duration_ms=5000)
        s = r.summary
        assert "78/100" in s
        assert "15/18" in s
        assert "3 failed" in s

    def test_summary_error(self):
        r = BenchmarkResult(error="Connection refused")
        s = r.summary
        assert "FAILED" in s
        assert "Connection refused" in s

    def test_passed_names(self):
        r = BenchmarkResult(
            details=[
                BenchmarkTestResult(name="webdriver", passed=True),
                BenchmarkTestResult(name="plugins", passed=False),
                BenchmarkTestResult(name="chrome", passed=True),
            ]
        )
        names = r.passed_names
        assert "webdriver" in names
        assert "chrome" in names
        assert "plugins" not in names

    def test_failed_names(self):
        r = BenchmarkResult(
            details=[
                BenchmarkTestResult(name="webdriver", passed=True),
                BenchmarkTestResult(name="plugins", passed=False),
                BenchmarkTestResult(name="webgl", passed=False),
            ]
        )
        names = r.failed_names
        assert "plugins" in names
        assert "webgl" in names
        assert "webdriver" not in names

    def test_all_passed(self):
        r = BenchmarkResult(score=100, passed=20, failed=0, total=20)
        assert r.passed == 20
        assert r.failed == 0
        assert len(r.failed_names) == 0

    def test_all_failed(self):
        r = BenchmarkResult(
            score=0,
            passed=0,
            failed=10,
            total=10,
            details=[BenchmarkTestResult(name=f"t{i}", passed=False) for i in range(10)],
        )
        assert len(r.failed_names) == 10
        assert len(r.passed_names) == 0


# ─── StealthBenchmark init ────────────────────────────────────────────────


class TestStealthBenchmarkInit:
    def test_default_init(self):
        bm = StealthBenchmark()
        assert bm._url == "https://bot.sannysoft.com"
        assert bm._timeout_ms == 30000
        assert bm._wait_after_load_ms == 5000

    def test_custom_init(self):
        config = StealthConfig.minimal()
        bm = StealthBenchmark(
            config=config,
            url="https://custom-test.com",
            timeout_ms=60000,
            wait_after_load_ms=10000,
        )
        assert bm._config is config
        assert bm._url == "https://custom-test.com"
        assert bm._timeout_ms == 60000
        assert bm._wait_after_load_ms == 10000

    def test_config_default_is_advanced(self):
        bm = StealthBenchmark()
        # Default config should have advanced level
        assert bm._config is not None


# ─── StealthBenchmark._is_passed ──────────────────────────────────────────


class TestIsPassed:
    def test_green_text(self):
        assert StealthBenchmark._is_passed("<td>green</td>", "ok") is True

    def test_red_text(self):
        assert StealthBenchmark._is_passed("<td>red</td>", "fail") is False

    def test_pass_text(self):
        assert StealthBenchmark._is_passed("", "pass") is True

    def test_fail_text(self):
        assert StealthBenchmark._is_passed("", "fail") is False

    def test_true_text(self):
        assert StealthBenchmark._is_passed("", "true") is True

    def test_false_text(self):
        assert StealthBenchmark._is_passed("", "false") is False

    def test_checkmark_emoji(self):
        assert StealthBenchmark._is_passed("", "✅") is True

    def test_cross_emoji(self):
        assert StealthBenchmark._is_passed("", "❌") is False

    def test_box_checkmark(self):
        assert StealthBenchmark._is_passed("", "☑") is True

    def test_box_cross(self):
        assert StealthBenchmark._is_passed("", "☒") is False

    def test_green_hex(self):
        assert StealthBenchmark._is_passed("color: #0f0", "ok") is True

    def test_red_hex(self):
        assert StealthBenchmark._is_passed("color: #f00", "fail") is False

    def test_green_full_hex(self):
        assert StealthBenchmark._is_passed("color: #00ff00", "ok") is True

    def test_red_full_hex(self):
        assert StealthBenchmark._is_passed("color: #ff0000", "fail") is False

    def test_blocked_text(self):
        assert StealthBenchmark._is_passed("", "blocked") is False

    def test_error_text(self):
        assert StealthBenchmark._is_passed("", "error") is False

    def test_success_text(self):
        assert StealthBenchmark._is_passed("", "success") is True

    def test_unknown_defaults_true(self):
        assert StealthBenchmark._is_passed("", "some value") is True
