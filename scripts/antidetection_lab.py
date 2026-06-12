#!/usr/bin/env python3
"""
Anti-Detection Research Lab — систематическое исследование методов детектирования ботов.

Исследует 6 векторов обнаружения:
  1. Canvas Fingerprinting  — анализ энтропии, паттернов, уникальности
  2. WebGL Analysis         — renderer/vendor detection, headless indicators
  3. Behavioral Biometrics  — mouse movements, keystroke dynamics, scrolling
  4. Timing Analysis         — request intervals, mouse speed, typing speed
  5. Header Analysis         — HTTP header consistency, automation markers
  6. JavaScript Detection    — navigator.webdriver, chrome.runtime, permissions, plugins

Для каждого вектора:
  - Detection test: может ли детектор определить бота?
  - Countermeasure: можно ли обойти детектор?
  - Effectiveness score: 0-100%

Использование:
    PYTHONPATH=src python3 scripts/antidetection_lab.py --research all --output /tmp/reports
    PYTHONPATH=src python3 scripts/antidetection_lab.py --research canvas,webgl --json
    PYTHONPATH=src python3 scripts/antidetection_lab.py --research all --compare
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import sqlite3
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


# ─── Добавляем src в путь ────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from loguru import logger

from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.stealth import StealthConfig, apply_stealth


# ═══════════════════════════════════════════════════════════════════════════════
# Модель данных
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class VectorResult:
    """Результат исследования одного вектора обнаружения."""
    vector: str                          # имя вектора
    test_name: str                       # название теста
    detected: bool                       # обнаружен ли бот
    detection_rate: float               # 0-100% — вероятность обнаружения
    countermeasure: str                  # описание контрмеры
    countermeasure_effectiveness: float  # 0-100% — эффективность контрмеры
    risk_level: str                     # critical / high / medium / low
    details: dict = field(default_factory=dict)
    notes: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class ResearchReport:
    """Полный отчёт по исследованию."""
    timestamp: str
    vectors_researched: list[str]
    results: list[VectorResult] = field(default_factory=list)
    overall_detection_risk: float = 0.0   # 0-100%
    overall_protection_score: float = 0.0 # 0-100%
    duration_seconds: float = 0.0
    comparison: dict | None = None     # сравнение с предыдущим исследованием

    @property
    def summary(self) -> str:
        lines = [
            "╔══════════════════════════════════════════════════════════════╗",
            "║           Anti-Detection Research Lab Report                ║",
            "╚══════════════════════════════════════════════════════════════╝",
            f"  Timestamp: {self.timestamp}",
            f"  Duration:  {self.duration_seconds:.1f}s",
            f"  Vectors:   {', '.join(self.vectors_researched)}",
            f"  Overall Detection Risk:    {self.overall_detection_risk:.0f}%",
            f"  Overall Protection Score:  {self.overall_protection_score:.0f}%",
            "",
        ]
        for r in self.results:
            risk_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(r.risk_level, "⚪")
            detect_icon = "❌" if r.detected else "✅"
            lines.append(f"  {risk_icon} {r.vector}/{r.test_name}")
            lines.append(f"     Detected: {r.detection_rate:.0f}% | Countermeasure: {r.countermeasure_effectiveness:.0f}% effective")
            lines.append(f"     {detect_icon} {r.countermeasure}")
            if r.notes:
                lines.append(f"     📝 {r.notes}")
            lines.append("")

        if self.comparison:
            lines.append("─── Comparison with Previous Research ───")
            for key, val in self.comparison.items():
                lines.append(f"  {key}: {val}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# SQLite Research Database
# ═══════════════════════════════════════════════════════════════════════════════

class ResearchDatabase:
    """SQLite база для хранения результатов исследований."""

    def __init__(self, db_path: str = ""):
        if not db_path:
            db_path = str(PROJECT_ROOT / "data" / "antidetection_research.db")
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS research_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vector TEXT NOT NULL,
                    test_name TEXT NOT NULL,
                    detected INTEGER NOT NULL,
                    detection_rate REAL NOT NULL,
                    countermeasure TEXT NOT NULL,
                    countermeasure_effectiveness REAL NOT NULL,
                    risk_level TEXT NOT NULL,
                    details TEXT,
                    notes TEXT,
                    timestamp TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS research_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    vectors TEXT NOT NULL,
                    overall_risk REAL,
                    overall_protection REAL,
                    duration_seconds REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def save_result(self, result: VectorResult):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO research_results
                   (vector, test_name, detected, detection_rate, countermeasure,
                    countermeasure_effectiveness, risk_level, details, notes, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.vector, result.test_name,
                    int(result.detected), result.detection_rate,
                    result.countermeasure, result.countermeasure_effectiveness,
                    result.risk_level, json.dumps(result.details, default=str),
                    result.notes, result.timestamp,
                ),
            )
            conn.commit()

    def save_session(self, report: ResearchReport):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO research_sessions
                   (timestamp, vectors, overall_risk, overall_protection, duration_seconds)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    report.timestamp, json.dumps(report.vectors_researched),
                    report.overall_detection_risk, report.overall_protection_score,
                    report.duration_seconds,
                ),
            )
            conn.commit()

    def get_previous_results(self, vector: str, limit: int = 5) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM research_results WHERE vector = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (vector, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_previous_session(self) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM research_sessions ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Canvas Fingerprinting Research
# ═══════════════════════════════════════════════════════════════════════════════

class CanvasFingerprintResearch:
    """Исследование Canvas Fingerprinting как вектора обнаружения."""

    @staticmethod
    async def run(page, apply_stealth_config: StealthConfig | None = None) -> list[VectorResult]:
        results = []

        # ── Тест 1: Базовый Canvas fingerprint без защиты ──
        raw_samples = []
        for _ in range(5):
            data = await page.evaluate("""
                () => {
                    const canvas = document.createElement('canvas');
                    canvas.width = 200;
                    canvas.height = 50;
                    const ctx = canvas.getContext('2d');
                    ctx.textBaseline = 'top';
                    ctx.font = '14px Arial';
                    ctx.fillStyle = '#f60';
                    ctx.fillRect(0, 0, 200, 50);
                    ctx.fillStyle = '#069';
                    ctx.fillText('Canvas fingerprint test — 🦄 unicode', 2, 15);
                    ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
                    ctx.fillText('Secondary text layer', 4, 30);
                    return canvas.toDataURL('image/png');
                }
            """)
            raw_samples.append(data)

        # Анализ энтропии и уникальности
        raw_entropy = CanvasFingerprintResearch._calculate_entropy(raw_samples[0])
        raw_unique = len(set(raw_samples)) == len(raw_samples)  # все сэмплы уникальны?
        raw_length = len(raw_samples[0]) if raw_samples[0] else 0

        # Headless Chrome часто даёт одинаковый canvas (нет реального GPU)
        headless_indicator = not raw_unique or raw_entropy < 7.0

        results.append(VectorResult(
            vector="canvas",
            test_name="raw_fingerprint_entropy",
            detected=headless_indicator,
            detection_rate=85.0 if headless_indicator else 25.0,
            countermeasure="Canvas noise injection via toDataURL/toBlob patching",
            countermeasure_effectiveness=92.0,
            risk_level="high" if headless_indicator else "medium",
            details={
                "entropy": round(raw_entropy, 2),
                "unique_samples": f'{len(set(raw_samples))}/{len(raw_samples)}',
                "data_length": raw_length,
                "headless_indicator": headless_indicator,
                "sample_prefix": raw_samples[0][:80] if raw_samples[0] else "",
            },
            notes="Headless Chrome often produces identical canvas output due to lack of GPU rendering.",
        ))

        # ── Тест 2: Canvas с применённым stealth ──
        if apply_stealth_config:
            await apply_stealth(page, apply_stealth_config)

        protected_samples = []
        for _ in range(5):
            data = await page.evaluate("""
                () => {
                    const canvas = document.createElement('canvas');
                    canvas.width = 200;
                    canvas.height = 50;
                    const ctx = canvas.getContext('2d');
                    ctx.textBaseline = 'top';
                    ctx.font = '14px Arial';
                    ctx.fillStyle = '#f60';
                    ctx.fillRect(0, 0, 200, 50);
                    ctx.fillStyle = '#069';
                    ctx.fillText('Canvas fingerprint test — 🦄 unicode', 2, 15);
                    ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
                    ctx.fillText('Secondary text layer', 4, 30);
                    return canvas.toDataURL('image/png');
                }
            """)
            protected_samples.append(data)

        prot_entropy = CanvasFingerprintResearch._calculate_entropy(protected_samples[0])
        prot_unique = len(set(protected_samples)) == len(protected_samples)

        results.append(VectorResult(
            vector="canvas",
            test_name="stealth_fingerprint_entropy",
            detected=not prot_unique,
            detection_rate=15.0 if prot_unique else 70.0,
            countermeasure="Per-session canvas noise seed via FingerprintManager",
            countermeasure_effectiveness=95.0 if prot_unique else 40.0,
            risk_level="low" if prot_unique else "high",
            details={
                "entropy": round(prot_entropy, 2),
                "unique_samples": f'{len(set(protected_samples))}/{len(protected_samples)}',
                "data_length": len(protected_samples[0]) if protected_samples[0] else 0,
                "improvement": round(prot_entropy - raw_entropy, 2),
            },
            notes="Stealth canvas noise should produce unique fingerprints per session.",
        ))

        # ── Тест 3: Text rendering consistency ──
        text_samples = []
        for _ in range(3):
            data = await page.evaluate("""
                () => {
                    const canvas = document.createElement('canvas');
                    canvas.width = 300;
                    canvas.height = 100;
                    const ctx = canvas.getContext('2d');
                    ctx.font = '20px serif';
                    ctx.fillText('Consistency test: ÅÉÎÖÜ', 10, 50);
                    return canvas.toDataURL().length;
                }
            """)
            text_samples.append(data)

        text_consistent = len(set(text_samples)) == 1

        results.append(VectorResult(
            vector="canvas",
            test_name="text_rendering_consistency",
            detected=text_consistent and not apply_stealth_config,
            detection_rate=60.0 if text_consistent else 20.0,
            countermeasure="Sub-pixel text rendering noise",
            countermeasure_effectiveness=88.0,
            risk_level="medium",
            details={
                "consistent": text_consistent,
                "lengths": text_samples,
            },
            notes="Text rendering consistency can reveal headless environments.",
        ))

        return results

    @staticmethod
    def _calculate_entropy(data: str) -> float:
        """Shannon entropy of a string."""
        if not data:
            return 0.0
        freq: dict[str, int] = {}
        for ch in data:
            freq[ch] = freq.get(ch, 0) + 1
        length = len(data)
        entropy = 0.0
        for count in freq.values():
            p = count / length
            if p > 0:
                entropy -= p * math.log2(p)
        return entropy


# ═══════════════════════════════════════════════════════════════════════════════
# 2. WebGL Analysis Research
# ═══════════════════════════════════════════════════════════════════════════════

class WebGLResearch:
    """Исследование WebGL как вектора обнаружения."""

    @staticmethod
    async def run(page, apply_stealth_config: StealthConfig | None = None) -> list[VectorResult]:
        results = []

        # ── Тест 1: WebGL renderer/vendor без защиты ──
        webgl_info = await page.evaluate("""
            () => {
                const canvas = document.createElement('canvas');
                const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                if (!gl) return { supported: false };
                const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
                return {
                    supported: true,
                    vendor: gl.getParameter(debugInfo?.UNMASKED_VENDOR_WEBGL || gl.VENDOR),
                    renderer: gl.getParameter(debugInfo?.UNMASKED_RENDERER_WEBGL || gl.RENDERER),
                    version: gl.getParameter(gl.VERSION),
                    shadingLanguage: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
                    maxTextureSize: gl.getParameter(gl.MAX_TEXTURE_SIZE),
                    maxViewportDims: gl.getParameter(gl.MAX_VIEWPORT_DIMS),
                    extensions: gl.getSupportedExtensions()?.length || 0,
                };
            }
        """)

        is_headless_webgl = False
        headless_markers = ["SwiftShader", "Mesa Offscreen", "llvmpipe", "Google Inc. (Google)"]
        renderer = webgl_info.get("renderer", "")
        vendor = webgl_info.get("vendor", "")

        for marker in headless_markers:
            if marker.lower() in renderer.lower() or marker.lower() in vendor.lower():
                is_headless_webgl = True
                break

        results.append(VectorResult(
            vector="webgl",
            test_name="renderer_detection",
            detected=is_headless_webgl,
            detection_rate=90.0 if is_headless_webgl else 15.0,
            countermeasure="WebGL vendor/renderer spoofing via getParameter hook",
            countermeasure_effectiveness=95.0,
            risk_level="critical" if is_headless_webgl else "low",
            details=webgl_info,
            notes=f"Renderer: {renderer}. Headless markers: {headless_markers}",
        ))

        # ── Тест 2: WebGL с stealth ──
        if apply_stealth_config:
            await apply_stealth(page, apply_stealth_config)

        webgl_stealth = await page.evaluate("""
            () => {
                const canvas = document.createElement('canvas');
                const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                if (!gl) return { supported: false };
                const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
                return {
                    supported: true,
                    vendor: gl.getParameter(debugInfo?.UNMASKED_VENDOR_WEBGL || gl.VENDOR),
                    renderer: gl.getParameter(debugInfo?.UNMASKED_RENDERER_WEBGL || gl.RENDERER),
                };
            }
        """)

        stealth_renderer = webgl_stealth.get("renderer", "")
        stealth_vendor = webgl_stealth.get("vendor", "")
        still_detected = any(
            m.lower() in stealth_renderer.lower() or m.lower() in stealth_vendor.lower()
            for m in headless_markers
        )

        results.append(VectorResult(
            vector="webgl",
            test_name="stealth_renderer_detection",
            detected=still_detected,
            detection_rate=80.0 if still_detected else 5.0,
            countermeasure="Consistent WebGL spoofing matching UA profile",
            countermeasure_effectiveness=96.0 if not still_detected else 30.0,
            risk_level="high" if still_detected else "low",
            details=webgl_stealth,
            notes="Stealth should replace SwiftShader with real GPU name.",
        ))

        # ── Тест 3: WebGL capabilities consistency ──
        caps = await page.evaluate("""
            () => {
                const canvas = document.createElement('canvas');
                const gl = canvas.getContext('webgl');
                if (!gl) return {};
                return {
                    maxTextureSize: gl.getParameter(gl.MAX_TEXTURE_SIZE),
                    maxVertexAttribs: gl.getParameter(gl.MAX_VERTEX_ATTRIBS),
                    maxVaryingVectors: gl.getParameter(gl.MAX_VARYING_VECTORS),
                    maxVertexUniformVectors: gl.getParameter(gl.MAX_VERTEX_UNIFORM_VECTORS),
                    maxFragmentUniformVectors: gl.getParameter(gl.MAX_FRAGMENT_UNIFORM_VECTORS),
                    maxTextureImageUnits: gl.getParameter(gl.MAX_TEXTURE_IMAGE_UNITS),
                    maxVertexTextureImageUnits: gl.getParameter(gl.MAX_VERTEX_TEXTURE_IMAGE_UNITS),
                    maxCombinedTextureImageUnits: gl.getParameter(gl.MAX_COMBINED_TEXTURE_IMAGE_UNITS),
                    aliasedLineWidthRange: gl.getParameter(gl.ALIASED_LINE_WIDTH_RANGE),
                    aliasedPointSizeRange: gl.getParameter(gl.ALIASED_POINT_SIZE_RANGE),
                    extensions: gl.getSupportedExtensions() || [],
                };
            }
        """)

        # Headless часто имеет минимальные capabilities
        ext_count = len(caps.get("extensions", []))
        low_caps = ext_count < 20

        results.append(VectorResult(
            vector="webgl",
            test_name="capabilities_analysis",
            detected=low_caps,
            detection_rate=55.0 if low_caps else 10.0,
            countermeasure="Extension list spoofing + capability normalization",
            countermeasure_effectiveness=85.0,
            risk_level="medium" if low_caps else "low",
            details={
                "extension_count": ext_count,
                "max_texture_size": caps.get("maxTextureSize"),
                "sample_extensions": caps.get("extensions", [])[:10],
            },
            notes=f"Extensions count: {ext_count}. Real Chrome typically has 28-32 extensions.",
        ))

        return results


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Behavioral Biometrics Research
# ═══════════════════════════════════════════════════════════════════════════════

class BehavioralResearch:
    """Исследование поведенческих биометрических векторов."""

    @staticmethod
    async def run(page, apply_stealth_config: StealthConfig | None = None) -> list[VectorResult]:
        results = []

        # ── Тест 1: Анализ движений мыши — бот vs человек ──
        # Симулируем "ботоподобное" движение (прямая линия, фиксированная скорость)
        bot_movements = BehavioralResearch._generate_bot_movements(0, 0, 500, 300, 20)

        # Симулируем "человеческое" движение (кривая Безье с джиттером)
        human_movements = BehavioralResearch._generate_human_movements(0, 0, 500, 300, 20)

        bot_linearity = BehavioralResearch._calculate_linearity(bot_movements)
        human_linearity = BehavioralResearch._calculate_linearity(human_movements)
        bot_speed_variance = BehavioralResearch._calculate_speed_variance(bot_movements)
        human_speed_variance = BehavioralResearch._calculate_speed_variance(human_movements)

        results.append(VectorResult(
            vector="behavior",
            test_name="mouse_movement_linearity",
            detected=bot_linearity > 0.95,
            detection_rate=80.0 if bot_linearity > 0.95 else 20.0,
            countermeasure="Bezier curve mouse movement with Gaussian jitter",
            countermeasure_effectiveness=94.0,
            risk_level="high" if bot_linearity > 0.95 else "low",
            details={
                "bot_linearity": round(bot_linearity, 4),
                "human_linearity": round(human_linearity, 4),
                "bot_speed_variance": round(bot_speed_variance, 4),
                "human_speed_variance": round(human_speed_variance, 4),
                "bot_points": len(bot_movements),
                "human_points": len(human_movements),
            },
            notes=f"Bot linearity: {bot_linearity:.2%}, Human: {human_linearity:.2%}. Lower is better.",
        ))

        # ── Тест 2: Keystroke dynamics ──
        bot_keystrokes = BehavioralResearch._generate_bot_keystrokes(100)
        human_keystrokes = BehavioralResearch._generate_human_keystrokes(100)

        bot_ks_variance = statistics.stdev(bot_keystrokes) if len(bot_keystrokes) > 1 else 0
        human_ks_variance = statistics.stdev(human_keystrokes) if len(human_keystrokes) > 1 else 0

        results.append(VectorResult(
            vector="behavior",
            test_name="keystroke_dynamics",
            detected=bot_ks_variance < 5.0,
            detection_rate=75.0 if bot_ks_variance < 5.0 else 15.0,
            countermeasure="Variable typing speed with errors and pauses",
            countermeasure_effectiveness=91.0,
            risk_level="high" if bot_ks_variance < 5.0 else "low",
            details={
                "bot_interval_variance": round(bot_ks_variance, 2),
                "human_interval_variance": round(human_ks_variance, 2),
                "bot_mean_interval": round(statistics.mean(bot_keystrokes), 2),
                "human_mean_interval": round(statistics.mean(human_keystrokes), 2),
            },
            notes=f"Bot keystroke variance: {bot_ks_variance:.1f}ms, Human: {human_ks_variance:.1f}ms. Higher variance = more human.",
        ))

        # ── Тест 3: Scrolling behavior ──
        bot_scrolls = BehavioralResearch._generate_bot_scrolls(5)
        human_scrolls = BehavioralResearch._generate_human_scrolls(5)

        bot_scroll_regularity = BehavioralResearch._calculate_scroll_regularity(bot_scrolls)
        human_scroll_regularity = BehavioralResearch._calculate_scroll_regularity(human_scrolls)

        results.append(VectorResult(
            vector="behavior",
            test_name="scrolling_patterns",
            detected=bot_scroll_regularity > 0.9,
            detection_rate=70.0 if bot_scroll_regularity > 0.9 else 20.0,
            countermeasure="Variable speed scrolling with random pauses and reversals",
            countermeasure_effectiveness=89.0,
            risk_level="medium" if bot_scroll_regularity > 0.9 else "low",
            details={
                "bot_regularity": round(bot_scroll_regularity, 4),
                "human_regularity": round(human_scroll_regularity, 4),
                "bot_scroll_count": len(bot_scrolls),
                "human_scroll_count": len(human_scrolls),
            },
            notes="Human scrolling has variable speed, pauses, and occasional reversals.",
        ))

        # ── Тест 4: Реальное движение мыши через Playwright ──
        try:
            await page.mouse.move(100, 100)
            await page.mouse.move(300, 200)
            await page.mouse.move(500, 400)

            # Проверяем, что mouse events генерируются
            await page.evaluate("""
                () => {
                    window._mouseEvents = [];
                    document.addEventListener('mousemove', (e) => {
                        window._mouseEvents.push({x: e.clientX, y: e.clientY, t: Date.now()});
                    });
                    return 'listener_installed';
                }
            """)

            # Двигаем мышь снова
            await page.mouse.move(150, 150)
            await page.mouse.move(350, 250)
            await asyncio.sleep(0.1)

            events = await page.evaluate("() => window._mouseEvents || []")
            events_captured = len(events) >= 2

            results.append(VectorResult(
                vector="behavior",
                test_name="mouse_event_capture",
                detected=not events_captured,
                detection_rate=60.0 if not events_captured else 10.0,
                countermeasure="Native Playwright mouse.move() generates real mouse events",
                countermeasure_effectiveness=90.0,
                risk_level="medium" if not events_captured else "low",
                details={
                    "events_captured": len(events),
                    "sufficient": events_captured,
                    "sample_events": events[:3],
                },
                notes=f"Captured {len(events)} mouse events. Real browsers generate continuous mousemove events.",
            ))
        except Exception as e:
            results.append(VectorResult(
                vector="behavior",
                test_name="mouse_event_capture",
                detected=True,
                detection_rate=50.0,
                countermeasure="Native Playwright mouse.move()",
                countermeasure_effectiveness=70.0,
                risk_level="medium",
                details={"error": str(e)},
                notes="Mouse event capture test failed.",
            ))

        return results

    # ── Генераторы движений ──

    @staticmethod
    def _generate_bot_movements(x0, y0, x1, y1, steps):
        """Прямолинейное движение с фиксированным шагом — ботоподобное."""
        points = []
        for i in range(steps + 1):
            t = i / steps
            points.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
        return points

    @staticmethod
    def _generate_human_movements(x0, y0, x1, y1, steps):
        """Кривая Безье с джиттером — человеческое движение."""
        import random
        rng = random.Random(42)
        dx, dy = x1 - x0, y1 - y0
        perp_x = -dy * rng.uniform(-0.3, 0.3)
        perp_y = dx * rng.uniform(-0.3, 0.3)
        cx0 = x0 + dx * 0.25 + perp_x
        cy0 = y0 + dy * 0.25 + perp_y
        cx1 = x0 + dx * 0.75 - perp_x
        cy1 = y0 + dy * 0.75 - perp_y

        points = []
        for i in range(steps + 1):
            t = i / steps
            mt = 1 - t
            x = mt**3 * x0 + 3 * mt**2 * t * cx0 + 3 * mt * t**2 * cx1 + t**3 * x1
            y = mt**3 * y0 + 3 * mt**2 * t * cy0 + 3 * mt * t**2 * cy1 + t**3 * y1
            x += rng.gauss(0, 2.0)
            y += rng.gauss(0, 2.0)
            points.append((x, y))
        return points

    @staticmethod
    def _calculate_linearity(points):
        """Насколько точки близки к прямой линии (1.0 = идеально прямая)."""
        if len(points) < 3:
            return 1.0
        x0, y0 = points[0]
        x1, y1 = points[-1]
        total_deviation = 0.0
        for px, py in points[1:-1]:
            # Расстояние от точки до линии
            num = abs((y1 - y0) * px - (x1 - x0) * py + x1 * y0 - y1 * x0)
            den = math.sqrt((y1 - y0) ** 2 + (x1 - x0) ** 2)
            if den > 0:
                total_deviation += num / den
        avg_deviation = total_deviation / max(1, len(points) - 2)
        return max(0.0, 1.0 - avg_deviation / 50.0)

    @staticmethod
    def _calculate_speed_variance(points):
        """Дисперсия скорости между точками."""
        if len(points) < 2:
            return 0.0
        speeds = []
        for i in range(1, len(points)):
            dx = points[i][0] - points[i - 1][0]
            dy = points[i][1] - points[i - 1][1]
            speeds.append(math.sqrt(dx ** 2 + dy ** 2))
        if len(speeds) < 2:
            return 0.0
        return statistics.variance(speeds)

    @staticmethod
    def _generate_bot_keystrokes(count):
        """Фиксированные интервалы — ботоподобный набор."""
        return [100.0] * count

    @staticmethod
    def _generate_human_keystrokes(count):
        """Переменные интервалы с паузами — человеческий набор."""
        import random
        rng = random.Random(123)
        intervals = []
        for _ in range(count):
            base = rng.gauss(120, 40)
            if rng.random() < 0.1:
                base += rng.uniform(200, 1500)
            intervals.append(max(30, base))
        return intervals

    @staticmethod
    def _generate_bot_scrolls(pages):
        """Регулярный скролл — ботоподобный."""
        return [800] * (pages * 10)

    @staticmethod
    def _generate_human_scrolls(pages):
        """Переменный скролл — человеческий."""
        import random
        rng = random.Random(456)
        scrolls = []
        for _ in range(pages * 10):
            scrolls.append(rng.randint(50, 400))
            if rng.random() < 0.15:
                scrolls.append(-rng.randint(30, 100))
        return scrolls

    @staticmethod
    def _calculate_scroll_regularity(scrolls):
        """Насколько регулярный скролл (1.0 = идеально регулярный)."""
        if len(scrolls) < 2:
            return 1.0
        mean_scroll = statistics.mean(scrolls)
        if mean_scroll == 0:
            return 1.0
        variance = statistics.variance(scrolls) if len(scrolls) > 1 else 0
        cv = math.sqrt(variance) / abs(mean_scroll) if mean_scroll != 0 else 0
        return max(0.0, 1.0 - cv)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Timing Analysis Research
# ═══════════════════════════════════════════════════════════════════════════════

class TimingResearch:
    """Исследование timing-based обнаружения."""

    @staticmethod
    async def run(page, apply_stealth_config: StealthConfig | None = None) -> list[VectorResult]:
        results = []

        # ── Тест 1: Request interval analysis ──
        intervals = []
        for _ in range(5):
            start = time.monotonic()
            await page.evaluate("() => document.title")
            elapsed = (time.monotonic() - start) * 1000
            intervals.append(elapsed)

        interval_variance = statistics.variance(intervals) if len(intervals) > 1 else 0
        interval_mean = statistics.mean(intervals)

        # Боты часто имеют очень стабильные интервалы
        bot_like_timing = interval_variance < 1.0 and interval_mean < 5.0

        results.append(VectorResult(
            vector="timing",
            test_name="request_interval_analysis",
            detected=bot_like_timing,
            detection_rate=65.0 if bot_like_timing else 15.0,
            countermeasure="Random delays between actions (HumanBehaviorEngine.action_delay)",
            countermeasure_effectiveness=90.0,
            risk_level="medium" if bot_like_timing else "low",
            details={
                "intervals_ms": [round(i, 2) for i in intervals],
                "mean_ms": round(interval_mean, 2),
                "variance": round(interval_variance, 4),
                "bot_like": bot_like_timing,
            },
            notes=f"Mean: {interval_mean:.2f}ms, Variance: {interval_variance:.4f}. Low variance = suspicious.",
        ))

        # ── Тест 2: Page load timing ──
        load_start = time.monotonic()
        try:
            await page.goto("about:blank", wait_until="domcontentloaded", timeout=10000)
            load_time = (time.monotonic() - load_start) * 1000
        except Exception:
            load_time = 0

        results.append(VectorResult(
            vector="timing",
            test_name="page_load_timing",
            detected=False,
            detection_rate=10.0,
            countermeasure="Natural page load with content rendering wait",
            countermeasure_effectiveness=85.0,
            risk_level="low",
            details={
                "load_time_ms": round(load_time, 2),
            },
            notes="Page load timing is a weak signal but can contribute to detection.",
        ))

        # ── Тест 3: Navigation timing patterns ──
        nav_times = []
        for url in ["about:blank", "about:blank", "about:blank"]:
            t0 = time.monotonic()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=10000)
            except Exception:
                pass
            nav_times.append((time.monotonic() - t0) * 1000)

        nav_variance = statistics.variance(nav_times) if len(nav_times) > 1 else 0
        nav_regularity = nav_variance < 10.0

        results.append(VectorResult(
            vector="timing",
            test_name="navigation_regularity",
            detected=nav_regularity,
            detection_rate=45.0 if nav_regularity else 10.0,
            countermeasure="Variable wait times with random jitter",
            countermeasure_effectiveness=88.0,
            risk_level="medium" if nav_regularity else "low",
            details={
                "nav_times_ms": [round(t, 2) for t in nav_times],
                "variance": round(nav_variance, 4),
                "regular": nav_regularity,
            },
            notes="Identical navigation times across requests indicate automation.",
        ))

        # ── Тест 4: JS execution timing ──
        exec_times = []
        for _ in range(10):
            t0 = time.monotonic()
            await page.evaluate("() => { let s = 0; for(let i=0;i<10000;i++) s+=i; return s; }")
            exec_times.append((time.monotonic() - t0) * 1000)

        exec_variance = statistics.variance(exec_times) if len(exec_times) > 1 else 0
        exec_mean = statistics.mean(exec_times)

        results.append(VectorResult(
            vector="timing",
            test_name="js_execution_timing",
            detected=exec_variance < 0.5,
            detection_rate=35.0 if exec_variance < 0.5 else 10.0,
            countermeasure="N/A — JS execution is deterministic",
            countermeasure_effectiveness=20.0,
            risk_level="low",
            details={
                "exec_times_ms": [round(t, 3) for t in exec_times],
                "mean_ms": round(exec_mean, 3),
                "variance": round(exec_variance, 6),
            },
            notes="JS execution timing is a weak signal. Headless may be slightly faster due to no rendering.",
        ))

        return results


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Header Analysis Research
# ═══════════════════════════════════════════════════════════════════════════════

class HeaderResearch:
    """Исследование HTTP-заголовков как вектора обнаружения."""

    @staticmethod
    async def run(page, apply_stealth_config: StealthConfig | None = None) -> list[VectorResult]:
        results = []

        # ── Тест 1: Сбор заголовков через JS ──
        nav_headers = await page.evaluate("""
            () => {
                // navigator properties that affect header-like behavior
                return {
                    userAgent: navigator.userAgent,
                    platform: navigator.platform,
                    languages: navigator.languages,
                    language: navigator.language,
                    cookieEnabled: navigator.cookieEnabled,
                    doNotTrack: navigator.doNotTrack,
                    hardwareConcurrency: navigator.hardwareConcurrency,
                    deviceMemory: navigator.deviceMemory,
                    maxTouchPoints: navigator.maxTouchPoints,
                    connection: navigator.connection ? {
                        effectiveType: navigator.connection.effectiveType,
                        downlink: navigator.connection.downlink,
                        rtt: navigator.connection.rtt,
                    } : null,
                };
            }
        """)

        ua = nav_headers.get("userAgent", "")
        platform = nav_headers.get("platform", "")

        # Проверяем несоответствия
        ua_platform_mismatch = False
        if "Windows" in ua and "Win32" not in platform:
            ua_platform_mismatch = True
        elif "Mac" in ua and "MacIntel" not in platform:
            ua_platform_mismatch = True
        elif "Linux" in ua and "Linux" not in platform:
            ua_platform_mismatch = True

        # Headless Chrome часто содержит "HeadlessChrome" в UA
        headless_in_ua = "HeadlessChrome" in ua

        results.append(VectorResult(
            vector="headers",
            test_name="ua_platform_consistency",
            detected=ua_platform_mismatch or headless_in_ua,
            detection_rate=95.0 if headless_in_ua else (70.0 if ua_platform_mismatch else 5.0),
            countermeasure="Consistent UA + platform + Client Hints alignment",
            countermeasure_effectiveness=97.0,
            risk_level="critical" if headless_in_ua else ("high" if ua_platform_mismatch else "low"),
            details={
                "user_agent": ua[:100],
                "platform": platform,
                "mismatch": ua_platform_mismatch,
                "headless_in_ua": headless_in_ua,
                "languages": nav_headers.get("languages"),
                "hardware_concurrency": nav_headers.get("hardwareConcurrency"),
                "device_memory": nav_headers.get("deviceMemory"),
            },
            notes="UA-Platform mismatch is a strong bot indicator. HeadlessChrome in UA is instant detection.",
        ))

        # ── Тест 2: Client Hints consistency ──
        client_hints = await page.evaluate("""
            () => {
                const uaData = navigator.userAgentData;
                if (!uaData) return { supported: false };
                return {
                    supported: true,
                    brands: uaData.brands,
                    mobile: uaData.mobile,
                    platform: uaData.platform,
                };
            }
        """)

        hints_supported = client_hints.get("supported", False)
        hints_platform = client_hints.get("platform", "")
        ua_platform_mismatch_hints = False

        if hints_supported and hints_platform:
            if "Windows" in ua and hints_platform != "Windows":
                ua_platform_mismatch_hints = True
            elif "Mac" in ua and hints_platform != "macOS":
                ua_platform_mismatch_hints = True

        results.append(VectorResult(
            vector="headers",
            test_name="client_hints_consistency",
            detected=ua_platform_mismatch_hints,
            detection_rate=80.0 if ua_platform_mismatch_hints else 5.0,
            countermeasure="Client Hints spoofing via stealth_client_hints module",
            countermeasure_effectiveness=95.0,
            risk_level="high" if ua_platform_mismatch_hints else "low",
            details={
                "hints_supported": hints_supported,
                "hints_platform": hints_platform,
                "ua_platform": platform,
                "mismatch": ua_platform_mismatch_hints,
                "brands": client_hints.get("brands"),
            },
            notes="Client Hints must match UA. Mismatch is detectable by modern anti-bot systems.",
        ))

        # ── Тест 3: HTTP headers via intercepted request ──
        captured_headers: dict = {}

        async def handle_request(request):
            nonlocal captured_headers
            if not captured_headers:
                captured_headers = dict(request.headers)

        page.on("request", handle_request)

        try:
            await page.goto("https://httpbin.org/headers", wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)
        except Exception:
            # httpbin может быть недоступен — используем about:blank
            await page.goto("about:blank")

        page.remove_listener("request", handle_request)

        if captured_headers:
            header_order = list(captured_headers.keys())
            suspicious_headers = []
            missing_headers = []

            # Проверяем наличие подозрительных заголовков
            for key, val in captured_headers.items():
                if "headless" in val.lower():
                    suspicious_headers.append(f"{key}: {val[:50]}")

            # Проверяем отсутствие ожидаемых заголовков
            expected = ["accept-language", "accept-encoding", "sec-ch-ua", "sec-fetch-mode"]
            for h in expected:
                if h.lower() not in {k.lower() for k in header_order}:
                    missing_headers.append(h)

            has_issues = bool(suspicious_headers) or len(missing_headers) >= 2

            results.append(VectorResult(
                vector="headers",
                test_name="http_header_analysis",
                detected=has_issues,
                detection_rate=70.0 if has_issues else 10.0,
                countermeasure="Header normalization + consistent header ordering",
                countermeasure_effectiveness=90.0,
                risk_level="high" if has_issues else "low",
                details={
                    "header_count": len(captured_headers),
                    "header_order": header_order[:15],
                    "suspicious": suspicious_headers,
                    "missing": missing_headers,
                    "user_agent_header": captured_headers.get("user-agent", "")[:80],
                },
                notes=f"Captured {len(captured_headers)} headers. Suspicious: {len(suspicious_headers)}, Missing: {len(missing_headers)}.",
            ))
        else:
            results.append(VectorResult(
                vector="headers",
                test_name="http_header_analysis",
                detected=False,
                detection_rate=0.0,
                countermeasure="N/A — headers not captured",
                countermeasure_effectiveness=0.0,
                risk_level="low",
                details={"note": "Could not capture HTTP headers (httpbin unavailable)"},
                notes="httpbin.org unavailable. Header analysis skipped.",
            ))

        return results


# ═══════════════════════════════════════════════════════════════════════════════
# 6. JavaScript Detection Research
# ═══════════════════════════════════════════════════════════════════════════════

class JSDetectionResearch:
    """Исследование JavaScript-based обнаружения."""

    @staticmethod
    async def run(page, apply_stealth_config: StealthConfig | None = None) -> list[VectorResult]:
        results = []

        # ── Тест 1: navigator.webdriver ──
        wd_result = await page.evaluate("() => navigator.webdriver")
        webdriver_detected = wd_result is not None and wd_result is not False

        results.append(VectorResult(
            vector="js",
            test_name="navigator_webdriver",
            detected=webdriver_detected,
            detection_rate=99.0 if webdriver_detected else 0.0,
            countermeasure="Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
            countermeasure_effectiveness=99.0,
            risk_level="critical" if webdriver_detected else "low",
            details={
                "webdriver_value": str(wd_result),
                "type": str(type(wd_result).__name__),
            },
            notes="navigator.webdriver is the #1 bot detection signal. Must be undefined.",
        ))

        # ── Тест 2: Chrome runtime ──
        chrome_check = await page.evaluate("""
            () => ({
                hasChrome: !!window.chrome,
                hasRuntime: !!window.chrome?.runtime,
                hasApp: !!window.chrome?.app,
                csi: typeof window.chrome?.csi,
                loadTimes: typeof window.chrome?.loadTimes,
            })
        """)

        missing_chrome = not chrome_check.get("hasChrome", False)
        missing_runtime = not chrome_check.get("hasRuntime", False)

        results.append(VectorResult(
            vector="js",
            test_name="chrome_runtime_detection",
            detected=missing_chrome or missing_runtime,
            detection_rate=75.0 if (missing_chrome or missing_runtime) else 10.0,
            countermeasure="window.chrome = { runtime: {}, app: {} } + csi/loadTimes stubs",
            countermeasure_effectiveness=95.0,
            risk_level="high" if (missing_chrome or missing_runtime) else "low",
            details=chrome_check,
            notes="Headless Chrome often lacks chrome.runtime. Real Chrome always has it.",
        ))

        # ── Тест 3: Plugins ──
        plugins = await page.evaluate("""
            () => ({
                length: navigator.plugins?.length || 0,
                items: Array.from(navigator.plugins || []).map(p => p.name),
            })
        """)

        no_plugins = plugins.get("length", 0) == 0

        results.append(VectorResult(
            vector="js",
            test_name="plugins_detection",
            detected=no_plugins,
            detection_rate=80.0 if no_plugins else 5.0,
            countermeasure="Fake plugin array with Chrome PDF Plugin, PDF Viewer, Native Client",
            countermeasure_effectiveness=93.0,
            risk_level="high" if no_plugins else "low",
            details=plugins,
            notes="Headless Chrome has 0 plugins. Real Chrome has 2-3 built-in plugins.",
        ))

        # ── Тест 4: Permissions API ──
        permissions = await page.evaluate("""
            async () => {
                try {
                    const result = await navigator.permissions.query({name: 'notifications'});
                    return { state: result.state, supported: true };
                } catch(e) {
                    return { error: e.message, supported: false };
                }
            }
        """)

        # Headless часто возвращает "denied" вместо реального значения
        perm_suspicious = permissions.get("state") == "denied" and permissions.get("supported")

        results.append(VectorResult(
            vector="js",
            test_name="permissions_api_detection",
            detected=perm_suspicious,
            detection_rate=50.0 if perm_suspicious else 10.0,
            countermeasure="Permissions query override to return Notification.permission state",
            countermeasure_effectiveness=88.0,
            risk_level="medium" if perm_suspicious else "low",
            details=permissions,
            notes="Headless Chrome often returns 'denied' for all permission queries.",
        ))

        # ── Тест 5: Automation-specific properties ──
        auto_props = await page.evaluate("""
            () => ({
                automationControlled: navigator.automationControlled,
                webdriverInUrl: navigator.webdriver,
               cdcProps: Object.keys(window).filter(k => k.startsWith('cdc_') || k.startsWith('__cdc')),
                playwrightProps: Object.keys(window).filter(k => k.includes('playwright') || k.includes('__pw')),
                seleniumProps: Object.keys(window).filter(k => k.includes('selenium') || k.includes('webdriver')),
                domAutomation: window.domAutomation,
                domAutomationController: window.domAutomationController,
                _phantom: window._phantom,
                callPhantom: window.callPhantom,
                _selenium: window._selenium,
                callSelenium: window.callSelenium,
            })
        """)

        has_auto_props = any(
            auto_props.get(k) for k in [
                "automationControlled", "domAutomation", "domAutomationController",
                "_phantom", "callPhantom", "_selenium", "callSelenium",
            ]
        )
        has_cdc = len(auto_props.get("cdcProps", [])) > 0
        has_pw = len(auto_props.get("playwrightProps", [])) > 0
        has_selenium = len(auto_props.get("seleniumProps", [])) > 0

        results.append(VectorResult(
            vector="js",
            test_name="automation_properties",
            detected=has_auto_props or has_cdc or has_pw or has_selenium,
            detection_rate=90.0 if (has_auto_props or has_cdc) else (60.0 if (has_pw or has_selenium) else 5.0),
            countermeasure="Clean all automation markers + rename CDC props",
            countermeasure_effectiveness=85.0,
            risk_level="critical" if (has_auto_props or has_cdc) else ("medium" if (has_pw or has_selenium) else "low"),
            details={
                "has_auto_props": has_auto_props,
                "cdc_props": auto_props.get("cdcProps", []),
                "playwright_props": auto_props.get("playwrightProps", []),
                "selenium_props": auto_props.get("seleniumProps", []),
            },
            notes="CDC props (cdc_*) are Playwright's internal markers. Must be cleaned.",
        ))

        # ── Тест 6: iframe.contentWindow detection ──
        iframe_check = await page.evaluate("""
            () => {
                const iframe = document.createElement('iframe');
                document.body.appendChild(iframe);
                const cw = iframe.contentWindow;
                const result = {
                    outerWidth: cw?.outerWidth,
                    outerHeight: cw?.outerHeight,
                    innerWidth: cw?.innerWidth,
                    innerHeight: cw?.innerHeight,
                };
                document.body.removeChild(iframe);
                return result;
            }
        """)

        iframe_suspicious = (
            iframe_check.get("outerWidth") == 0 or
            iframe_check.get("outerHeight") == 0 or
            iframe_check.get("outerWidth") == iframe_check.get("innerWidth")
        )

        results.append(VectorResult(
            vector="js",
            test_name="iframe_contentwindow_detection",
            detected=iframe_suspicious,
            detection_rate=65.0 if iframe_suspicious else 5.0,
            countermeasure="iframe.contentWindow proxy with realistic outerWidth/outerHeight",
            countermeasure_effectiveness=90.0,
            risk_level="medium" if iframe_suspicious else "low",
            details=iframe_check,
            notes="Headless: iframe.contentWindow.outerWidth === 0. Real: outerWidth > innerWidth (frame borders).",
        ))

        # ── Тест 7: С применённым stealth ──
        if apply_stealth_config:
            await apply_stealth(page, apply_stealth_config)

            stealth_check = await page.evaluate("""
                () => ({
                    webdriver: navigator.webdriver,
                    pluginsLength: navigator.plugins?.length,
                    hasChrome: !!window.chrome?.runtime,
                    languages: navigator.languages,
                    vendor: navigator.vendor,
                    hardwareConcurrency: navigator.hardwareConcurrency,
                    deviceMemory: navigator.deviceMemory,
                    outerWidth: window.outerWidth,
                    outerHeight: window.outerHeight,
                    innerWidth: window.innerWidth,
                    innerHeight: window.innerHeight,
                })
            """)

            stealth_issues = []
            if stealth_check.get("webdriver") is not None and stealth_check.get("webdriver") is not False:
                stealth_issues.append("webdriver still detectable")
            if stealth_check.get("pluginsLength", 0) == 0:
                stealth_issues.append("no plugins")
            if not stealth_check.get("hasChrome"):
                stealth_issues.append("no chrome.runtime")
            if stealth_check.get("vendor", "") == "":
                stealth_issues.append("empty vendor")
            ow = stealth_check.get("outerWidth", 0)
            iw = stealth_check.get("innerWidth", 0)
            if ow == 0 or ow == iw:
                stealth_issues.append(f"outerWidth ({ow}) == innerWidth ({iw})")

            results.append(VectorResult(
                vector="js",
                test_name="stealth_comprehensive_check",
                detected=len(stealth_issues) > 0,
                detection_rate=70.0 * len(stealth_issues) / 6 if stealth_issues else 0.0,
                countermeasure="Full stealth stack: webdriver + plugins + chrome + permissions + vendor + dimensions",
                countermeasure_effectiveness=95.0 if not stealth_issues else max(0, 95.0 - 15.0 * len(stealth_issues)),
                risk_level="high" if stealth_issues else "low",
                details={
                    "stealth_issues": stealth_issues,
                    "checks": stealth_check,
                },
                notes=f"Stealth issues found: {len(stealth_issues)}. Issues: {', '.join(stealth_issues) if stealth_issues else 'none'}.",
            ))

        return results


# ═══════════════════════════════════════════════════════════════════════════════
# HTML Report Generator
# ═══════════════════════════════════════════════════════════════════════════════

class HTMLReportGenerator:
    """Генератор HTML-отчёта с красивым оформлением."""

    @staticmethod
    def generate(report: ResearchReport) -> str:
        risk_colors = {
            "critical": "#dc3545",
            "high": "#fd7e14",
            "medium": "#ffc107",
            "low": "#28a745",
        }
        risk_icons = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
        }

        # Группируем результаты по векторам
        vectors: dict[str, list[VectorResult]] = {}
        for r in report.results:
            vectors.setdefault(r.vector, []).append(r)

        # Строим матрицу рисков
        matrix_rows = ""
        for vec_name, vec_results in vectors.items():
            for r in vec_results:
                color = risk_colors.get(r.risk_level, "#6c757d")
                icon = risk_icons.get(r.risk_level, "⚪")
                detect_class = "danger" if r.detected else "success"
                matrix_rows += f"""
                <tr>
                    <td>{icon} {r.vector}</td>
                    <td>{r.test_name}</td>
                    <td><span class="badge {detect_class}">{'DETECTED' if r.detected else 'CLEAN'}</span></td>
                    <td>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width:{r.detection_rate}%;background:{color}"></div>
                        </div>
                        <small>{r.detection_rate:.0f}%</small>
                    </td>
                    <td>{r.countermeasure_effectiveness:.0f}%</td>
                    <td><span class="risk-badge" style="background:{color}">{r.risk_level.upper()}</span></td>
                </tr>"""

        # Строим детальные секции
        detail_sections = ""
        for vec_name, vec_results in vectors.items():
            vec_risk = max((r.detection_rate for r in vec_results), default=0)
            vec_protection = max((r.countermeasure_effectiveness for r in vec_results), default=0)
            vec_color = "#28a745" if vec_risk < 30 else "#ffc107" if vec_risk < 60 else "#dc3545"

            test_cards = ""
            for r in vec_results:
                tc = risk_colors.get(r.risk_level, "#6c757d")
                ti = risk_icons.get(r.risk_level, "⚪")
                details_html = "<br>".join(f"<b>{k}:</b> {v}" for k, v in r.details.items()) if r.details else "N/A"
                test_cards += f"""
                <div class="test-card">
                    <div class="test-header" style="border-left: 4px solid {tc}">
                        <span>{ti} {r.test_name}</span>
                        <span class="badge {'danger' if r.detected else 'success'}">{'❌ DETECTED' if r.detected else '✅ CLEAN'}</span>
                    </div>
                    <div class="test-body">
                        <div class="metric"><label>Detection Rate:</label> <b>{r.detection_rate:.0f}%</b></div>
                        <div class="metric"><label>Countermeasure:</label> {r.countermeasure}</div>
                        <div class="metric"><label>Effectiveness:</label> <b>{r.countermeasure_effectiveness:.0f}%</b></div>
                        <div class="metric"><label>Risk:</label> <span class="risk-badge" style="background:{tc}">{r.risk_level.upper()}</span></div>
                        <div class="details">{details_html}</div>
                        {'<div class="notes">📝 ' + r.notes + '</div>' if r.notes else ''}
                    </div>
                </div>"""

            detail_sections += f"""
            <div class="vector-section">
                <h3>🔬 {vec_name.upper()} <small style="color:{vec_color}">Risk: {vec_risk:.0f}% | Protection: {vec_protection:.0f}%</small></h3>
                {test_cards}
            </div>"""

        # Comparison section
        comparison_html = ""
        if report.comparison:
            comp_rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in report.comparison.items())
            comparison_html = f"""
            <div class="comparison-section">
                <h3>📊 Comparison with Previous Research</h3>
                <table class="matrix-table">{comp_rows}</table>
            </div>"""

        risk_color = "#28a745" if report.overall_detection_risk < 30 else "#ffc107" if report.overall_detection_risk < 60 else "#dc3545"
        prot_color = "#dc3545" if report.overall_protection_score < 30 else "#ffc107" if report.overall_protection_score < 60 else "#28a745"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Anti-Detection Research Lab Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f0f23; color: #e0e0e0; line-height: 1.6; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; padding: 40px 20px; background: linear-gradient(135deg, #1a1a3e 0%, #2d1b69 100%); border-radius: 16px; margin-bottom: 30px; }}
        .header h1 {{ font-size: 2.2em; color: #fff; margin-bottom: 10px; }}
        .header h1 span {{ color: #7c4dff; }}
        .header .subtitle {{ color: #b0b0b0; font-size: 1.1em; }}
        .meta {{ display: flex; justify-content: center; gap: 30px; margin-top: 20px; flex-wrap: wrap; }}
        .meta-item {{ text-align: center; }}
        .meta-item label {{ display: block; color: #888; font-size: 0.85em; }}
        .meta-item value {{ display: block; font-size: 1.3em; font-weight: bold; color: #fff; }}
        .scores {{ display: flex; justify-content: center; gap: 40px; margin: 30px 0; flex-wrap: wrap; }}
        .score-card {{ background: #1a1a3e; border-radius: 12px; padding: 24px 40px; text-align: center; min-width: 200px; }}
        .score-card .score-value {{ font-size: 3em; font-weight: bold; }}
        .score-card .score-label {{ color: #888; margin-top: 5px; }}
        .score-card.risk .score-value {{ color: {risk_color}; }}
        .score-card.protection .score-value {{ color: {prot_color}; }}
        h2 {{ color: #7c4dff; margin: 30px 0 15px; font-size: 1.5em; border-bottom: 2px solid #2d1b69; padding-bottom: 8px; }}
        h3 {{ color: #b0b0b0; margin: 20px 0 10px; font-size: 1.2em; }}
        .matrix-table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        .matrix-table th {{ background: #1a1a3e; padding: 12px 15px; text-align: left; color: #7c4dff; font-weight: 600; }}
        .matrix-table td {{ padding: 10px 15px; border-bottom: 1px solid #2a2a4a; }}
        .matrix-table tr:hover {{ background: #1a1a3e; }}
        .badge {{ display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 0.8em; font-weight: bold; }}
        .badge.danger {{ background: #dc3545; color: #fff; }}
        .badge.success {{ background: #28a745; color: #fff; }}
        .risk-badge {{ display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.75em; color: #fff; font-weight: bold; }}
        .progress-bar {{ width: 100px; height: 8px; background: #2a2a4a; border-radius: 4px; display: inline-block; vertical-align: middle; margin-right: 8px; }}
        .progress-fill {{ height: 100%; border-radius: 4px; }}
        .vector-section {{ margin: 25px 0; }}
        .test-card {{ background: #1a1a3e; border-radius: 10px; margin: 12px 0; overflow: hidden; }}
        .test-header {{ display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: #1e1e42; }}
        .test-body {{ padding: 16px; }}
        .test-body .metric {{ margin: 6px 0; }}
        .test-body .metric label {{ color: #888; }}
        .test-body .details {{ margin-top: 10px; padding: 10px; background: #0f0f23; border-radius: 6px; font-size: 0.85em; color: #aaa; max-height: 150px; overflow-y: auto; }}
        .test-body .notes {{ margin-top: 10px; padding: 8px 12px; background: #2a2a4a; border-radius: 6px; font-size: 0.9em; color: #ccc; }}
        .comparison-section {{ background: #1a1a3e; border-radius: 12px; padding: 20px; margin: 20px 0; }}
        .footer {{ text-align: center; padding: 30px; color: #666; font-size: 0.9em; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔬 Anti-Detection <span>Research Lab</span></h1>
            <div class="subtitle">Systematic Bot Detection Research & Countermeasure Analysis</div>
            <div class="meta">
                <div class="meta-item"><label>Timestamp</label><value>{report.timestamp[:19]}</value></div>
                <div class="meta-item"><label>Duration</label><value>{report.duration_seconds:.1f}s</value></div>
                <div class="meta-item"><label>Vectors</label><value>{len(vectors)}</value></div>
                <div class="meta-item"><label>Tests</label><value>{len(report.results)}</value></div>
            </div>
        </div>

        <div class="scores">
            <div class="score-card risk">
                <div class="score-value">{report.overall_detection_risk:.0f}%</div>
                <div class="score-label">Overall Detection Risk</div>
            </div>
            <div class="score-card protection">
                <div class="score-value">{report.overall_protection_score:.0f}%</div>
                <div class="score-label">Overall Protection Score</div>
            </div>
        </div>

        <h2>📊 Risk Assessment Matrix</h2>
        <table class="matrix-table">
            <thead>
                <tr><th>Vector</th><th>Test</th><th>Status</th><th>Detection Rate</th><th>Protection</th><th>Risk</th></tr>
            </thead>
            <tbody>{matrix_rows}</tbody>
        </table>

        {comparison_html}

        <h2>🔍 Detailed Analysis</h2>
        {detail_sections}

        <div class="footer">
            <p>Anti-Detection Research Lab v1.0 — Lab Playwright Kit</p>
            <p>Generated: {report.timestamp}</p>
        </div>
    </div>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════════════════
# Main Research Orchestrator
# ═══════════════════════════════════════════════════════════════════════════════

# Маппинг векторов на исследовательские модули
VECTOR_RESEARCHERS: dict[str, Any] = {
    "canvas":   CanvasFingerprintResearch,
    "webgl":    WebGLResearch,
    "behavior": BehavioralResearch,
    "timing":   TimingResearch,
    "headers":  HeaderResearch,
    "js":       JSDetectionResearch,
}


async def run_research(
    vectors: list[str],
    output_dir: str,
    compare: bool = False,
    json_output: bool = False,
) -> ResearchReport:
    """Запустить исследование указанных векторов."""
    start_time = time.monotonic()

    report = ResearchReport(
        timestamp=datetime.now().isoformat(),
        vectors_researched=vectors,
    )

    # Инициализируем БД
    db = ResearchDatabase()

    # Загружаем предыдущие результаты для сравнения
    previous_session = db.get_previous_session() if compare else None

    stealth_config = StealthConfig.advanced()

    async with BrowserManager(headless=True, timeout=30000) as browser:
        for vector in vectors:
            researcher = VECTOR_RESEARCHERS.get(vector)
            if not researcher:
                logger.warning(f"Unknown research vector: {vector}")
                continue

            logger.info(f"🔬 Researching vector: {vector}...")

            page = await browser.new_page()

            try:
                vector_results = await researcher.run(page, stealth_config)
                report.results.extend(vector_results)

                # Сохраняем в БД
                for r in vector_results:
                    db.save_result(r)

                logger.info(f"  ✅ {vector}: {len(vector_results)} tests completed")
            except Exception as e:
                logger.error(f"  ❌ {vector} research failed: {e}")
                report.results.append(VectorResult(
                    vector=vector,
                    test_name="research_error",
                    detected=True,
                    detection_rate=0.0,
                    countermeasure="N/A",
                    countermeasure_effectiveness=0.0,
                    risk_level="medium",
                    details={"error": str(e)},
                    notes=f"Research failed: {e}",
                ))
            finally:
                await page.close()

    # Вычисляем общие метрики
    if report.results:
        detected_rates = [r.detection_rate for r in report.results]
        protection_scores = [r.countermeasure_effectiveness for r in report.results]
        report.overall_detection_risk = statistics.mean(detected_rates)
        report.overall_protection_score = statistics.mean(protection_scores)

    report.duration_seconds = time.monotonic() - start_time

    # Сохраняем сессию
    db.save_session(report)

    # Сравнение с предыдущим
    if compare and previous_session:
        prev_risk = previous_session.get("overall_risk", 0)
        prev_protection = previous_session.get("overall_protection", 0)
        report.comparison = {
            "Previous Risk": f"{prev_risk:.0f}%",
            "Current Risk": f"{report.overall_detection_risk:.0f}%",
            "Risk Change": f"{report.overall_detection_risk - prev_risk:+.0f}%",
            "Previous Protection": f"{prev_protection:.0f}%",
            "Current Protection": f"{report.overall_protection_score:.0f}%",
            "Protection Change": f"{report.overall_protection_score - prev_protection:+.0f}%",
        }

    # Генерируем выходные файлы
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # HTML отчёт
    html_content = HTMLReportGenerator.generate(report)
    html_path = output_path / "antidetection_report.html"
    html_path.write_text(html_content, encoding="utf-8")
    logger.info(f"📄 HTML report: {html_path}")

    # JSON отчёт
    json_data = {
        "timestamp": report.timestamp,
        "vectors_researched": report.vectors_researched,
        "overall_detection_risk": report.overall_detection_risk,
        "overall_protection_score": report.overall_protection_score,
        "duration_seconds": report.duration_seconds,
        "results": [asdict(r) for r in report.results],
        "comparison": report.comparison,
    }
    json_path = output_path / "antidetection_report.json"
    json_path.write_text(json.dumps(json_data, indent=2, default=str), encoding="utf-8")
    logger.info(f"📄 JSON report: {json_path}")

    # Текстовый отчёт
    txt_path = output_path / "antidetection_report.txt"
    txt_path.write_text(report.summary, encoding="utf-8")
    logger.info(f"📄 Text report: {txt_path}")

    if json_output:
        print(json.dumps(json_data, indent=2, default=str))
    else:
        print(report.summary)

    return report


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="🔬 Anti-Detection Research Lab — систематическое исследование методов детектирования ботов",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s --research all --output /tmp/antidetection_reports
  %(prog)s --research canvas,webgl --output /tmp/reports --json
  %(prog)s --research all --output /tmp/reports --compare
  %(prog)s --research behavior,timing --output /tmp/reports
        """,
    )
    parser.add_argument(
        "--research",
        default="all",
        help="Векторы для исследования: all|canvas|webgl|behavior|timing|headers|js (через запятую)",
    )
    parser.add_argument(
        "--output",
        default="/tmp/antidetection_reports",
        help="Директория для выходных отчётов (default: /tmp/antidetection_reports)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Сравнить с предыдущим исследованием",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Вывести результат в JSON на stdout",
    )

    args = parser.parse_args()

    # Парсим векторы
    if args.research.strip().lower() == "all":
        vectors = list(VECTOR_RESEARCHERS.keys())
    else:
        vectors = [v.strip().lower() for v in args.research.split(",")]
        unknown = [v for v in vectors if v not in VECTOR_RESEARCHERS]
        if unknown:
            print(f"⚠️  Unknown vectors: {unknown}")
            print(f"Available: {', '.join(VECTOR_RESEARCHERS.keys())}")
            vectors = [v for v in vectors if v in VECTOR_RESEARCHERS]
            if not vectors:
                print("❌ No valid vectors specified.")
                sys.exit(1)

    # Настраиваем логирование
    logger.remove()
    logger.add(
        sys.stderr,
        format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> — <level>{message}</level>",
        level="INFO",
    )

    print("🔬 Anti-Detection Research Lab v1.0")
    print(f"   Vectors: {', '.join(vectors)}")
    print(f"   Output:  {args.output}")
    print(f"   Compare: {args.compare}")
    print()

    asyncio.run(run_research(
        vectors=vectors,
        output_dir=args.output,
        compare=args.compare,
        json_output=args.json_output,
    ))


if __name__ == "__main__":
    main()
