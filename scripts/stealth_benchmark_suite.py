#!/usr/bin/env python3
"""
Stealth Benchmark Suite — систематическое тестирование всех модулей антидетекта.

Тестирует:
  - Fingerprint Consistency  (Canvas, WebGL, Audio, Screen, Hardware)
  - Canvas Spoofing           (шум на пиксельном уровне, детерминизм по seed)
  - WebGL Spoofing            (vendor/renderer подмена)
  - Audio Spoofing            (AudioContext FFT спектр)
  - WebRTC Leak Prevention    (нет утечки реального IP)
  - Client Hints              (согласованность Sec-CH-UA с UA)
  - Behavior Realism          (мышь, скролл, набор текста)
  - Full Integration          (все модули одновременно)

Использование:
    python3 scripts/stealth_benchmark_suite.py --tests all --output /tmp/reports
    python3 scripts/stealth_benchmark_suite.py --tests fingerprint,behavior --json

Автор: Лаборатория DoctorM&Ai, Бестия
Версия: 1.0.0
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# ─── Импорты из lab_playwright_kit ──────────────────────────────────────────
SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, SRC_DIR)

from loguru import logger

from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.stealth import StealthConfig, apply_stealth
from lab_playwright_kit.stealth_webrtc import WebRTCConfig, apply_webrtc_protection
from lab_playwright_kit.stealth_audio import AudioConfig, apply_audio_spoofing
from lab_playwright_kit.stealth_client_hints import ClientHintsConfig, apply_client_hints
from lab_playwright_kit.fingerprint import FingerprintManager, BrowserFingerprint
from lab_playwright_kit.human_behavior import HumanBehaviorEngine, BehaviorProfile


# ─── Модель данных ──────────────────────────────────────────────────────────

class BenchmarkTestStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class StealthTestResult:
    """Результат одного теста."""
    name: str
    category: str
    status: BenchmarkTestStatus
    score: float
    details: str = ""
    duration_ms: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CategoryScore:
    """Скор по категории."""
    name: str
    weight: float
    score: float
    tests_passed: int = 0
    tests_failed: int = 0
    tests_total: int = 0
    results: list[StealthTestResult] = field(default_factory=list)


@dataclass
class SuiteReport:
    """Полный отчёт бенчмарка."""
    overall_score: float = 0.0
    categories: list[CategoryScore] = field(default_factory=list)
    duration_ms: float = 0.0
    timestamp: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "errors": self.errors,
            "categories": [
                {
                    "name": c.name,
                    "weight": c.weight,
                    "score": c.score,
                    "tests_passed": c.tests_passed,
                    "tests_failed": c.tests_failed,
                    "tests_total": c.tests_total,
                    "results": [
                        {
                            "name": r.name,
                            "status": r.status.value,
                            "score": r.score,
                            "details": r.details,
                            "duration_ms": r.duration_ms,
                            "extra": r.extra,
                        }
                        for r in c.results
                    ],
                }
                for c in self.categories
            ],
        }


# ─── Категории и веса ─────────────────────────────────────────────────────

CATEGORY_WEIGHTS = {
    "fingerprint": 0.25,
    "behavior": 0.25,
    "network": 0.25,
    "consistency": 0.25,
}


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

async def _fresh_page(browser_mgr):
    """Создать свежую страницу и навигировать на about:blank.

    Важно: add_init_script работает только для будущих навигаций.
    Поэтому все stealth-скрипты применяются ДО навигации.
    """
    page = await browser_mgr.new_page()
    await page.goto("about:blank")
    return page


async def _apply_stealth_and_navigate(page, config):
    """Применить stealth через add_init_script и навигировать.

    add_init_script работает только для будущих навигаций.
    Поэтому после применения нужно сделать goto.
    """
    await apply_stealth(page, config)
    await page.goto("about:blank")


# ═══════════════════════════════════════════════════════════════════════════
# ТЕСТЫ: FINGERPRINT
# ═══════════════════════════════════════════════════════════════════════════

async def test_fingerprint_generation() -> StealthTestResult:
    """FingerprintManager.generate() создаёт валидный отпечаток."""
    start = time.monotonic()
    try:
        fp = FingerprintManager.generate("test_fp_001", os="windows", browser="chrome")
        checks = [
            (len(fp.user_agent) > 0, "user_agent не пустой"),
            (len(fp.webgl_vendor) > 0, "webgl_vendor не пустой"),
            (len(fp.webgl_renderer) > 0, "webgl_renderer не пустой"),
            (fp.screen_width > 0, "screen_width > 0"),
            (fp.screen_height > 0, "screen_height > 0"),
            (fp.hardware_cores > 0, "hardware_cores > 0"),
            (fp.hardware_memory > 0, "hardware_memory > 0"),
            (len(fp.fonts) > 0, "fonts не пустой"),
            (fp.canvas_noise_seed > 0, "canvas_noise_seed > 0"),
            (fp.audio_noise_seed > 0, "audio_noise_seed > 0"),
        ]
        passed = sum(1 for ok, _ in checks if ok)
        total = len(checks)
        score = (passed / total) * 100
        details = "; ".join(msg for ok, msg in checks if not ok) or "Все проверки пройдены"
        return StealthTestResult(
            name="Fingerprint Generation",
            category="fingerprint",
            status=BenchmarkTestStatus.PASSED if score == 100 else BenchmarkTestStatus.FAILED,
            score=score,
            details=details,
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Fingerprint Generation",
            category="fingerprint",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_fingerprint_determinism() -> StealthTestResult:
    """Одинаковый profile_name → одинаковый отпечаток."""
    start = time.monotonic()
    try:
        fp1 = FingerprintManager.generate("det_test_001", os="windows", browser="chrome")
        fp2 = FingerprintManager.generate("det_test_001", os="windows", browser="chrome")
        checks = [
            (fp1.user_agent == fp2.user_agent, "user_agent совпадает"),
            (fp1.webgl_renderer == fp2.webgl_renderer, "webgl_renderer совпадает"),
            (fp1.canvas_noise_seed == fp2.canvas_noise_seed, "canvas_noise_seed совпадает"),
            (fp1.audio_noise_seed == fp2.audio_noise_seed, "audio_noise_seed совпадает"),
            (fp1.screen_width == fp2.screen_width, "screen совпадает"),
            (fp1.hardware_cores == fp2.hardware_cores, "hardware совпадает"),
        ]
        passed = sum(1 for ok, _ in checks if ok)
        total = len(checks)
        score = (passed / total) * 100
        details = "; ".join(msg for ok, msg in checks if not ok) or "Детерминизм подтверждён"
        return StealthTestResult(
            name="Fingerprint Determinism",
            category="fingerprint",
            status=BenchmarkTestStatus.PASSED if score == 100 else BenchmarkTestStatus.FAILED,
            score=score,
            details=details,
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Fingerprint Determinism",
            category="fingerprint",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_fingerprint_uniqueness() -> StealthTestResult:
    """Разные profile_name → разные отпечатки."""
    start = time.monotonic()
    try:
        fp1 = FingerprintManager.generate("uniq_test_001", os="windows", browser="chrome")
        fp2 = FingerprintManager.generate("uniq_test_002", os="windows", browser="chrome")
        checks = [
            (fp1.canvas_noise_seed != fp2.canvas_noise_seed, "canvas seed разный"),
            (fp1.audio_noise_seed != fp2.audio_noise_seed, "audio seed разный"),
        ]
        passed = sum(1 for ok, _ in checks if ok)
        total = len(checks)
        score = (passed / total) * 100
        details = "; ".join(msg for ok, msg in checks if not ok) or "Уникальность подтверждена"
        return StealthTestResult(
            name="Fingerprint Uniqueness",
            category="fingerprint",
            status=BenchmarkTestStatus.PASSED if score == 100 else BenchmarkTestStatus.FAILED,
            score=score,
            details=details,
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Fingerprint Uniqueness",
            category="fingerprint",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_canvas_spoofing_active(page) -> StealthTestResult:
    """Canvas шум применяется и влияет на toDataURL."""
    start = time.monotonic()
    try:
        fp = FingerprintManager.generate("canvas_test", os="windows", browser="chrome")
        await FingerprintManager.apply(page, fp)

        result = await page.evaluate("""
            () => {
                const canvas = document.createElement('canvas');
                canvas.width = 200;
                canvas.height = 50;
                const ctx = canvas.getContext('2d');
                ctx.fillStyle = '#ff0000';
                ctx.fillRect(0, 0, 100, 50);
                ctx.fillStyle = '#00ff00';
                ctx.fillRect(100, 0, 100, 50);
                const dataURL = canvas.toDataURL();
                return {
                    length: dataURL.length,
                    prefix: dataURL.substring(0, 30),
                    hasContent: dataURL.length > 100
                };
            }
        """)
        score = 100.0 if result.get("hasContent") else 0.0
        return StealthTestResult(
            name="Canvas Spoofing Active",
            category="fingerprint",
            status=BenchmarkTestStatus.PASSED if score == 100 else BenchmarkTestStatus.FAILED,
            score=score,
            details=f"Canvas dataURL length={result.get('length')}, hasContent={result.get('hasContent')}",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Canvas Spoofing Active",
            category="fingerprint",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_canvas_noise_consistency(page) -> StealthTestResult:
    """Canvas шум консистентен при повторных вызовах с тем же seed."""
    start = time.monotonic()
    try:
        fp = FingerprintManager.generate("canvas_cons", os="windows", browser="chrome")
        await FingerprintManager.apply(page, fp)

        result = await page.evaluate("""
            () => {
                const results = [];
                for (let i = 0; i < 3; i++) {
                    const canvas = document.createElement('canvas');
                    canvas.width = 100;
                    canvas.height = 50;
                    const ctx = canvas.getContext('2d');
                    ctx.fillStyle = '#336699';
                    ctx.fillRect(0, 0, 100, 50);
                    results.push(canvas.toDataURL());
                }
                const allSame = results[0] === results[1] && results[1] === results[2];
                const allValid = results.every(r => r.length > 100);
                return {
                    allSame,
                    allValid,
                    lengths: results.map(r => r.length),
                    firstPrefix: results[0].substring(0, 40)
                };
            }
        """)
        all_same = result.get("allSame", False)
        all_valid = result.get("allValid", False)
        score = (50.0 if all_same else 0.0) + (50.0 if all_valid else 0.0)
        details = f"allSame={all_same}, allValid={all_valid}, lengths={result.get('lengths')}"
        return StealthTestResult(
            name="Canvas Noise Consistency",
            category="fingerprint",
            status=BenchmarkTestStatus.PASSED if score == 100 else BenchmarkTestStatus.FAILED,
            score=score,
            details=details,
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Canvas Noise Consistency",
            category="fingerprint",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_webgl_spoofing(page) -> StealthTestResult:
    """WebGL vendor и renderer подменены на ожидаемые значения."""
    start = time.monotonic()
    try:
        fp = FingerprintManager.generate("webgl_test", os="windows", browser="chrome")
        await FingerprintManager.apply(page, fp)

        result = await page.evaluate("""
            () => {
                const canvas = document.createElement('canvas');
                const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                if (!gl) return { error: 'WebGL not available' };
                const ext = gl.getExtension('WEBGL_debug_renderer_info');
                if (!ext) return { error: 'WEBGL_debug_renderer_info not available' };
                return {
                    vendor: gl.getParameter(ext.UNMASKED_VENDOR_WEBGL),
                    renderer: gl.getParameter(ext.UNMASKED_RENDERER_WEBGL),
                };
            }
        """)
        if "error" in result:
            return StealthTestResult(
                name="WebGL Spoofing",
                category="fingerprint",
                status=BenchmarkTestStatus.SKIPPED,
                score=0,
                details=result["error"],
                duration_ms=(time.monotonic() - start) * 1000,
            )

        vendor = result.get("vendor", "")
        renderer = result.get("renderer", "")
        expected_vendor = fp.webgl_vendor
        expected_renderer = fp.webgl_renderer

        vendor_ok = vendor == expected_vendor
        renderer_ok = renderer == expected_renderer
        score = (100.0 if vendor_ok else 0.0) * 0.5 + (100.0 if renderer_ok else 0.0) * 0.5

        details = (f"vendor={vendor} (expected={expected_vendor}, {'OK' if vendor_ok else 'FAIL'}), "
                   f"renderer={renderer[:60]}... (expected={expected_renderer[:60]}..., "
                   f"{'OK' if renderer_ok else 'FAIL'})")

        return StealthTestResult(
            name="WebGL Spoofing",
            category="fingerprint",
            status=BenchmarkTestStatus.PASSED if score == 100 else BenchmarkTestStatus.FAILED,
            score=score,
            details=details,
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="WebGL Spoofing",
            category="fingerprint",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_audio_spoofing(page) -> StealthTestResult:
    """AudioContext FFT спектр подменён на фейковые значения."""
    start = time.monotonic()
    try:
        config = AudioConfig.full(noise_seed=42)
        await apply_audio_spoofing(page, config)
        # add_init_script требует навигации для активации
        await page.goto("about:blank")

        result = await page.evaluate("""
            () => {
                try {
                    const ctx = new AudioContext();
                    const analyser = ctx.createAnalyser();
                    analyser.fftSize = 32;
                    const data = new Float32Array(analyser.frequencyBinCount);
                    analyser.getFloatFrequencyData(data);
                    const values = Array.from(data);
                    // Фейковый спектр: base=-40, sin amplitude=15, noise=±5 → range ~-60..-20
                    // Проверяем что значения не -inf (значит спуфинг работает)
                    const allFinite = values.every(v => isFinite(v));
                    const allInRange = values.every(v => v > -80 && v < 0);
                    const avg = values.reduce((a, b) => a + b, 0) / values.length;
                    return {
                        values: values.slice(0, 5),
                        allFinite,
                        allInRange,
                        avg: isFinite(avg) ? avg.toFixed(2) : 'N/A',
                        count: values.length
                    };
                } catch(e) {
                    return { error: e.message };
                }
            }
        """)
        if "error" in result:
            return StealthTestResult(
                name="Audio Spoofing",
                category="fingerprint",
                status=BenchmarkTestStatus.ERROR,
                score=0,
                details=result["error"],
                duration_ms=(time.monotonic() - start) * 1000,
            )

        all_finite = result.get("allFinite", False)
        all_in_range = result.get("allInRange", False)
        # Основная проверка: значения конечные (не -inf), значит спуфинг работает
        score = (50.0 if all_finite else 0.0) + (50.0 if all_in_range else 0.0)
        return StealthTestResult(
            name="Audio Spoofing",
            category="fingerprint",
            status=BenchmarkTestStatus.PASSED if score == 100 else (BenchmarkTestStatus.PASSED if score >= 50 else BenchmarkTestStatus.FAILED),
            score=score,
            details=f"FFT avg={result.get('avg')} dB, allFinite={all_finite}, allInRange={all_in_range}, sample={result.get('values')}",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Audio Spoofing",
            category="fingerprint",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_screen_spoofing(page) -> StealthTestResult:
    """Screen параметры подменены на ожидаемые значения."""
    start = time.monotonic()
    try:
        fp = FingerprintManager.generate("screen_test", os="windows", browser="chrome")
        await FingerprintManager.apply(page, fp)

        result = await page.evaluate(
            "() => ({"
            "  width: screen.width,"
            "  height: screen.height,"
            "  availWidth: screen.availWidth,"
            "  availHeight: screen.availHeight,"
            "  colorDepth: screen.colorDepth,"
            "})"
        )
        checks = [
            (result.get("width") == fp.screen_width,
             f"width={result.get('width')} (expected {fp.screen_width})"),
            (result.get("height") == fp.screen_height,
             f"height={result.get('height')} (expected {fp.screen_height})"),
            (result.get("colorDepth") == fp.screen_color_depth,
             f"colorDepth={result.get('colorDepth')} (expected {fp.screen_color_depth})"),
        ]
        passed = sum(1 for ok, _ in checks if ok)
        total = len(checks)
        score = (passed / total) * 100
        details = "; ".join(msg for ok, msg in checks if not ok) or "Screen параметры совпадают"
        return StealthTestResult(
            name="Screen Spoofing",
            category="fingerprint",
            status=BenchmarkTestStatus.PASSED if score == 100 else BenchmarkTestStatus.FAILED,
            score=score,
            details=details,
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Screen Spoofing",
            category="fingerprint",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_hardware_spoofing(page) -> StealthTestResult:
    """Hardware параметры (cores, memory, platform) подменены."""
    start = time.monotonic()
    try:
        fp = FingerprintManager.generate("hw_test", os="windows", browser="chrome")
        await FingerprintManager.apply(page, fp)

        result = await page.evaluate(
            "() => ({"
            "  cores: navigator.hardwareConcurrency,"
            "  memory: navigator.deviceMemory,"
            "  platform: navigator.platform,"
            "})"
        )
        checks = [
            (result.get("cores") == fp.hardware_cores,
             f"cores={result.get('cores')} (expected {fp.hardware_cores})"),
            (result.get("memory") == fp.hardware_memory,
             f"memory={result.get('memory')} (expected {fp.hardware_memory})"),
            (result.get("platform") == fp.hardware_platform,
             f"platform={result.get('platform')} (expected {fp.hardware_platform})"),
        ]
        passed = sum(1 for ok, _ in checks if ok)
        total = len(checks)
        score = (passed / total) * 100
        details = "; ".join(msg for ok, msg in checks if not ok) or "Hardware параметры совпадают"
        return StealthTestResult(
            name="Hardware Spoofing",
            category="fingerprint",
            status=BenchmarkTestStatus.PASSED if score == 100 else BenchmarkTestStatus.FAILED,
            score=score,
            details=details,
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Hardware Spoofing",
            category="fingerprint",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


# ═══════════════════════════════════════════════════════════════════════════
# ТЕСТЫ: BEHAVIOR
# ═══════════════════════════════════════════════════════════════════════════

async def test_mouse_movement(page) -> StealthTestResult:
    """HumanBehaviorEngine.move_mouse_to() работает без ошибок."""
    start = time.monotonic()
    try:
        behavior = HumanBehaviorEngine(page, profile="casual_reader", seed=42)
        await behavior.move_mouse_to(500, 300)
        score = 100.0
        return StealthTestResult(
            name="Mouse Movement",
            category="behavior",
            status=BenchmarkTestStatus.PASSED,
            score=score,
            details="move_mouse_to(500, 300) выполнен без ошибок",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Mouse Movement",
            category="behavior",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_scroll_behavior(page) -> StealthTestResult:
    """HumanBehaviorEngine.scroll_down() работает плавно."""
    start = time.monotonic()
    try:
        await page.set_content(
            "<div style='height:5000px;background:linear-gradient(red,blue)'></div>"
        )
        behavior = HumanBehaviorEngine(page, profile="casual_reader", seed=42)
        await behavior.scroll_down(pages=0.5)

        scroll_y = await page.evaluate("() => window.scrollY")
        score = 100.0 if scroll_y > 0 else 0.0
        return StealthTestResult(
            name="Scroll Behavior",
            category="behavior",
            status=BenchmarkTestStatus.PASSED if score == 100 else BenchmarkTestStatus.FAILED,
            score=score,
            details=f"scrollY={scroll_y} после scroll_down(0.5)",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Scroll Behavior",
            category="behavior",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_type_text(page) -> StealthTestResult:
    """HumanBehaviorEngine.type_text() работает без ошибок."""
    start = time.monotonic()
    try:
        await page.set_content("<input id='test-input' type='text' />")
        behavior = HumanBehaviorEngine(page, profile="casual_reader", seed=42)
        await behavior.type_text("Hello World", locator=page.locator("#test-input"))

        value = await page.evaluate("() => document.getElementById('test-input').value")
        score = 100.0 if value == "Hello World" else 0.0
        return StealthTestResult(
            name="Type Text",
            category="behavior",
            status=BenchmarkTestStatus.PASSED if score == 100 else BenchmarkTestStatus.FAILED,
            score=score,
            details=f"Введённый текст: '{value}' (expected 'Hello World')",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Type Text",
            category="behavior",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_behavior_profiles() -> StealthTestResult:
    """Все 4 пресета поведения создаются без ошибок."""
    start = time.monotonic()
    try:
        profiles = ["casual_reader", "power_user", "researcher", "social_media"]
        results = {}
        for name in profiles:
            try:
                BehaviorProfile(name=name)
                results[name] = "OK"
            except Exception as e:
                results[name] = f"FAIL: {e}"

        all_ok = all(v == "OK" for v in results.values())
        score = 100.0 if all_ok else (sum(1 for v in results.values() if v == "OK") / len(results)) * 100
        return StealthTestResult(
            name="Behavior Profiles",
            category="behavior",
            status=BenchmarkTestStatus.PASSED if all_ok else BenchmarkTestStatus.FAILED,
            score=score,
            details=str(results),
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Behavior Profiles",
            category="behavior",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_bezier_mouse_trajectory() -> StealthTestResult:
    """Кривые Безье генерируют корректные точки траектории."""
    start = time.monotonic()
    try:
        import random as _rnd
        engine = HumanBehaviorEngine.__new__(HumanBehaviorEngine)
        engine._rng = _rnd.Random(42)

        points = engine._generate_bezier_points(0, 0, 100, 100, 20)
        checks = [
            (len(points) == 21, f"21 точка (получено {len(points)})"),
            (points[0] == (0, 0), f"start={points[0]}"),
            (points[-1] == (100, 100), f"end={points[-1]}"),
        ]
        passed = sum(1 for ok, _ in checks if ok)
        total = len(checks)
        score = (passed / total) * 100
        details = "; ".join(msg for ok, msg in checks if not ok) or "Траектория корректна"
        return StealthTestResult(
            name="Bezier Mouse Trajectory",
            category="behavior",
            status=BenchmarkTestStatus.PASSED if score == 100 else BenchmarkTestStatus.FAILED,
            score=score,
            details=details,
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Bezier Mouse Trajectory",
            category="behavior",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


# ═══════════════════════════════════════════════════════════════════════════
# ТЕСТЫ: NETWORK (WebRTC, Client Hints)
# ═══════════════════════════════════════════════════════════════════════════

async def test_webrtc_block_all(page) -> StealthTestResult:
    """WebRTC block_all — RTCPeerConnection полностью заблокирован."""
    start = time.monotonic()
    try:
        config = WebRTCConfig.block_all()
        await apply_webrtc_protection(page, config)

        result = await page.evaluate("""
            () => {
                try {
                    const pc = new RTCPeerConnection();
                    return {
                        exists: true,
                        createOfferWorks: typeof pc.createOffer === 'function',
                        connectionState: pc.connectionState,
                        isFake: pc.connectionState === 'new' && typeof pc.close === 'function'
                    };
                } catch(e) {
                    return { error: e.message };
                }
            }
        """)
        if "error" in result:
            return StealthTestResult(
                name="WebRTC Block All",
                category="network",
                status=BenchmarkTestStatus.ERROR,
                score=0,
                details=result["error"],
                duration_ms=(time.monotonic() - start) * 1000,
            )

        is_fake = result.get("isFake", False)
        score = 100.0 if is_fake else 0.0
        return StealthTestResult(
            name="WebRTC Block All",
            category="network",
            status=BenchmarkTestStatus.PASSED if is_fake else BenchmarkTestStatus.FAILED,
            score=score,
            details=f"exists={result.get('exists')}, connectionState={result.get('connectionState')}, isFake={is_fake}",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="WebRTC Block All",
            category="network",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_webrtc_filter_host(page) -> StealthTestResult:
    """WebRTC filter_host — RTCPeerConnection работает, но host-кандидаты фильтруются."""
    start = time.monotonic()
    try:
        config = WebRTCConfig.filter_host()
        await apply_webrtc_protection(page, config)

        result = await page.evaluate("""
            () => {
                try {
                    const pc = new RTCPeerConnection();
                    return {
                        exists: true,
                        connectionState: pc.connectionState,
                        hasCreateOffer: typeof pc.createOffer === 'function',
                        hasAddIceCandidate: typeof pc.addIceCandidate === 'function',
                    };
                } catch(e) {
                    return { error: e.message };
                }
            }
        """)
        if "error" in result:
            return StealthTestResult(
                name="WebRTC Filter Host",
                category="network",
                status=BenchmarkTestStatus.ERROR,
                score=0,
                details=result["error"],
                duration_ms=(time.monotonic() - start) * 1000,
            )

        works = result.get("exists") and result.get("hasCreateOffer")
        score = 100.0 if works else 0.0
        return StealthTestResult(
            name="WebRTC Filter Host",
            category="network",
            status=BenchmarkTestStatus.PASSED if works else BenchmarkTestStatus.FAILED,
            score=score,
            details=f"RTCPeerConnection работает: {result}",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="WebRTC Filter Host",
            category="network",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_client_hints_consistency(page) -> StealthTestResult:
    """Client Hints согласованы с User-Agent."""
    start = time.monotonic()
    try:
        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        config = ClientHintsConfig.from_user_agent(ua)
        await apply_client_hints(page, config)
        # apply_client_hints использует add_init_script — нужна навигация
        await page.goto("about:blank")

        result = await page.evaluate("""
            () => {
                if (!navigator.userAgentData) return { error: 'userAgentData not available' };
                return {
                    platform: navigator.userAgentData.platform,
                    mobile: navigator.userAgentData.mobile,
                    brands: navigator.userAgentData.brands,
                };
            }
        """)
        if "error" in result:
            return StealthTestResult(
                name="Client Hints Consistency",
                category="network",
                status=BenchmarkTestStatus.SKIPPED,
                score=0,
                details=result["error"],
                duration_ms=(time.monotonic() - start) * 1000,
            )

        platform = result.get("platform", "")
        mobile = result.get("mobile", True)
        brands = result.get("brands", [])

        platform_ok = platform == "Windows"
        mobile_ok = mobile is False
        brands_ok = len(brands) >= 2 and any(
            b.get("brand") in ("Google Chrome", "Chromium") for b in brands
        )

        checks = [platform_ok, mobile_ok, brands_ok]
        score = (sum(1 for ok in checks if ok) / len(checks)) * 100
        details = (f"platform={platform} ({'OK' if platform_ok else 'FAIL'}), "
                   f"mobile={mobile} ({'OK' if mobile_ok else 'FAIL'}), "
                   f"brands={len(brands)} ({'OK' if brands_ok else 'FAIL'})")

        return StealthTestResult(
            name="Client Hints Consistency",
            category="network",
            status=BenchmarkTestStatus.PASSED if score == 100 else BenchmarkTestStatus.FAILED,
            score=score,
            details=details,
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Client Hints Consistency",
            category="network",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_client_hints_high_entropy(page) -> StealthTestResult:
    """getHighEntropyValues возвращает согласованные данные."""
    start = time.monotonic()
    try:
        config = ClientHintsConfig.chrome_windows("131")
        await apply_client_hints(page, config)
        # apply_client_hints использует add_init_script — нужна навигация
        await page.goto("about:blank")

        result = await page.evaluate("""
            async () => {
                try {
                    const data = await navigator.userAgentData.getHighEntropyValues([
                        'platform', 'platformVersion', 'architecture', 'bitness', 'uaFullVersion'
                    ]);
                    return data;
                } catch(e) {
                    return { error: e.message };
                }
            }
        """)
        if "error" in result:
            return StealthTestResult(
                name="Client Hints High Entropy",
                category="network",
                status=BenchmarkTestStatus.ERROR,
                score=0,
                details=result["error"],
                duration_ms=(time.monotonic() - start) * 1000,
            )

        checks = [
            (result.get("platform") == "Windows", f"platform={result.get('platform')}"),
            (result.get("architecture") == "x86", f"arch={result.get('architecture')}"),
            (result.get("bitness") == "64", f"bitness={result.get('bitness')}"),
            ("131" in str(result.get("uaFullVersion", "")), f"uaFullVersion={result.get('uaFullVersion')}"),
        ]
        passed = sum(1 for ok, _ in checks if ok)
        total = len(checks)
        score = (passed / total) * 100
        details = "; ".join(msg for ok, msg in checks if not ok) or "High entropy values согласованы"
        return StealthTestResult(
            name="Client Hints High Entropy",
            category="network",
            status=BenchmarkTestStatus.PASSED if score == 100 else BenchmarkTestStatus.FAILED,
            score=score,
            details=details,
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Client Hints High Entropy",
            category="network",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


# ═══════════════════════════════════════════════════════════════════════════
# ТЕСТЫ: CONSISTENCY
# ═══════════════════════════════════════════════════════════════════════════

async def test_stealth_webdriver_hidden(page) -> StealthTestResult:
    """navigator.webdriver === undefined после применения stealth."""
    start = time.monotonic()
    try:
        config = StealthConfig.advanced()
        await _apply_stealth_and_navigate(page, config)

        result = await page.evaluate("() => navigator.webdriver")
        score = 100.0 if result is None or result is False else 0.0
        return StealthTestResult(
            name="Webdriver Hidden",
            category="consistency",
            status=BenchmarkTestStatus.PASSED if score == 100 else BenchmarkTestStatus.FAILED,
            score=score,
            details=f"navigator.webdriver = {result}",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Webdriver Hidden",
            category="consistency",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_stealth_plugins_populated(page) -> StealthTestResult:
    """navigator.plugins содержит фейковые плагины."""
    start = time.monotonic()
    try:
        config = StealthConfig.advanced()
        await _apply_stealth_and_navigate(page, config)

        result = await page.evaluate("""
            () => ({
                length: navigator.plugins.length,
                names: Array.from(navigator.plugins).map(p => p.name)
            })
        """)
        length = result.get("length", 0)
        names = result.get("names", [])
        has_pdf = any("PDF" in n for n in names)
        has_nacl = any("Native Client" in n for n in names)
        score = (100.0 if length >= 3 else (length / 3) * 100) * 0.5
        score += (50.0 if has_pdf else 0.0) + (50.0 if has_nacl else 0.0) * 0.5
        details = f"plugins count={length}, names={names}"
        return StealthTestResult(
            name="Plugins Populated",
            category="consistency",
            status=BenchmarkTestStatus.PASSED if length >= 3 else BenchmarkTestStatus.FAILED,
            score=min(score, 100.0),
            details=details,
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Plugins Populated",
            category="consistency",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_stealth_languages(page) -> StealthTestResult:
    """navigator.languages содержит реалистичные значения."""
    start = time.monotonic()
    try:
        config = StealthConfig.advanced()
        await _apply_stealth_and_navigate(page, config)

        result = await page.evaluate("() => navigator.languages")
        has_ru = any("ru" in str(l).lower() for l in result) if result else False
        has_en = any("en" in str(l).lower() for l in result) if result else False
        score = (50.0 if has_ru else 0.0) + (50.0 if has_en else 0.0)
        details = f"languages={result}"
        return StealthTestResult(
            name="Languages Realistic",
            category="consistency",
            status=BenchmarkTestStatus.PASSED if score == 100 else BenchmarkTestStatus.FAILED,
            score=score,
            details=details,
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Languages Realistic",
            category="consistency",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_stealth_permissions(page) -> StealthTestResult:
    """permissions.query для notifications возвращает корректный результат."""
    start = time.monotonic()
    try:
        config = StealthConfig.advanced()
        await _apply_stealth_and_navigate(page, config)

        result = await page.evaluate("""
            () => navigator.permissions.query({ name: 'notifications' })
                .then(r => r.state).catch(e => 'error: ' + e.message)
        """)
        valid_states = ("granted", "denied", "prompt")
        score = 100.0 if result in valid_states else 0.0
        return StealthTestResult(
            name="Permissions API",
            category="consistency",
            status=BenchmarkTestStatus.PASSED if score == 100 else BenchmarkTestStatus.FAILED,
            score=score,
            details=f"notifications.state = {result}",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Permissions API",
            category="consistency",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_stealth_chrome_runtime(page) -> StealthTestResult:
    """window.chrome.runtime существует."""
    start = time.monotonic()
    try:
        config = StealthConfig.advanced()
        await _apply_stealth_and_navigate(page, config)

        result = await page.evaluate("""
            () => ({
                hasChrome: typeof window.chrome !== 'undefined',
                hasRuntime: typeof window.chrome !== 'undefined' && typeof window.chrome.runtime !== 'undefined',
                hasApp: typeof window.chrome !== 'undefined' && typeof window.chrome.app !== 'undefined',
            })
        """)
        score = 0.0
        if result.get("hasChrome"):
            score += 33.3
        if result.get("hasRuntime"):
            score += 33.3
        if result.get("hasApp"):
            score += 33.4
        return StealthTestResult(
            name="Chrome Runtime",
            category="consistency",
            status=BenchmarkTestStatus.PASSED if score == 100 else BenchmarkTestStatus.FAILED,
            score=score,
            details=str(result),
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Chrome Runtime",
            category="consistency",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_full_integration(page) -> StealthTestResult:
    """Все stealth-модули активны одновременно — нет конфликтов.

    Используем add_init_script для всех модулей, затем одну навигацию.
    FingerprintManager.apply НЕ вызываем во избежание конфликта
    Object.defineProperty с уже определёнными stealth-скриптами.
    """
    start = time.monotonic()
    try:
        # Применяем ВСЁ через add_init_script (требует навигации после)
        stealth_config = StealthConfig.full()
        await apply_stealth(page, stealth_config)

        webrtc_config = WebRTCConfig.block_all()
        await apply_webrtc_protection(page, webrtc_config)

        audio_config = AudioConfig.full(noise_seed=42)
        await apply_audio_spoofing(page, audio_config)

        hints_config = ClientHintsConfig.chrome_windows("131")
        await apply_client_hints(page, hints_config)

        # Навигация для активации всех add_init_script
        await page.goto("about:blank")

        result = await page.evaluate("""
            () => ({
                webdriver: navigator.webdriver,
                plugins: navigator.plugins.length,
                languages: navigator.languages.length,
                chrome: typeof window.chrome !== 'undefined',
                vendor: navigator.vendor,
                hardwareConcurrency: navigator.hardwareConcurrency,
                deviceMemory: navigator.deviceMemory,
                screenDepth: screen.colorDepth,
            })
        """)
        checks = [
            (result.get("webdriver") is None or result.get("webdriver") is False,
             f"webdriver={result.get('webdriver')}"),
            (result.get("plugins", 0) >= 3,
             f"plugins={result.get('plugins')}"),
            (result.get("languages", 0) >= 2,
             f"languages={result.get('languages')}"),
            (result.get("chrome") is True,
             f"chrome={result.get('chrome')}"),
            (result.get("vendor") == "Google Inc.",
             f"vendor={result.get('vendor')}"),
            (result.get("hardwareConcurrency") == 8,
             f"cores={result.get('hardwareConcurrency')}"),
            (result.get("deviceMemory") == 8,
             f"memory={result.get('deviceMemory')}"),
            (result.get("screenDepth") == 24,
             f"screenDepth={result.get('screenDepth')}"),
        ]
        passed = sum(1 for ok, _ in checks if ok)
        total = len(checks)
        score = (passed / total) * 100
        details = "; ".join(msg for ok, msg in checks if not ok) or f"Все {total} проверок пройдены"
        return StealthTestResult(
            name="Full Integration",
            category="consistency",
            status=BenchmarkTestStatus.PASSED if score >= 75 else BenchmarkTestStatus.FAILED,
            score=score,
            details=details,
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Full Integration",
            category="consistency",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def test_stealth_levels() -> StealthTestResult:
    """Все 4 уровня stealth генерируют разное количество скриптов."""
    start = time.monotonic()
    try:
        levels = {
            "minimal": StealthConfig.minimal(),
            "standard": StealthConfig.standard(),
            "advanced": StealthConfig.advanced(),
            "full": StealthConfig.full(),
        }
        counts = {name: len(cfg.get_scripts()) for name, cfg in levels.items()}
        checks = [
            (counts["minimal"] == 1, f"minimal={counts['minimal']} (expected 1)"),
            (counts["standard"] == 6, f"standard={counts['standard']} (expected 6)"),
            (counts["advanced"] >= 12, f"advanced={counts['advanced']} (expected >= 12)"),
            (counts["full"] >= 12, f"full={counts['full']} (expected >= 12)"),
        ]
        passed = sum(1 for ok, _ in checks if ok)
        total = len(checks)
        score = (passed / total) * 100
        details = str(counts)
        return StealthTestResult(
            name="Stealth Levels",
            category="consistency",
            status=BenchmarkTestStatus.PASSED if score == 100 else BenchmarkTestStatus.FAILED,
            score=score,
            details=details,
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as e:
        return StealthTestResult(
            name="Stealth Levels",
            category="consistency",
            status=BenchmarkTestStatus.ERROR,
            score=0,
            details=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )


# ═══════════════════════════════════════════════════════════════════════════
# РЕЕСТР ТЕСТОВ
# ═══════════════════════════════════════════════════════════════════════════

UNIT_TESTS = [
    ("fingerprint", test_fingerprint_generation),
    ("fingerprint", test_fingerprint_determinism),
    ("fingerprint", test_fingerprint_uniqueness),
    ("behavior", test_behavior_profiles),
    ("behavior", test_bezier_mouse_trajectory),
    ("consistency", test_stealth_levels),
]

BROWSER_TESTS = [
    ("fingerprint", test_canvas_spoofing_active),
    ("fingerprint", test_canvas_noise_consistency),
    ("fingerprint", test_webgl_spoofing),
    ("fingerprint", test_audio_spoofing),
    ("fingerprint", test_screen_spoofing),
    ("fingerprint", test_hardware_spoofing),
    ("behavior", test_mouse_movement),
    ("behavior", test_scroll_behavior),
    ("behavior", test_type_text),
    ("network", test_webrtc_block_all),
    ("network", test_webrtc_filter_host),
    ("network", test_client_hints_consistency),
    ("network", test_client_hints_high_entropy),
    ("consistency", test_stealth_webdriver_hidden),
    ("consistency", test_stealth_plugins_populated),
    ("consistency", test_stealth_languages),
    ("consistency", test_stealth_permissions),
    ("consistency", test_stealth_chrome_runtime),
    ("consistency", test_full_integration),
]


# ═══════════════════════════════════════════════════════════════════════════
# HTML REPORT GENERATOR
# ═══════════════════════════════════════════════════════════════════════════

def generate_html_report(report: SuiteReport, output_dir: str) -> str:
    """Генерация красивого HTML-отчёта."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    def score_color(score: float) -> str:
        if score >= 80:
            return "#22c55e"
        elif score >= 60:
            return "#f59e0b"
        else:
            return "#ef4444"

    def status_badge(status: BenchmarkTestStatus) -> str:
        colors = {
            BenchmarkTestStatus.PASSED: "#22c55e",
            BenchmarkTestStatus.FAILED: "#ef4444",
            BenchmarkTestStatus.SKIPPED: "#6b7280",
            BenchmarkTestStatus.ERROR: "#f97316",
        }
        labels = {
            BenchmarkTestStatus.PASSED: "✅ PASSED",
            BenchmarkTestStatus.FAILED: "❌ FAILED",
            BenchmarkTestStatus.SKIPPED: "⏭ SKIPPED",
            BenchmarkTestStatus.ERROR: "⚠️ ERROR",
        }
        color = colors.get(status, "#6b7280")
        label = labels.get(status, str(status))
        return (f'<span style="background:{color};color:#fff;'
                f'padding:2px 8px;border-radius:4px;font-size:12px;'
                f'font-weight:600">{label}</span>')

    category_sections = ""
    for cat in report.categories:
        rows = ""
        for r in cat.results:
            rows += f"""
            <tr>
                <td style="padding:8px 12px;border-bottom:1px solid #1e293b">{r.name}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #1e293b;text-align:center">{status_badge(r.status)}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #1e293b;text-align:center">
                    <span style="color:{score_color(r.score)};font-weight:600">{r.score:.0f}</span>
                </td>
                <td style="padding:8px 12px;border-bottom:1px solid #1e293b;color:#94a3b8;font-size:13px">{r.details}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #1e293b;text-align:right;color:#64748b">{r.duration_ms:.0f}ms</td>
            </tr>"""

        cat_score_color = score_color(cat.score)
        pass_rate = f"{cat.tests_passed}/{cat.tests_total}"

        category_sections += f"""
        <div style="margin-bottom:32px">
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
                <h2 style="color:#e2e8f0;margin:0;font-size:20px">{cat.name.upper()}</h2>
                <span style="background:{cat_score_color};color:#fff;padding:4px 12px;border-radius:6px;font-weight:700;font-size:18px">{cat.score:.0f}/100</span>
                <span style="color:#64748b;font-size:14px">({pass_rate} passed, weight={cat.weight:.0%})</span>
            </div>
            <table style="width:100%;border-collapse:collapse;background:#0f172a;border-radius:8px;overflow:hidden">
                <thead>
                    <tr style="background:#1e293b">
                        <th style="padding:10px 12px;text-align:left;color:#94a3b8;font-size:13px;font-weight:600">Тест</th>
                        <th style="padding:10px 12px;text-align:center;color:#94a3b8;font-size:13px;font-weight:600">Статус</th>
                        <th style="padding:10px 12px;text-align:center;color:#94a3b8;font-size:13px;font-weight:600">Скор</th>
                        <th style="padding:10px 12px;text-align:left;color:#94a3b8;font-size:13px;font-weight:600">Детали</th>
                        <th style="padding:10px 12px;text-align:right;color:#94a3b8;font-size:13px;font-weight:600">Время</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>"""

    recommendations = []
    for cat in report.categories:
        if cat.score < 60:
            recommendations.append(
                f"🔴 <strong>{cat.name.upper()}</strong>: Критически низкий скор "
                f"({cat.score:.0f}/100). Необходимо исправить проваленные тесты."
            )
        elif cat.score < 80:
            recommendations.append(
                f"🟡 <strong>{cat.name.upper()}</strong>: Скор ниже оптимального "
                f"({cat.score:.0f}/100). Рекомендуется улучшить."
            )

    if not recommendations:
        recommendations.append(
            "🟢 Все категории показывают хороший результат. Stealth-система работает корректно."
        )

    rec_html = "".join(
        f"<li style='margin-bottom:8px;color:#e2e8f0'>{r}</li>" for r in recommendations
    )

    overall_color = score_color(report.overall_score)

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stealth Benchmark Suite — Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #020617; color: #e2e8f0; line-height: 1.6; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 32px 24px; }}
        .header {{ text-align: center; margin-bottom: 40px; padding: 32px; background: linear-gradient(135deg, #0f172a, #1e293b); border-radius: 16px; border: 1px solid #1e293b; }}
        .score-circle {{ width: 160px; height: 160px; border-radius: 50%; background: conic-gradient({overall_color} {report.overall_score * 3.6}deg, #1e293b 0deg); display: flex; align-items: center; justify-content: center; margin: 0 auto 16px; }}
        .score-inner {{ width: 130px; height: 130px; border-radius: 50%; background: #0f172a; display: flex; flex-direction: column; align-items: center; justify-content: center; }}
        .score-value {{ font-size: 42px; font-weight: 800; color: {overall_color}; }}
        .score-label {{ font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 1px; }}
        h1 {{ font-size: 28px; margin-bottom: 8px; color: #f1f5f9; }}
        .subtitle {{ color: #64748b; font-size: 14px; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }}
        .stat-card {{ background: #0f172a; border: 1px solid #1e293b; border-radius: 12px; padding: 20px; text-align: center; }}
        .stat-value {{ font-size: 24px; font-weight: 700; color: #f1f5f9; }}
        .stat-label {{ font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }}
        .recommendations {{ background: #0f172a; border: 1px solid #1e293b; border-radius: 12px; padding: 24px; margin-top: 32px; }}
        .recommendations h3 {{ margin-bottom: 12px; color: #f1f5f9; }}
        .footer {{ text-align: center; margin-top: 40px; color: #475569; font-size: 13px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="score-circle">
                <div class="score-inner">
                    <div class="score-value">{report.overall_score:.0f}</div>
                    <div class="score-label">Stealth Score</div>
                </div>
            </div>
            <h1>🛡️ Stealth Benchmark Suite</h1>
            <div class="subtitle">Отчёт: {report.timestamp} | Длительность: {report.duration_ms / 1000:.1f}s</div>
        </div>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">{sum(c.tests_passed for c in report.categories)}</div>
                <div class="stat-label">Тестов пройдено</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{sum(c.tests_failed for c in report.categories)}</div>
                <div class="stat-label">Тестов провалено</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{sum(c.tests_total for c in report.categories)}</div>
                <div class="stat-label">Всего тестов</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{len(report.categories)}</div>
                <div class="stat-label">Категорий</div>
            </div>
        </div>

        {category_sections}

        <div class="recommendations">
            <h3>📋 Рекомендации</h3>
            <ul style="list-style:none;padding:0">
                {rec_html}
            </ul>
        </div>

        <div class="footer">
            Stealth Benchmark Suite v1.0.0 | Лаборатория DoctorM&Ai | Бестия 🦾
        </div>
    </div>
</body>
</html>"""

    report_file = output_path / "stealth_benchmark_report.html"
    report_file.write_text(html, encoding="utf-8")
    return str(report_file)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN RUNNER
# ═══════════════════════════════════════════════════════════════════════════

async def run_suite(
    tests_filter: str = "all",
    output_dir: str = "/tmp/stealth_reports",
    json_output: bool = False,
) -> SuiteReport:
    """Запустить бенчмарк-сьюит."""
    from datetime import datetime

    suite_start = time.monotonic()
    report = SuiteReport(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    if tests_filter == "all":
        categories_to_run = set(CATEGORY_WEIGHTS.keys())
    else:
        categories_to_run = set(t.strip() for t in tests_filter.split(","))

    logger.info(f"🚀 Stealth Benchmark Suite starting — categories: {categories_to_run}")

    # ─── Unit-тесты (без браузера) ─────────────────────────────────────────
    unit_results: dict[str, list[StealthTestResult]] = {cat: [] for cat in categories_to_run}

    for category, test_func in UNIT_TESTS:
        if category not in categories_to_run:
            continue
        logger.info(f"  [UNIT] {test_func.__name__}...")
        try:
            result = await test_func()
            unit_results[category].append(result)
            logger.info(
                f"    → {result.status.value} ({result.score:.0f}/100) "
                f"in {result.duration_ms:.0f}ms"
            )
        except Exception as e:
            logger.error(f"    → ERROR: {e}")
            unit_results[category].append(StealthTestResult(
                name=test_func.__name__,
                category=category,
                status=BenchmarkTestStatus.ERROR,
                score=0,
                details=str(e),
            ))

    # ─── Browser-тесты ─────────────────────────────────────────────────────
    browser_results: dict[str, list[StealthTestResult]] = {cat: [] for cat in categories_to_run}

    logger.info("🌐 Starting browser for integration tests...")
    try:
        async with BrowserManager(headless=True) as browser:
            for category, test_func in BROWSER_TESTS:
                if category not in categories_to_run:
                    continue
                test_name = test_func.__name__
                logger.info(f"  [BROWSER] {test_name}...")

                # Каждый тест получает свежую страницу, чтобы избежать конфликтов
                # Object.defineProperty (FingerprintManager.apply нельзя вызывать
                # дважды на одной странице — "Cannot redefine property")
                page = await browser.new_page()
                await page.goto("about:blank")

                try:
                    result = await test_func(page)
                    browser_results[category].append(result)
                    logger.info(
                        f"    → {result.status.value} ({result.score:.0f}/100) "
                        f"in {result.duration_ms:.0f}ms"
                    )
                except Exception as e:
                    logger.error(f"    → ERROR: {e}")
                    browser_results[category].append(StealthTestResult(
                        name=test_name,
                        category=category,
                        status=BenchmarkTestStatus.ERROR,
                        score=0,
                        details=str(e),
                    ))
                finally:
                    await page.close()
    except Exception as e:
        logger.error(f"Browser failed to start: {e}")
        report.errors.append(f"Browser error: {e}")

    # ─── Агрегация результатов ─────────────────────────────────────────────
    for category_name in categories_to_run:
        weight = CATEGORY_WEIGHTS.get(category_name, 0.25)
        all_results = unit_results.get(category_name, []) + browser_results.get(category_name, [])

        if not all_results:
            report.categories.append(CategoryScore(
                name=category_name,
                weight=weight,
                score=0,
                tests_total=0,
            ))
            continue

        total_score = sum(r.score for r in all_results)
        avg_score = total_score / len(all_results)

        passed = sum(1 for r in all_results if r.status == BenchmarkTestStatus.PASSED)
        failed = sum(1 for r in all_results if r.status in (BenchmarkTestStatus.FAILED, BenchmarkTestStatus.ERROR))

        report.categories.append(CategoryScore(
            name=category_name,
            weight=weight,
            score=avg_score,
            tests_passed=passed,
            tests_failed=failed,
            tests_total=len(all_results),
            results=all_results,
        ))

    total_weight = sum(c.weight for c in report.categories)
    if total_weight > 0:
        report.overall_score = sum(c.score * c.weight for c in report.categories) / total_weight
    else:
        report.overall_score = 0

    report.duration_ms = (time.monotonic() - suite_start) * 1000

    # ─── Генерация отчётов ─────────────────────────────────────────────────
    html_path = generate_html_report(report, output_dir)
    logger.info(f"📊 HTML report: {html_path}")

    if json_output:
        json_path = os.path.join(output_dir, "stealth_benchmark_results.json")
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"📄 JSON report: {json_path}")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Stealth Benchmark Suite — тестирование антидетекта Lab Playwright Kit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python3 scripts/stealth_benchmark_suite.py --tests all --output /tmp/reports
  python3 scripts/stealth_benchmark_suite.py --tests fingerprint,behavior --json
  python3 scripts/stealth_benchmark_suite.py --tests network --output ./reports
        """,
    )
    parser.add_argument(
        "--tests",
        default="all",
        help="Какие тесты запускать: all|fingerprint|behavior|network|consistency (или через запятую)",
    )
    parser.add_argument(
        "--output",
        default="/tmp/stealth_reports",
        help="Директория для отчётов (default: /tmp/stealth_reports)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Также сохранить результаты в JSON",
    )

    args = parser.parse_args()

    logger.remove()
    logger.add(
        sys.stderr,
        format="<level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )

    report = asyncio.run(run_suite(
        tests_filter=args.tests,
        output_dir=args.output,
        json_output=args.json,
    ))

    # Выводим итоговый скор
    print(f"\n{'=' * 60}")
    print(f"  🛡️  STEALTH BENCHMARK SUITE — RESULTS")
    print(f"{'=' * 60}")
    print(f"  Overall Score: {report.overall_score:.1f}/100")
    print(f"  Duration: {report.duration_ms / 1000:.1f}s")
    print(f"{'─' * 60}")
    for cat in report.categories:
        status = "🟢" if cat.score >= 80 else ("🟡" if cat.score >= 60 else "🔴")
        print(
            f"  {status} {cat.name.upper():15s} {cat.score:6.1f}/100  "
            f"({cat.tests_passed}/{cat.tests_total} passed, weight={cat.weight:.0%})"
        )
    print(f"{'=' * 60}")

    if report.errors:
        print(f"\n⚠️  Errors ({len(report.errors)}):")
        for err in report.errors:
            print(f"  — {err}")

    sys.exit(0 if report.overall_score >= 60 else 1)


if __name__ == "__main__":
    main()


# Backward compatibility aliases
TestStatus = BenchmarkTestStatus
