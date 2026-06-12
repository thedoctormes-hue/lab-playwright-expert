"""
StealthAudit — единый аудит скрытности браузера.

Агрегирует результаты из трёх модулей:
  - stealth_score.py   → StealthScoreResult (оценка 0.0-1.0 по 9 проверкам)
  - stealth_benchmark.py → BenchmarkResult (реальный бенчмарк на bot.sannysoft.com)
  - stealth_pipeline.py  → PipelineResult (применённые слои защиты)

Использование:
    >>> audit = StealthAudit(level="advanced")
    >>> report = await audit.run_full(page)
    >>> print(report.summary)
    StealthAudit: score=0.87, risk=low, benchmark=78/100, pipeline=advanced(18 scripts, audio, webrtc)
    >>> print(report.to_dict())  # для логирования/отправки

Модули опциональны: можно запустить только score, только benchmark, или всё вместе.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from playwright.async_api import Page

from .stealth_score import RiskLevel, StealthScoreResult, StealthScorer
from .stealth_benchmark import BenchmarkResult, StealthBenchmark
from .stealth_pipeline import PipelineResult, StealthPipeline


@dataclass
class StealthAuditReport:
    """Единый отчёт аудита скрытности.

    Собирает результаты из всех трёх модулей в один объект.

    Attributes:
        score_result: Результат StealthScorer (оценка по 9 проверкам).
        benchmark_result: Результат StealthBenchmark (реальный бенчмарк).
        pipeline_result: Результат StealthPipeline (применённые слои).
        overall_score: Общий score (0-100, взвешенный).
        duration_ms: Общее время выполнения аудита.
        timestamp: Время создания отчёта.
    """
    score_result: StealthScoreResult | None = None
    benchmark_result: BenchmarkResult | None = None
    pipeline_result: PipelineResult | None = None
    overall_score: float = 0.0
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @property
    def score(self) -> float:
        """Score от StealthScorer (0.0-1.0), если был запущен."""
        if self.score_result:
            return self.score_result.score
        return 0.0

    @property
    def risk_level(self) -> str:
        """Уровень риска, если score был запущен."""
        if self.score_result:
            return self.score_result.risk_level.value
        return "unknown"

    @property
    def benchmark_score(self) -> int:
        """Score от StealthBenchmark (0-100), если был запущен."""
        if self.benchmark_result:
            return self.benchmark_result.score
        return 0

    @property
    def pipeline_level(self) -> str:
        """Уровень pipeline, если был применён."""
        if self.pipeline_result:
            return self.pipeline_result.level
        return "none"

    @property
    def weak_points(self) -> list[str]:
        """Список слабых мест из всех модулей."""
        weak: list[str] = []

        if self.score_result:
            for check in self.score_result.checks:
                if not check.passed:
                    weak.append(f"score:{check.name} ({check.risk.value})")

        if self.benchmark_result:
            for name in self.benchmark_result.failed_names:
                weak.append(f"benchmark:{name}")

        return weak

    @property
    def recommendations(self) -> list[str]:
        """Объединённые рекомендации из всех модулей."""
        recs: list[str] = []

        if self.score_result:
            recs.extend(self.score_result.recommendations)

        if self.benchmark_result and self.benchmark_result.failed:
            recs.append(
                f"Benchmark failed tests: {', '.join(self.benchmark_result.failed_names)}"
            )

        return recs

    @property
    def summary(self) -> str:
        """Краткое описание отчёта."""
        parts = []

        if self.score_result:
            parts.append(
                f"score={self.score_result.score:.2f}/{self.risk_level}"
            )

        if self.benchmark_result:
            parts.append(
                f"benchmark={self.benchmark_result.score}/100"
            )

        if self.pipeline_result:
            parts.append(
                f"pipeline={self.pipeline_result.level}"
            )

        if self.overall_score > 0:
            parts.append(f"overall={self.overall_score:.0f}/100")

        return f"StealthAudit({', '.join(parts)}, {self.duration_ms:.0f}ms)"

    def to_dict(self) -> dict[str, Any]:
        """Сериализация в словарь (для JSON/логирования)."""
        return {
            "overall_score": self.overall_score,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "score": {
                "value": self.score,
                "risk_level": self.risk_level,
                "passed": self.score_result.passed_checks if self.score_result else 0,
                "total": self.score_result.total_checks if self.score_result else 0,
                "checks": [
                    {
                        "name": c.name,
                        "passed": c.passed,
                        "score": c.score,
                        "risk": c.risk.value,
                    }
                    for c in (self.score_result.checks if self.score_result else [])
                ],
            },
            "benchmark": {
                "score": self.benchmark_score,
                "passed": self.benchmark_result.passed if self.benchmark_result else 0,
                "failed": self.benchmark_result.failed if self.benchmark_result else 0,
                "total": self.benchmark_result.total if self.benchmark_result else 0,
                "failed_tests": self.benchmark_result.failed_names if self.benchmark_result else [],
            },
            "pipeline": {
                "level": self.pipeline_level,
                "scripts": self.pipeline_result.stealth_scripts if self.pipeline_result else 0,
                "audio": self.pipeline_result.audio_applied if self.pipeline_result else False,
                "webrtc": self.pipeline_result.webrtc_applied if self.pipeline_result else False,
                "client_hints": self.pipeline_result.client_hints_applied if self.pipeline_result else False,
            },
            "weak_points": self.weak_points,
            "recommendations": self.recommendations,
        }


class StealthAudit:
    """Единый аудит скрытности браузера.

    Запускает score, benchmark и/или pipeline и собирает результаты
    в единый StealthAuditReport.

    Example:
        >>> audit = StealthAudit(level="advanced")
        >>> report = await audit.run_full(page)
        >>> print(report.summary)
        StealthAudit(score=0.87/low, benchmark=78/100, pipeline=advanced, overall=82/100, 3500ms)

        >>> # Только score (быстро, без браузера):
        >>> report = await audit.run_score(page)
        >>> print(report.score)

        >>> # Только benchmark (реальный тест):
        >>> report = await audit.run_benchmark()
        >>> print(report.benchmark_score)
    """

    def __init__(
        self,
        level: str = "advanced",
        benchmark_url: str = StealthBenchmark.DEFAULT_URL,
        benchmark_timeout_ms: int = 30000,
    ):
        """Инициализация аудита.

        Args:
            level: Уровень stealth для pipeline (minimal/standard/advanced/full).
            benchmark_url: URL для бенчмарка.
            benchmark_timeout_ms: Таймаут бенчмарка.
        """
        self._level = level
        self._benchmark_url = benchmark_url
        self._benchmark_timeout_ms = benchmark_timeout_ms
        self._scorer = StealthScorer()
        self._pipeline = StealthPipeline.level(level)
        self._benchmark = StealthBenchmark(
            config=self._pipeline.stealth_config,
            url=benchmark_url,
            timeout_ms=benchmark_timeout_ms,
        )

    async def run_full(self, page: Page) -> StealthAuditReport:
        """Полный аудит: score + pipeline + benchmark.

        Args:
            page: Playwright Page объект.

        Returns:
            StealthAuditReport с результатами всех трёх модулей.
        """
        start = time.monotonic()
        report = StealthAuditReport()

        # 1. Score (быстро, на текущей странице)
        try:
            report.score_result = await self._scorer.score(page)
            logger.info(f"StealthAudit: score={report.score_result.score:.2f}")
        except Exception as e:
            logger.warning(f"StealthAudit: score failed: {e}")

        # 2. Pipeline (применить защиту)
        try:
            report.pipeline_result = await self._pipeline.apply(page)
            logger.info(f"StealthAudit: pipeline={report.pipeline_result.summary}")
        except Exception as e:
            logger.warning(f"StealthAudit: pipeline failed: {e}")

        # 3. Benchmark (реальный тест на bot.sannysoft.com)
        try:
            report.benchmark_result = await self._benchmark.run()
            logger.info(f"StealthAudit: benchmark={report.benchmark_result.summary}")
        except Exception as e:
            logger.warning(f"StealthAudit: benchmark failed: {e}")

        # Считаем общий score
        report.duration_ms = (time.monotonic() - start) * 1000
        report.overall_score = self._calc_overall_score(report)

        logger.info(f"StealthAudit: {report.summary}")
        return report

    async def run_score(self, page: Page) -> StealthAuditReport:
        """Только score (быстро, без запуска браузера).

        Args:
            page: Playwright Page объект.

        Returns:
            StealthAuditReport только с score_result.
        """
        start = time.monotonic()
        report = StealthAuditReport()

        try:
            report.score_result = await self._scorer.score(page)
        except Exception as e:
            logger.warning(f"StealthAudit: score failed: {e}")

        report.duration_ms = (time.monotonic() - start) * 1000
        report.overall_score = report.score * 100

        logger.info(f"StealthAudit (score only): {report.summary}")
        return report

    async def run_benchmark(self) -> StealthAuditReport:
        """Только benchmark (реальный тест).

        Returns:
            StealthAuditReport только с benchmark_result.
        """
        start = time.monotonic()
        report = StealthAuditReport()

        report.benchmark_result = await self._benchmark.run()
        report.duration_ms = (time.monotonic() - start) * 1000
        report.overall_score = float(report.benchmark_score)

        logger.info(f"StealthAudit (benchmark only): {report.summary}")
        return report

    async def run_pipeline(self, page: Page) -> StealthAuditReport:
        """Только pipeline (применить защиту).

        Args:
            page: Playwright Page объект.

        Returns:
            StealthAuditReport только с pipeline_result.
        """
        start = time.monotonic()
        report = StealthAuditReport()

        report.pipeline_result = await self._pipeline.apply(page)
        report.duration_ms = (time.monotonic() - start) * 1000

        logger.info(f"StealthAudit (pipeline only): {report.summary}")
        return report

    @staticmethod
    def _calc_overall_score(report: StealthAuditReport) -> float:
        """Рассчитать общий score из доступных результатов.

        Веса:
          - score: 40% (если есть)
          - benchmark: 60% (если есть)

        Returns:
            float: Общий score 0-100.
        """
        scores: list[tuple[float, float]] = []  # (score, weight)

        if report.score_result:
            scores.append((report.score * 100, 0.4))

        if report.benchmark_result:
            scores.append((float(report.benchmark_score), 0.6))

        if not scores:
            return 0.0

        total_weight = sum(w for _, w in scores)
        weighted = sum(s * w for s, w in scores)
        return weighted / total_weight
