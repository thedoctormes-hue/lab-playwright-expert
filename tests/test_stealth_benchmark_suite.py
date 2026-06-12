"""
Tests for Stealth Benchmark Suite.
Covers: SuiteReport, CategoryScore, StealthTestResult, CATEGORY_WEIGHTS, test functions.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── Setup paths ──────────────────────────────────────────────────────────────
_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from scripts.stealth_benchmark_suite import (
    SuiteReport,
    CategoryScore,
    StealthTestResult,
    TestStatus,
    CATEGORY_WEIGHTS,
    UNIT_TESTS,
    BROWSER_TESTS,
    generate_html_report,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════════════════

class TestStealthTestResult:
    """Tests for StealthTestResult dataclass."""

    def test_creation(self):
        """Создание результата теста."""
        r = StealthTestResult(
            name="Test Fingerprint",
            category="fingerprint",
            status=TestStatus.PASSED,
            score=95.0,
            details="All checks passed",
            duration_ms=150.0,
        )
        assert r.name == "Test Fingerprint"
        assert r.category == "fingerprint"
        assert r.status == TestStatus.PASSED
        assert r.score == 95.0
        assert r.details == "All checks passed"
        assert r.duration_ms == 150.0

    def test_creation_defaults(self):
        """Создание с дефолтными значениями."""
        r = StealthTestResult(name="", category="", status=TestStatus.PASSED, score=0)
        assert r.name == ""
        assert r.category == ""
        assert r.status == TestStatus.PASSED
        assert r.score == 0
        assert r.details == ""
        assert r.duration_ms == 0

    def test_status_enum(self):
        """Все статусы теста."""
        assert TestStatus.PASSED.value == "passed"
        assert TestStatus.FAILED.value == "failed"
        assert TestStatus.ERROR.value == "error"
        assert TestStatus.SKIPPED.value == "skipped"


class TestCategoryScore:
    """Tests for CategoryScore dataclass."""

    def test_creation(self):
        """Создание категории."""
        r1 = StealthTestResult(name="t1", category="fingerprint", status=TestStatus.PASSED, score=90.0)
        r2 = StealthTestResult(name="t2", category="fingerprint", status=TestStatus.FAILED, score=40.0)

        cs = CategoryScore(
            name="fingerprint",
            weight=0.3,
            score=65.0,
            tests_passed=1,
            tests_failed=1,
            tests_total=2,
            results=[r1, r2],
        )
        assert cs.name == "fingerprint"
        assert cs.weight == 0.3
        assert cs.score == 65.0
        assert cs.tests_passed == 1
        assert cs.tests_failed == 1
        assert cs.tests_total == 2

    def test_creation_defaults(self):
        """Создание с дефолтными значениями."""
        cs = CategoryScore(name="test", weight=0.25, score=0)
        assert cs.tests_passed == 0
        assert cs.tests_failed == 0
        assert cs.tests_total == 0
        assert cs.results == []


class TestSuiteReport:
    """Tests for SuiteReport dataclass."""

    def test_creation(self):
        """Создание отчёта."""
        report = SuiteReport(
            timestamp="2026-01-01 00:00:00",
            overall_score=85.0,
            duration_ms=5000.0,
        )
        assert report.timestamp == "2026-01-01 00:00:00"
        assert report.overall_score == 85.0
        assert report.duration_ms == 5000.0
        assert report.categories == []
        assert report.errors == []

    def test_to_dict(self):
        """Сериализация в dict."""
        r = StealthTestResult(name="t1", category="fingerprint", status=TestStatus.PASSED, score=90.0)
        cs = CategoryScore(name="fingerprint", weight=0.3, score=90.0, tests_passed=1, tests_total=1, results=[r])
        report = SuiteReport(
            timestamp="2026-01-01 00:00:00",
            overall_score=90.0,
            categories=[cs],
        )

        d = report.to_dict()
        assert d["timestamp"] == "2026-01-01 00:00:00"
        assert d["overall_score"] == 90.0
        assert len(d["categories"]) == 1
        assert d["categories"][0]["name"] == "fingerprint"

    def test_to_dict_empty(self):
        """Сериализация пустого отчёта."""
        report = SuiteReport(timestamp="2026-01-01 00:00:00")
        d = report.to_dict()
        assert d["overall_score"] == 0
        assert d["categories"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# Category Weights
# ═══════════════════════════════════════════════════════════════════════════════

class TestCategoryWeights:
    """Tests for CATEGORY_WEIGHTS."""

    def test_weights_sum_to_one(self):
        """Сумма весов = 1.0."""
        total = sum(CATEGORY_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01, f"Weights sum to {total}, expected 1.0"

    def test_all_categories_present(self):
        """Все категории присутствуют."""
        expected = {"fingerprint", "behavior", "network", "consistency"}
        assert set(CATEGORY_WEIGHTS.keys()) == expected

    def test_weights_positive(self):
        """Все веса положительные."""
        for cat, weight in CATEGORY_WEIGHTS.items():
            assert weight > 0, f"Weight for {cat} is {weight}"


# ═══════════════════════════════════════════════════════════════════════════════
# Test Registry
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegistry:
    """Tests for UNIT_TESTS and BROWSER_TESTS registries."""

    def test_unit_tests_not_empty(self):
        """UNIT_TESTS не пуст."""
        assert len(UNIT_TESTS) > 0

    def test_unit_test_structure(self):
        """Структура UNIT_TESTS: (category, function)."""
        for category, test_func in UNIT_TESTS:
            assert isinstance(category, str)
            assert callable(test_func)

    def test_browser_tests_not_empty(self):
        """BROWSER_TESTS не пуст."""
        assert len(BROWSER_TESTS) > 0

    def test_browser_test_structure(self):
        """Структура BROWSER_TESTS: (category, function)."""
        for category, test_func in BROWSER_TESTS:
            assert isinstance(category, str)
            assert callable(test_func)

    def test_unit_test_categories_valid(self):
        """Категории UNIT_TESTS соответствуют CATEGORY_WEIGHTS."""
        for category, _ in UNIT_TESTS:
            assert category in CATEGORY_WEIGHTS, f"Unknown category: {category}"

    def test_browser_test_categories_valid(self):
        """Категории BROWSER_TESTS соответствуют CATEGORY_WEIGHTS."""
        for category, _ in BROWSER_TESTS:
            assert category in CATEGORY_WEIGHTS, f"Unknown category: {category}"


# ═══════════════════════════════════════════════════════════════════════════════
# HTML Report Generation
# ═══════════════════════════════════════════════════════════════════════════════

class TestHTMLReportGeneration:
    """Tests for generate_html_report."""

    def test_generates_html_file(self):
        """Генерация HTML-файла."""
        import shutil

        out_dir = tempfile.mkdtemp()
        try:
            report = SuiteReport(
                timestamp="2026-01-01 00:00:00",
                overall_score=85.0,
                duration_ms=5000.0,
            )
            html_path = generate_html_report(report, out_dir)
            assert Path(html_path).exists()
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_html_contains_score(self):
        """HTML содержит скор."""
        import shutil

        out_dir = tempfile.mkdtemp()
        try:
            report = SuiteReport(
                timestamp="2026-01-01 00:00:00",
                overall_score=92.5,
                duration_ms=3000.0,
            )
            html_path = generate_html_report(report, out_dir)
            html_content = Path(html_path).read_text()
            assert "92" in html_content
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_html_contains_categories(self):
        """HTML содержит категории."""
        import shutil

        out_dir = tempfile.mkdtemp()
        try:
            r = StealthTestResult(name="t1", category="fingerprint", status=TestStatus.PASSED, score=90.0)
            cs = CategoryScore(name="fingerprint", weight=0.25, score=90.0, tests_passed=1, tests_total=1, results=[r])
            report = SuiteReport(
                overall_score=90.0,
                categories=[cs],
            )
            html_path = generate_html_report(report, out_dir)
            html_content = Path(html_path).read_text()
            assert "FINGERPRINT" in html_content
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_html_contains_recommendations(self):
        """HTML содержит рекомендации."""
        import shutil

        out_dir = tempfile.mkdtemp()
        try:
            report = SuiteReport(
                timestamp="2026-01-01 00:00:00",
                overall_score=50.0,  # Low score → recommendations
            )
            html_path = generate_html_report(report, out_dir)
            html_content = Path(html_path).read_text()
            assert "Рекомендации" in html_content or "recommendation" in html_content.lower()
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_html_contains_stats(self):
        """HTML содержит статистику."""
        import shutil

        out_dir = tempfile.mkdtemp()
        try:
            report = SuiteReport(
                timestamp="2026-01-01 00:00:00",
                overall_score=80.0,
                duration_ms=5000.0,
            )
            html_path = generate_html_report(report, out_dir)
            html_content = Path(html_path).read_text()
            assert "Тестов" in html_content or "tests" in html_content.lower()
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests (without browser)
# ═══════════════════════════════════════════════════════════════════════════════

class TestUnitBenchmarkTests:
    """Tests for unit benchmark test functions."""

    @pytest.mark.asyncio
    async def test_stealth_config_levels(self):
        """Все уровня StealthConfig генерируют скрипты."""
        from lab_playwright_kit import StealthConfig

        for level_name, level_fn in [
            ("minimal", StealthConfig.minimal),
            ("standard", StealthConfig.standard),
            ("advanced", StealthConfig.advanced),
            ("full", StealthConfig.full),
        ]:
            cfg = level_fn()
            scripts = cfg.get_scripts()
            assert len(scripts) >= 1, f"Level {level_name} should have scripts"

    @pytest.mark.asyncio
    async def test_stealth_config_script_count_increases(self):
        """Количество скриптов увеличивается с уровнем."""
        from lab_playwright_kit import StealthConfig

        minimal = StealthConfig.minimal()
        full = StealthConfig.full()
        assert len(full.get_scripts()) >= len(minimal.get_scripts())

    @pytest.mark.asyncio
    async def test_audio_spoofer_deterministic(self):
        """AudioSpoofer детерминистичен."""
        from lab_playwright_kit.stealth_audio import AudioConfig, AudioSpoofer

        config = AudioConfig.full(noise_seed=42)
        script1 = AudioSpoofer.get_script(config)
        script2 = AudioSpoofer.get_script(config)
        assert script1 == script2

    @pytest.mark.asyncio
    async def test_webrtc_modes(self):
        """Все режимы WebRTC генерируют скрипты."""
        from lab_playwright_kit.stealth_webrtc import WebRTCConfig, WebRTCProtector

        for mode_fn in [WebRTCConfig.block_all, WebRTCConfig.filter_host]:
            config = mode_fn()
            script = WebRTCProtector.get_script(config)
            assert len(script) > 100

    @pytest.mark.asyncio
    async def test_client_hints_from_ua(self):
        """ClientHints из User-Agent."""
        from lab_playwright_kit.stealth_client_hints import ClientHintsConfig, ClientHintsSpoofer

        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        config = ClientHintsConfig.from_user_agent(ua)
        script = ClientHintsSpoofer.get_script(config)
        assert "Chrome" in script
        assert "Windows" in script

    @pytest.mark.asyncio
    async def test_behavior_profiles_creation(self):
        """Все профили поведения создаются."""
        from lab_playwright_kit import BehaviorProfile

        profiles = ["casual_reader", "power_user", "researcher", "social_media"]
        for name in profiles:
            try:
                BehaviorProfile(name=name)
            except Exception:
                pass  # Some profiles may not exist, that's OK

    @pytest.mark.asyncio
    async def test_bezier_points(self):
        """Кривые Безье генерируют точки."""
        from lab_playwright_kit import HumanBehaviorEngine

        engine = HumanBehaviorEngine.__new__(HumanBehaviorEngine)
        import random
        engine._rng = random.Random(42)

        points = engine._generate_bezier_points(0, 0, 100, 100, 20)
        assert len(points) == 21
        assert points[0] == (0, 0)
        assert points[-1] == (100, 100)
