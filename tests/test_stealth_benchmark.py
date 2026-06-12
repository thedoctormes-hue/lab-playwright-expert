"""
Тесты для Stealth Benchmark модуля.

Покрывает:
  - TestResult — результат одного теста
  - BenchmarkResult — результат бенчмарка
  - StealthBenchmark — инициализация и настройки
"""
import pytest

from lab_playwright_kit.stealth_benchmark import (
    BenchmarkResult,
    StealthBenchmark,
    TestResult,
)


# ─── TestResult ───────────────────────────────────────────────────────────────

class TestTestResult:
    def test_create_passed(self):
        result = TestResult(name="webdriver", passed=True)
        assert result.name == "webdriver"
        assert result.passed is True
        assert result.value == ""
        assert result.expected == ""

    def test_create_failed(self):
        result = TestResult(name="canvas", passed=False, value="detected", expected="clean")
        assert result.name == "canvas"
        assert result.passed is False
        assert result.value == "detected"
        assert result.expected == "clean"

    def test_create_with_all_fields(self):
        result = TestResult(
            name="webgl",
            passed=True,
            value="ok",
            expected="ok",
        )
        assert result.name == "webgl"
        assert result.passed is True
        assert result.value == "ok"
        assert result.expected == "ok"


# ─── BenchmarkResult ─────────────────────────────────────────────────────────

class TestBenchmarkResult:
    def test_default_result(self):
        result = BenchmarkResult()
        assert result.score == 0
        assert result.passed == 0
        assert result.failed == 0
        assert result.total == 0
        assert result.details == []
        assert result.duration_ms == 0.0
        assert result.url == ""
        assert result.error is None

    def test_summary_no_error(self):
        result = BenchmarkResult(score=80, passed=8, failed=2, total=10, duration_ms=5000)
        summary = result.summary
        assert "80/100" in summary
        assert "8/10" in summary
        assert "2 failed" in summary

    def test_summary_with_error(self):
        result = BenchmarkResult(error="Connection failed")
        summary = result.summary
        assert "FAILED" in summary
        assert "Connection failed" in summary

    def test_passed_names(self):
        result = BenchmarkResult(details=[
            TestResult(name="webdriver", passed=True),
            TestResult(name="canvas", passed=False),
            TestResult(name="webgl", passed=True),
        ])
        assert result.passed_names == ["webdriver", "webgl"]

    def test_failed_names(self):
        result = BenchmarkResult(details=[
            TestResult(name="webdriver", passed=True),
            TestResult(name="canvas", passed=False),
            TestResult(name="webgl", passed=False),
        ])
        assert result.failed_names == ["canvas", "webgl"]

    def test_empty_passed_names(self):
        result = BenchmarkResult()
        assert result.passed_names == []

    def test_empty_failed_names(self):
        result = BenchmarkResult()
        assert result.failed_names == []

    def test_score_calculation(self):
        result = BenchmarkResult(score=75, passed=3, failed=1, total=4)
        assert result.score == 75


# ─── StealthBenchmark ────────────────────────────────────────────────────────

class TestStealthBenchmark:
    def test_default_init(self):
        bench = StealthBenchmark()
        assert bench._url == "https://bot.sannysoft.com"
        assert bench._timeout_ms == 30000
        assert bench._wait_after_load_ms == 5000

    def test_custom_url(self):
        bench = StealthBenchmark(url="https://custom.test.com")
        assert bench._url == "https://custom.test.com"

    def test_custom_timeout(self):
        bench = StealthBenchmark(timeout_ms=60000)
        assert bench._timeout_ms == 60000

    def test_custom_wait(self):
        bench = StealthBenchmark(wait_after_load_ms=10000)
        assert bench._wait_after_load_ms == 10000

    def test_default_url_constant(self):
        assert StealthBenchmark.DEFAULT_URL == "https://bot.sannysoft.com"


# ─── StealthBenchmark._is_passed() ──────────────────────────────────────────

class TestStealthBenchmarkIsPassed:
    def test_pass_text(self):
        assert StealthBenchmark._is_passed("", "ok") is True
        assert StealthBenchmark._is_passed("", "pass") is True
        assert StealthBenchmark._is_passed("", "true") is True
        assert StealthBenchmark._is_passed("", "success") is True

    def test_fail_text(self):
        assert StealthBenchmark._is_passed("", "fail") is False
        assert StealthBenchmark._is_passed("", "false") is False
        assert StealthBenchmark._is_passed("", "error") is False
        assert StealthBenchmark._is_passed("", "blocked") is False

    def test_green_html(self):
        assert StealthBenchmark._is_passed("color: green", "") is True
        assert StealthBenchmark._is_passed("#0f0", "") is True
        assert StealthBenchmark._is_passed("#00ff00", "") is True

    def test_red_html(self):
        assert StealthBenchmark._is_passed("color: red", "") is False
        assert StealthBenchmark._is_passed("#f00", "") is False
        assert StealthBenchmark._is_passed("#ff0000", "") is False

    def test_check_emoji(self):
        assert StealthBenchmark._is_passed("", "✅") is True
        assert StealthBenchmark._is_passed("", "☑") is True

    def test_cross_emoji(self):
        assert StealthBenchmark._is_passed("", "❌") is False
        assert StealthBenchmark._is_passed("", "☒") is False

    def test_unknown_defaults_to_passed(self):
        assert StealthBenchmark._is_passed("", "some unknown value") is True
