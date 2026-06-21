"""
Расширенные тесты для StealthAudit.

Покрывает:
  - StealthAuditReport (properties: score, risk_level, benchmark_score, pipeline_level, weak_points, recommendations, summary, to_dict)
  - StealthAudit.__init__
  - StealthAudit.run_score_only
  - StealthAudit.run_full (mocked sub-modules)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lab_playwright_kit.stealth_audit import (
    StealthAudit,
    StealthAuditReport,
)
from lab_playwright_kit.stealth_benchmark import (
    BenchmarkResult,
    BenchmarkTestResult,
    StealthBenchmark,
)
from lab_playwright_kit.stealth_pipeline import PipelineResult, StealthPipeline
from lab_playwright_kit.stealth_score import (
    RiskLevel,
    StealthCheck,
    StealthScorer,
    StealthScoreResult,
)


# ─── StealthAuditReport ─────────────────────────────────────────────────────


class TestStealthAuditReport:
    def test_defaults(self):
        r = StealthAuditReport()
        assert r.score_result is None
        assert r.benchmark_result is None
        assert r.pipeline_result is None
        assert r.overall_score == 0.0
        assert r.duration_ms == 0.0
        assert r.timestamp > 0

    def test_score_none(self):
        r = StealthAuditReport()
        assert r.score == 0.0

    def test_score_with_result(self):
        sr = StealthScoreResult(score=0.85)
        r = StealthAuditReport(score_result=sr)
        assert r.score == 0.85

    def test_risk_level_none(self):
        r = StealthAuditReport()
        assert r.risk_level == "unknown"

    def test_risk_level_with_result(self):
        sr = StealthScoreResult(score=0.85, risk_level=RiskLevel.LOW)
        r = StealthAuditReport(score_result=sr)
        assert r.risk_level == "low"

    def test_benchmark_score_none(self):
        r = StealthAuditReport()
        assert r.benchmark_score == 0

    def test_benchmark_score_with_result(self):
        br = BenchmarkResult(score=78)
        r = StealthAuditReport(benchmark_result=br)
        assert r.benchmark_score == 78

    def test_pipeline_level_none(self):
        r = StealthAuditReport()
        assert r.pipeline_level == "none"

    def test_pipeline_level_with_result(self):
        pr = PipelineResult(level="advanced")
        r = StealthAuditReport(pipeline_result=pr)
        assert r.pipeline_level == "advanced"

    def test_weak_points_empty(self):
        r = StealthAuditReport()
        assert r.weak_points == []

    def test_weak_points_from_score(self):
        sr = StealthScoreResult(
            score=0.5,
            checks=[
                StealthCheck(
                    name="webdriver", passed=True, score=1.0, weight=0.2, risk=RiskLevel.LOW
                ),
                StealthCheck(
                    name="plugins", passed=False, score=0.0, weight=0.15, risk=RiskLevel.HIGH
                ),
            ],
        )
        r = StealthAuditReport(score_result=sr)
        weak = r.weak_points
        assert len(weak) == 1
        assert "plugins" in weak[0]

    def test_weak_points_from_benchmark(self):
        br = BenchmarkResult(
            score=50,
            failed=2,
            details=[
                BenchmarkTestResult(name="webdriver", passed=False),
                BenchmarkTestResult(name="plugins", passed=False),
            ],
        )
        r = StealthAuditReport(benchmark_result=br)
        weak = r.weak_points
        assert len(weak) == 2
        assert any("webdriver" in w for w in weak)

    def test_recommendations_empty(self):
        r = StealthAuditReport()
        assert r.recommendations == []

    def test_recommendations_from_score(self):
        sr = StealthScoreResult(score=0.5, recommendations=["Fix webdriver", "Fix plugins"])
        r = StealthAuditReport(score_result=sr)
        assert len(r.recommendations) == 2

    def test_recommendations_from_benchmark(self):
        br = BenchmarkResult(
            score=50,
            failed=2,
            details=[
                BenchmarkTestResult(name="webdriver", passed=False),
                BenchmarkTestResult(name="plugins", passed=False),
            ],
        )
        r = StealthAuditReport(benchmark_result=br)
        assert len(r.recommendations) == 1
        assert "webdriver" in r.recommendations[0]

    def test_summary_empty(self):
        r = StealthAuditReport()
        s = r.summary
        assert "StealthAudit" in s

    def test_summary_with_all(self):
        sr = StealthScoreResult(score=0.85, risk_level=RiskLevel.LOW)
        br = BenchmarkResult(score=78)
        pr = PipelineResult(level="advanced")
        r = StealthAuditReport(
            score_result=sr,
            benchmark_result=br,
            pipeline_result=pr,
            overall_score=82.0,
            duration_ms=5000,
        )
        s = r.summary
        assert "score=0.85" in s
        assert "benchmark=78/100" in s
        assert "pipeline=advanced" in s
        assert "overall=82/100" in s

    def test_to_dict(self):
        r = StealthAuditReport(overall_score=75.0, duration_ms=3000)
        d = r.to_dict()
        assert d["overall_score"] == 75.0
        assert d["duration_ms"] == 3000


# ─── StealthAudit init ─────────────────────────────────────────────────────


class TestStealthAuditInit:
    def test_default_init(self):
        audit = StealthAudit()
        assert audit._level == "advanced"

    def test_custom_level(self):
        audit = StealthAudit(level="full")
        assert audit._level == "full"

    def test_all_levels(self):
        for level in ["minimal", "standard", "advanced", "full"]:
            audit = StealthAudit(level=level)
            assert audit._level == level


# ─── StealthAudit.run_score_only ──────────────────────────────────────────


class TestRunScoreOnly:
    @pytest.mark.asyncio
    async def test_run_score(self):
        audit = StealthAudit()
        page = MagicMock()
        mock_sr = StealthScoreResult(score=0.9, risk_level=RiskLevel.LOW)

        with patch.object(StealthScorer, "score", new_callable=AsyncMock, return_value=mock_sr):
            report = await audit.run_score(page)

        assert report.score_result is mock_sr
        assert report.score == 0.9
        assert report.benchmark_result is None
        assert report.pipeline_result is None


# ─── StealthAudit.run_full ────────────────────────────────────────────────


class TestRunFull:
    @pytest.mark.asyncio
    async def test_run_full(self):
        audit = StealthAudit()
        page = MagicMock()

        mock_sr = StealthScoreResult(score=0.85, risk_level=RiskLevel.LOW)
        mock_br = BenchmarkResult(score=78, passed=15, failed=3, total=18)
        mock_pr = PipelineResult(level="advanced")

        with (
            patch.object(StealthScorer, "score", new_callable=AsyncMock, return_value=mock_sr),
            patch.object(StealthBenchmark, "run", new_callable=AsyncMock, return_value=mock_br),
            patch.object(StealthPipeline, "apply", new_callable=AsyncMock, return_value=mock_pr),
        ):
            report = await audit.run_full(page)

        assert report.score_result is mock_sr
        assert report.benchmark_result is mock_br
        assert report.pipeline_result is mock_pr
        assert report.overall_score > 0
