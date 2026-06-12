"""
Тесты для StealthAudit и StealthAuditReport — единый аудит скрытности.

Покрывает:
  - StealthAuditReport: score, risk_level, benchmark_score, pipeline_level
  - StealthAuditReport: weak_points, recommendations, summary, to_dict
  - StealthAudit: run_score, run_benchmark, run_pipeline (изолированные)
  - StealthAudit: run_full (все три модуля)
  - StealthAudit._calc_overall_score: взвешенный расчёт
  - Обработка ошибок: score/benchmark/pipeline fail → warning, не crash
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lab_playwright_kit.stealth_audit import StealthAudit, StealthAuditReport
from lab_playwright_kit.stealth_benchmark import BenchmarkResult, TestResult, StealthBenchmark
from lab_playwright_kit.stealth_pipeline import PipelineResult, StealthPipeline
from lab_playwright_kit.stealth_score import (
    RiskLevel,
    StealthCheck,
    StealthScoreResult,
    StealthScorer,
)


# ─── StealthAuditReport ──────────────────────────────────────────────────────

class TestStealthAuditReportEmpty:
    """Отчёт без результатов — все дефолты."""

    def test_default_score(self):
        report = StealthAuditReport()
        assert report.score == 0.0

    def test_default_risk_level(self):
        report = StealthAuditReport()
        assert report.risk_level == "unknown"

    def test_default_benchmark_score(self):
        report = StealthAuditReport()
        assert report.benchmark_score == 0

    def test_default_pipeline_level(self):
        report = StealthAuditReport()
        assert report.pipeline_level == "none"

    def test_default_weak_points(self):
        report = StealthAuditReport()
        assert report.weak_points == []

    def test_default_recommendations(self):
        report = StealthAuditReport()
        assert report.recommendations == []

    def test_summary_empty(self):
        report = StealthAuditReport()
        assert "StealthAudit" in report.summary

    def test_to_dict_empty(self):
        report = StealthAuditReport()
        d = report.to_dict()
        assert d["overall_score"] == 0.0
        assert d["score"]["value"] == 0.0
        assert d["benchmark"]["score"] == 0
        assert d["pipeline"]["level"] == "none"
        assert d["weak_points"] == []
        assert d["recommendations"] == []


class TestStealthAuditReportWithScore:
    """Отчёт с score_result."""

    @pytest.fixture
    def score_result(self):
        checks = [
            StealthCheck("webdriver", True, 1.0, 0.2, RiskLevel.LOW, "ok"),
            StealthCheck("plugins", True, 1.0, 0.2, RiskLevel.LOW, "ok"),
            StealthCheck("chrome", False, 0.0, 0.2, RiskLevel.HIGH, "missing", "fix chrome"),
        ]
        return StealthScoreResult(
            score=0.85,
            risk_level=RiskLevel.LOW,
            checks=checks,
            recommendations=["fix chrome"],
        )

    @pytest.fixture
    def report(self, score_result):
        return StealthAuditReport(score_result=score_result)

    def test_score(self, report):
        assert report.score == 0.85

    def test_risk_level(self, report):
        assert report.risk_level == "low"

    def test_weak_points(self, report):
        weak = report.weak_points
        assert len(weak) == 1
        assert "score:chrome" in weak[0]
        assert "high" in weak[0]

    def test_recommendations(self, report):
        assert report.recommendations == ["fix chrome"]

    def test_summary(self, report):
        s = report.summary
        assert "score=0.85" in s
        assert "low" in s

    def test_to_dict(self, report):
        d = report.to_dict()
        assert d["score"]["value"] == 0.85
        assert d["score"]["risk_level"] == "low"
        assert len(d["score"]["checks"]) == 3


class TestStealthAuditReportWithBenchmark:
    """Отчёт с benchmark_result."""

    @pytest.fixture
    def benchmark_result(self):
        details = [
            TestResult("webrtc", False, "leak"),
            TestResult("audio", False, "fail"),
            TestResult("canvas", True, "ok"),
        ]
        return BenchmarkResult(
            score=78,
            passed=7,
            failed=2,
            total=9,
            details=details,
        )

    @pytest.fixture
    def report(self, benchmark_result):
        return StealthAuditReport(benchmark_result=benchmark_result)

    def test_benchmark_score(self, report):
        assert report.benchmark_score == 78

    def test_weak_points(self, report):
        weak = report.weak_points
        assert "benchmark:webrtc" in weak
        assert "benchmark:audio" in weak

    def test_recommendations(self, report):
        recs = report.recommendations
        assert len(recs) == 1
        assert "webrtc" in recs[0]
        assert "audio" in recs[0]

    def test_summary(self, report):
        s = report.summary
        assert "benchmark=78/100" in s


class TestStealthAuditReportWithPipeline:
    """Отчёт с pipeline_result."""

    @pytest.fixture
    def pipeline_result(self):
        return PipelineResult(
            level="advanced",
            stealth_scripts=18,
            audio_applied=True,
            webrtc_applied=True,
            client_hints_applied=True,
        )

    @pytest.fixture
    def report(self, pipeline_result):
        return StealthAuditReport(pipeline_result=pipeline_result)

    def test_pipeline_level(self, report):
        assert report.pipeline_level == "advanced"

    def test_summary(self, report):
        s = report.summary
        assert "pipeline=advanced" in s

    def test_to_dict(self, report):
        d = report.to_dict()
        assert d["pipeline"]["level"] == "advanced"
        assert d["pipeline"]["scripts"] == 18
        assert d["pipeline"]["audio"] is True
        assert d["pipeline"]["webrtc"] is True
        assert d["pipeline"]["client_hints"] is True


class TestStealthAuditReportFull:
    """Полный отчёт со всеми тремя результатами."""

    @pytest.fixture
    def full_report(self):
        checks = [
            StealthCheck("webdriver", True, 1.0, 0.2, RiskLevel.LOW, "ok"),
            StealthCheck("chrome", False, 0.0, 0.2, RiskLevel.HIGH, "missing", "fix chrome"),
        ]
        score = StealthScoreResult(
            score=0.7,
            risk_level=RiskLevel.MEDIUM,
            checks=checks,
            recommendations=["fix chrome"],
        )
        benchmark_details = [
            TestResult("webrtc", False, "leak"),
            TestResult("canvas", True, "ok"),
        ]
        benchmark = BenchmarkResult(
            score=80,
            passed=8,
            failed=1,
            total=9,
            details=benchmark_details,
        )
        pipeline = PipelineResult(
            level="standard",
            stealth_scripts=12,
            audio_applied=True,
            webrtc_applied=False,
            client_hints_applied=True,
        )
        return StealthAuditReport(
            score_result=score,
            benchmark_result=benchmark,
            pipeline_result=pipeline,
            overall_score=74.0,
            duration_ms=3500.0,
        )

    def test_weak_points_all(self, full_report):
        weak = full_report.weak_points
        assert len(weak) == 2  # score:chrome + benchmark:webrtc
        assert any("score:chrome" in w for w in weak)
        assert any("benchmark:webrtc" in w for w in weak)

    def test_recommendations_merged(self, full_report):
        recs = full_report.recommendations
        assert "fix chrome" in recs
        assert any("webrtc" in r for r in recs)

    def test_summary_all(self, full_report):
        s = full_report.summary
        assert "score=0.70" in s or "score=0.7" in s
        assert "benchmark=80/100" in s
        assert "pipeline=standard" in s
        assert "overall=74/100" in s

    def test_to_dict_structure(self, full_report):
        d = full_report.to_dict()
        assert d["overall_score"] == 74.0
        assert d["duration_ms"] == 3500.0
        assert "timestamp" in d


class TestCalcOverallScore:
    """Статический метод _calc_overall_score."""

    def test_no_results(self):
        report = StealthAuditReport()
        assert StealthAudit._calc_overall_score(report) == 0.0

    def test_score_only(self):
        checks = [StealthCheck("wd", True, 1.0, 0.2, RiskLevel.LOW, "ok")]
        score = StealthScoreResult(score=0.8, risk_level=RiskLevel.LOW, checks=checks)
        report = StealthAuditReport(score_result=score)
        assert StealthAudit._calc_overall_score(report) == 80.0  # 0.8 * 100

    def test_benchmark_only(self):
        benchmark = BenchmarkResult(score=75, passed=7, failed=2, total=9)
        report = StealthAuditReport(benchmark_result=benchmark)
        assert StealthAudit._calc_overall_score(report) == 75.0

    def test_weighted_score_and_benchmark(self):
        """score 40% + benchmark 60%."""
        checks = [StealthCheck("wd", True, 1.0, 0.2, RiskLevel.LOW, "ok")]
        score = StealthScoreResult(score=0.8, risk_level=RiskLevel.LOW, checks=checks)
        # 80 * 0.4 = 32
        benchmark = BenchmarkResult(score=60, passed=5, failed=4, total=9)
        # 60 * 0.6 = 36 → total = 68
        report = StealthAuditReport(score_result=score, benchmark_result=benchmark)
        result = StealthAudit._calc_overall_score(report)
        assert result == pytest.approx(68.0)


# ─── StealthAudit ────────────────────────────────────────────────────────────

class TestStealthAuditInit:
    def test_default_init(self):
        audit = StealthAudit()
        assert audit._level == "advanced"
        assert audit._scorer is not None
        assert audit._pipeline is not None
        assert audit._benchmark is not None

    def test_custom_init(self):
        audit = StealthAudit(level="minimal", benchmark_url="http://localhost")
        assert audit._level == "minimal"


class TestStealthAuditRunScore:
    @pytest.mark.asyncio
    async def test_run_score_success(self):
        audit = StealthAudit()
        mock_page = MagicMock()

        mock_score = StealthScoreResult(
            score=0.9,
            risk_level=RiskLevel.LOW,
            checks=[],
        )

        with patch.object(audit._scorer, "score", new_callable=AsyncMock, return_value=mock_score):
            report = await audit.run_score(mock_page)

        assert report.score_result is not None
        assert report.score == 0.9
        assert report.overall_score == 90.0
        assert report.duration_ms > 0

    @pytest.mark.asyncio
    async def test_run_score_exception_returns_empty(self):
        """score() бросает → warning, не crash."""
        audit = StealthAudit()
        mock_page = MagicMock()

        with patch.object(audit._scorer, "score", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
            report = await audit.run_score(mock_page)

        assert report.score_result is None
        assert report.score == 0.0


class TestStealthAuditRunBenchmark:
    @pytest.mark.asyncio
    async def test_run_benchmark_success(self):
        audit = StealthAudit()

        mock_benchmark = BenchmarkResult(
            score=82, passed=8, failed=1, total=9,
            details=[TestResult("audio", False, "fail")],
        )

        with patch.object(audit._benchmark, "run", new_callable=AsyncMock, return_value=mock_benchmark):
            report = await audit.run_benchmark()

        assert report.benchmark_result is not None
        assert report.benchmark_score == 82
        assert report.overall_score == 82.0

    @pytest.mark.asyncio
    async def test_run_benchmark_exception_propagates(self):
        """benchmark.run() бросает → exception пробрасывается (нет try/except в run_benchmark)."""
        audit = StealthAudit()

        with patch.object(audit._benchmark, "run", new_callable=AsyncMock, side_effect=RuntimeError("net error")):
            with pytest.raises(RuntimeError, match="net error"):
                await audit.run_benchmark()


class TestStealthAuditRunPipeline:
    @pytest.mark.asyncio
    async def test_run_pipeline_success(self):
        audit = StealthAudit()
        mock_page = MagicMock()

        mock_pipeline = PipelineResult(
            level="advanced",
            stealth_scripts=18,
            audio_applied=True,
            webrtc_applied=True,
            client_hints_applied=True,
        )

        with patch.object(audit._pipeline, "apply", new_callable=AsyncMock, return_value=mock_pipeline):
            report = await audit.run_pipeline(mock_page)

        assert report.pipeline_result is not None
        assert report.pipeline_level == "advanced"


class TestStealthAuditRunFull:
    @pytest.mark.asyncio
    async def test_run_full_all_success(self):
        """Полный аудит: все три модуля успешно."""
        audit = StealthAudit()
        mock_page = MagicMock()

        mock_score = StealthScoreResult(
            score=0.85, risk_level=RiskLevel.LOW, checks=[],
        )
        mock_pipeline = PipelineResult(
            level="advanced", stealth_scripts=18,
            audio_applied=True, webrtc_applied=True, client_hints_applied=True,
        )
        mock_benchmark = BenchmarkResult(
            score=78, passed=7, failed=2, total=9,
            details=[
                TestResult("webrtc", False, "leak"),
                TestResult("audio", False, "fail"),
            ],
        )

        with patch.object(audit._scorer, "score", new_callable=AsyncMock, return_value=mock_score), \
             patch.object(audit._pipeline, "apply", new_callable=AsyncMock, return_value=mock_pipeline), \
             patch.object(audit._benchmark, "run", new_callable=AsyncMock, return_value=mock_benchmark):
            report = await audit.run_full(mock_page)

        assert report.score_result is not None
        assert report.pipeline_result is not None
        assert report.benchmark_result is not None
        assert report.duration_ms > 0
        assert report.overall_score > 0

    @pytest.mark.asyncio
    async def test_run_full_score_fails_others_ok(self):
        """score падает, pipeline + benchmark работают."""
        audit = StealthAudit()
        mock_page = MagicMock()

        mock_pipeline = PipelineResult(
            level="standard", stealth_scripts=12,
            audio_applied=True, webrtc_applied=False, client_hints_applied=True,
        )
        mock_benchmark = BenchmarkResult(
            score=70, passed=7, failed=2, total=9,
            details=[TestResult("webrtc", False, "leak")],
        )

        with patch.object(audit._scorer, "score", new_callable=AsyncMock, side_effect=RuntimeError("score fail")), \
             patch.object(audit._pipeline, "apply", new_callable=AsyncMock, return_value=mock_pipeline), \
             patch.object(audit._benchmark, "run", new_callable=AsyncMock, return_value=mock_benchmark):
            report = await audit.run_full(mock_page)

        assert report.score_result is None
        assert report.pipeline_result is not None
        assert report.benchmark_result is not None

    @pytest.mark.asyncio
    async def test_run_full_pipeline_fails_others_ok(self):
        """pipeline падает, score + benchmark работают."""
        audit = StealthAudit()
        mock_page = MagicMock()

        mock_score = StealthScoreResult(
            score=0.75, risk_level=RiskLevel.LOW, checks=[],
        )
        mock_benchmark = BenchmarkResult(
            score=65, passed=6, failed=3, total=9,
            details=[TestResult("audio", False, "fail")],
        )

        with patch.object(audit._scorer, "score", new_callable=AsyncMock, return_value=mock_score), \
             patch.object(audit._pipeline, "apply", new_callable=AsyncMock, side_effect=RuntimeError("pipeline fail")), \
             patch.object(audit._benchmark, "run", new_callable=AsyncMock, return_value=mock_benchmark):
            report = await audit.run_full(mock_page)

        assert report.score_result is not None
        assert report.pipeline_result is None
        assert report.benchmark_result is not None
