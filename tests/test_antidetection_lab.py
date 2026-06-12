"""
Tests for Anti-Detection Research Lab.
Covers: ResearchReport, VectorResult, ResearchDatabase, HTMLReportGenerator, CLI.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── Setup paths ──────────────────────────────────────────────────────────────
_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from scripts.antidetection_lab import (
    ResearchReport,
    VectorResult,
    ResearchDatabase,
    HTMLReportGenerator,
    VECTOR_RESEARCHERS,
    BehavioralResearch,
    TimingResearch,
    JSDetectionResearch,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════════════════

class TestVectorResult:
    """Tests for VectorResult dataclass."""

    def test_creation(self):
        """Создание VectorResult."""
        r = VectorResult(
            vector="canvas",
            test_name="canvas_noise",
            detected=False,
            detection_rate=10.0,
            countermeasure="Canvas noise injection",
            countermeasure_effectiveness=90.0,
            risk_level="low",
            details={"noise_seed": 42},
            notes="Canvas noise effectively prevents fingerprinting",
        )
        assert r.vector == "canvas"
        assert r.test_name == "canvas_noise"
        assert r.detected is False
        assert r.detection_rate == 10.0
        assert r.countermeasure == "Canvas noise injection"
        assert r.countermeasure_effectiveness == 90.0
        assert r.risk_level == "low"
        assert r.details["noise_seed"] == 42
        assert r.notes == "Canvas noise effectively prevents fingerprinting"

    def test_creation_defaults(self):
        """Создание с дефолтными значениями."""
        r = VectorResult(
            vector="", test_name="", detected=False,
            detection_rate=0.0, countermeasure="",
            countermeasure_effectiveness=0.0, risk_level="medium",
        )
        assert r.vector == ""
        assert r.test_name == ""
        assert r.detected is False
        assert r.detection_rate == 0.0
        assert r.countermeasure == ""
        assert r.countermeasure_effectiveness == 0.0
        assert r.risk_level == "medium"
        assert r.details == {}
        assert r.notes == ""


class TestResearchReport:
    """Tests for ResearchReport dataclass."""

    def test_creation(self):
        """Создание отчёта."""
        report = ResearchReport(
            timestamp="2026-01-01T00:00:00",
            vectors_researched=["canvas", "webgl"],
            overall_detection_risk=25.0,
            overall_protection_score=85.0,
            duration_seconds=10.5,
        )
        assert report.timestamp == "2026-01-01T00:00:00"
        assert report.vectors_researched == ["canvas", "webgl"]
        assert report.overall_detection_risk == 25.0
        assert report.overall_protection_score == 85.0
        assert report.duration_seconds == 10.5
        assert report.results == []
        assert report.comparison is None

    def test_summary_property(self):
        """Свойство summary."""
        report = ResearchReport(
            timestamp="2026-01-01T00:00:00",
            vectors_researched=["canvas"],
            overall_detection_risk=30.0,
            overall_protection_score=80.0,
        )
        summary = report.summary
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_summary_with_results(self):
        """Summary с результатами."""
        r1 = VectorResult(
            vector="canvas", test_name="noise_test", detected=False,
            detection_rate=10.0, countermeasure="noise", countermeasure_effectiveness=90.0,
            risk_level="low",
        )
        r2 = VectorResult(
            vector="webgl", test_name="renderer_test", detected=True,
            detection_rate=60.0, countermeasure="spoofing", countermeasure_effectiveness=70.0,
            risk_level="medium",
        )
        report = ResearchReport(
            timestamp="2026-01-01T00:00:00",
            vectors_researched=["canvas", "webgl"],
            results=[r1, r2],
            overall_detection_risk=35.0,
            overall_protection_score=80.0,
        )
        summary = report.summary
        assert "canvas" in summary or "webgl" in summary

    def test_comparison_field(self):
        """Поле comparison."""
        report = ResearchReport(
            timestamp="2026-01-01T00:00:00",
            vectors_researched=["canvas"],
            comparison={
                "Previous Risk": "40%",
                "Current Risk": "30%",
                "Risk Change": "-10%",
            },
        )
        assert report.comparison is not None
        assert "Previous Risk" in report.comparison


# ═══════════════════════════════════════════════════════════════════════════════
# ResearchDatabase
# ═══════════════════════════════════════════════════════════════════════════════

class TestResearchDatabase:
    """Tests for ResearchDatabase."""

    def _make_db(self):
        """Создать временную БД."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        return ResearchDatabase(db_path=tmp.name), tmp.name

    def test_init_creates_tables(self):
        """Инициализация создаёт таблицы."""
        db, path = self._make_db()
        try:
            conn = sqlite3.connect(path)
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            assert "research_results" in tables
            assert "research_sessions" in tables
            conn.close()
        finally:
            os.unlink(path)

    def test_save_result(self):
        """Сохранение результата."""
        db, path = self._make_db()
        try:
            r = VectorResult(
                vector="canvas", test_name="noise_test", detected=False,
                detection_rate=10.0, countermeasure="noise", countermeasure_effectiveness=90.0,
                risk_level="low",
            )
            db.save_result(r)

            conn = sqlite3.connect(path)
            cursor = conn.execute("SELECT COUNT(*) FROM research_results")
            assert cursor.fetchone()[0] == 1
            conn.close()
        finally:
            os.unlink(path)

    def test_save_session(self):
        """Сохранение сессии."""
        db, path = self._make_db()
        try:
            report = ResearchReport(
                timestamp="2026-01-01T00:00:00",
                vectors_researched=["canvas"],
                overall_detection_risk=30.0,
                overall_protection_score=80.0,
            )
            db.save_session(report)

            conn = sqlite3.connect(path)
            cursor = conn.execute("SELECT COUNT(*) FROM research_sessions")
            assert cursor.fetchone()[0] == 1
            conn.close()
        finally:
            os.unlink(path)

    def test_get_previous_session(self):
        """Получение предыдущей сессии."""
        db, path = self._make_db()
        try:
            # No previous session initially
            assert db.get_previous_session() is None

            # Save a session
            report = ResearchReport(
                timestamp="2026-01-01T00:00:00",
                vectors_researched=["canvas"],
                overall_detection_risk=30.0,
                overall_protection_score=80.0,
            )
            db.save_session(report)

            # Now there should be a previous session
            prev = db.get_previous_session()
            assert prev is not None
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════════════════
# Vector Researchers
# ═══════════════════════════════════════════════════════════════════════════════

class TestVectorResearchers:
    """Tests for vector researcher registry."""

    def test_all_vectors_registered(self):
        """Все векторы зарегистрированы."""
        expected = {"canvas", "webgl", "behavior", "timing", "headers", "js"}
        assert set(VECTOR_RESEARCHERS.keys()) == expected

    def test_researchers_are_classes(self):
        """Исследователи — классы."""
        for name, cls in VECTOR_RESEARCHERS.items():
            assert isinstance(cls, type), f"{name} is not a class"

    def test_researchers_have_run_method(self):
        """Исследователи имеют метод run."""
        for name, cls in VECTOR_RESEARCHERS.items():
            assert hasattr(cls, 'run'), f"{name} missing run method"


# ═══════════════════════════════════════════════════════════════════════════════
# BehavioralResearch (Unit Tests)
# ═══════════════════════════════════════════════════════════════════════════════

class TestBehavioralResearch:
    """Tests for BehavioralResearch static methods."""

    def test_generate_bot_movements(self):
        """Ботоподобное движение — прямолинейное."""
        points = BehavioralResearch._generate_bot_movements(0, 0, 100, 100, 10)
        assert len(points) == 11
        assert points[0] == (0, 0)
        assert points[-1] == (100, 100)

    def test_generate_human_movements(self):
        """Человеческое движение — кривая Безье."""
        points = BehavioralResearch._generate_human_movements(0, 0, 100, 100, 10)
        assert len(points) == 11
        # Start and end should be approximately correct
        assert abs(points[0][0]) < 5
        assert abs(points[0][1]) < 5

    def test_calculate_linearity_straight_line(self):
        """Линейность прямой линии ≈ 1.0."""
        points = [(i, i) for i in range(10)]
        linearity = BehavioralResearch._calculate_linearity(points)
        assert linearity > 0.9

    def test_calculate_linearity_few_points(self):
        """Линейность для < 3 точек."""
        assert BehavioralResearch._calculate_linearity([(0, 0), (1, 1)]) == 1.0
        assert BehavioralResearch._calculate_linearity([]) == 1.0

    def test_calculate_speed_variance(self):
        """Дисперсия скорости."""
        points = [(0, 0), (10, 0), (20, 0), (30, 0)]
        variance = BehavioralResearch._calculate_speed_variance(points)
        assert variance >= 0

    def test_calculate_speed_variance_single_point(self):
        """Дисперсия скорости для одной точки."""
        assert BehavioralResearch._calculate_speed_variance([(0, 0)]) == 0.0

    def test_generate_bot_keystrokes(self):
        """Ботоподобные нажатия — фиксированные интервалы."""
        intervals = BehavioralResearch._generate_bot_keystrokes(10)
        assert len(intervals) == 10
        assert all(i == intervals[0] for i in intervals)

    def test_generate_human_keystrokes(self):
        """Человеческие нажатия — переменные интервалы."""
        intervals = BehavioralResearch._generate_human_keystrokes(100)
        assert len(intervals) == 100
        # Should have some variance
        assert len(set(intervals)) > 1

    def test_generate_bot_scrolls(self):
        """Ботоподобный скролл — регулярный."""
        scrolls = BehavioralResearch._generate_bot_scrolls(2)
        assert len(scrolls) == 20
        assert all(s == 800 for s in scrolls)

    def test_generate_human_scrolls(self):
        """Человеческий скролл — переменный."""
        scrolls = BehavioralResearch._generate_human_scrolls(2)
        # Base count is pages*10, plus random reverse scrolls (15% chance each)
        assert len(scrolls) >= 20
        # Should have some negative (reverse) scrolls or varied values
        assert any(s < 0 for s in scrolls) or len(set(scrolls)) > 1

    def test_calculate_scroll_regularity(self):
        """Регулярность скролла."""
        regular_scrolls = [800] * 10
        regularity = BehavioralResearch._calculate_scroll_regularity(regular_scrolls)
        assert regularity > 0.9

    def test_calculate_scroll_regularity_empty(self):
        """Регулярность пустого скролла."""
        assert BehavioralResearch._calculate_scroll_regularity([]) == 1.0
        assert BehavioralResearch._calculate_scroll_regularity([100]) == 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# HTMLReportGenerator
# ═══════════════════════════════════════════════════════════════════════════════

class TestHTMLReportGenerator:
    """Tests for HTMLReportGenerator."""

    def test_generates_html(self):
        """Генерация HTML."""
        report = ResearchReport(
            timestamp="2026-01-01T00:00:00",
            vectors_researched=["canvas", "webgl"],
            overall_detection_risk=30.0,
            overall_protection_score=80.0,
        )
        html = HTMLReportGenerator.generate(report)
        assert isinstance(html, str)
        assert len(html) > 0
        assert "<html" in html.lower()

    def test_html_contains_vectors(self):
        """HTML содержит векторы."""
        r = VectorResult(
            vector="canvas", test_name="noise_test", detected=False,
            detection_rate=10.0, countermeasure="noise", countermeasure_effectiveness=90.0,
            risk_level="low",
        )
        report = ResearchReport(
            timestamp="2026-01-01T00:00:00",
            vectors_researched=["canvas"],
            results=[r],
        )
        html = HTMLReportGenerator.generate(report)
        assert "canvas" in html

    def test_html_contains_results(self):
        """HTML содержит результаты."""
        r = VectorResult(
            vector="canvas", test_name="noise_test", detected=False,
            detection_rate=10.0, countermeasure="noise", countermeasure_effectiveness=90.0,
            risk_level="low",
        )
        report = ResearchReport(
            timestamp="2026-01-01T00:00:00",
            vectors_researched=["canvas"],
            results=[r],
        )
        html = HTMLReportGenerator.generate(report)
        assert "noise_test" in html

    def test_html_contains_comparison(self):
        """HTML содержит сравнение."""
        report = ResearchReport(
            timestamp="2026-01-01T00:00:00",
            vectors_researched=["canvas"],
            comparison={"Previous Risk": "40%", "Current Risk": "30%"},
        )
        html = HTMLReportGenerator.generate(report)
        assert "40%" in html
        assert "30%" in html


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Arguments
# ═══════════════════════════════════════════════════════════════════════════════

class TestCLI:
    """Tests for CLI argument parsing."""

    def test_valid_research_vectors(self):
        """Валидные векторы исследования."""
        valid = ["canvas", "webgl", "behavior", "timing", "headers", "js"]
        for v in valid:
            assert v in VECTOR_RESEARCHERS

    def test_all_vector(self):
        """'all' — все векторы."""
        all_vectors = list(VECTOR_RESEARCHERS.keys())
        assert len(all_vectors) >= 4

    def test_unknown_vector(self):
        """Неизвестный вектор."""
        assert "unknown_vector" not in VECTOR_RESEARCHERS
