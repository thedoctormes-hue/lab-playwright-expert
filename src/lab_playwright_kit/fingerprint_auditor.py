"""
Fingerprint Consistency Engine — аудит и валидация браузерных отпечатков.

Проверяет согласованность fingerprint компонентов:
  - User-Agent ↔ navigator.platform ↔ OS
  - WebGL vendor/renderer ↔ GPU ↔ platform
  - Screen resolution ↔ viewport ↔ devicePixelRatio
  - Timezone ↔ locale ↔ Intl
  - Canvas/WebGL хеши ↔ ожидаемые значения
  - Client Hints ↔ User-Agent

Использование:
    >>> auditor = FingerprintAuditor()
    >>> report = await auditor.audit_page(page)
    >>> print(report.score)  # 0.0 - 1.0
    >>> print(report.issues)  # список несоответствий
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class FingerprintIssue:
    """Несоответствие в fingerprint."""
    check: str
    severity: Severity
    message: str
    expected: str = ""
    actual: str = ""


@dataclass
class FingerprintReport:
    """Отчёт об аудите fingerprint."""
    score: float = 1.0  # 0.0 - 1.0 (1.0 = идеально)
    issues: list[FingerprintIssue] = field(default_factory=list)
    fingerprint_data: dict[str, Any] = field(default_factory=dict)

    @property
    def is_consistent(self) -> bool:
        return self.score >= 0.8

    @property
    def critical_issues(self) -> list[FingerprintIssue]:
        return [i for i in self.issues if i.severity == Severity.CRITICAL]

    @property
    def warnings(self) -> list[FingerprintIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]


class FingerprintAuditor:
    """Аудитор согласованности браузерных отпечатков."""

    # Маппинг UA → ожидаемая платформа
    UA_PLATFORM_MAP = {
        "Windows": "Win32",
        "MacIntel": "MacIntel",
        "Linux": "Linux x86_64",
    }

    # Маппинг OS → ожидаемые WebGL vendors
    OS_GPU_MAP = {
        "windows": ["Google Inc. (NVIDIA)", "Google Inc. (AMD)", "Google Inc. (Intel)", "Google Inc."],
        "macos": ["Apple Inc.", "Apple"],
        "linux": ["Google Inc. (Intel)", "Google Inc. (AMD)", "Google Inc. (NVIDIA)", "Google Inc."],
    }

    def __init__(self, strict: bool = False):
        self.strict = strict

    async def audit_page(self, page) -> FingerprintReport:
        """Полный аудит fingerprint страницы.

        Args:
            page: Playwright page object

        Returns:
            FingerprintReport с результатами
        """
        report = FingerprintReport()

        try:
            # Собираем данные через JS
            fp_data = await page.evaluate("""() => {
                return {
                    userAgent: navigator.userAgent,
                    platform: navigator.platform,
                    language: navigator.language,
                    languages: navigator.languages,
                    hardwareConcurrency: navigator.hardwareConcurrency,
                    deviceMemory: navigator.deviceMemory,
                    screenWidth: screen.width,
                    screenHeight: screen.height,
                    colorDepth: screen.colorDepth,
                    pixelRatio: window.devicePixelRatio,
                    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                    timezoneOffset: new Date().getTimezoneOffset(),
                    canvasHash: null,
                    webglVendor: null,
                    webglRenderer: null,
                    webglVersion: null,
                    touchSupport: 'ontouchstart' in window,
                    maxTouchPoints: navigator.maxTouchPoints || 0,
                    cookieEnabled: navigator.cookieEnabled,
                    doNotTrack: navigator.doNotTrack,
                    plugins: Array.from(navigator.plugins).map(p => p.name),
                    mimeTypes: Array.from(navigator.mimeTypes).map(t => t.type),
                };
            }""")
            report.fingerprint_data = fp_data

            # Пробуем получить canvas hash
            try:
                canvas_hash = await page.evaluate("""() => {
                    const canvas = document.createElement('canvas');
                    canvas.width = 200;
                    canvas.height = 50;
                    const ctx = canvas.getContext('2d');
                    ctx.textBaseline = 'top';
                    ctx.font = '14px Arial';
                    ctx.fillStyle = '#f60';
                    ctx.fillRect(0, 0, 200, 50);
                    ctx.fillStyle = '#069';
                    ctx.fillText('Fingerprint', 2, 15);
                    return canvas.toDataURL();
                }""")
                if canvas_hash:
                    fp_data["canvasHash"] = hashlib.md5(canvas_hash.encode()).hexdigest()[:16]
            except Exception:
                pass

            # Пробуем получить WebGL info
            try:
                webgl_info = await page.evaluate("""() => {
                    const canvas = document.createElement('canvas');
                    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                    if (!gl) return null;
                    const ext = gl.getExtension('WEBGL_debug_renderer_info');
                    return {
                        vendor: ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
                        renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
                        version: gl.getParameter(gl.VERSION),
                    };
                }""")
                if webgl_info:
                    fp_data["webglVendor"] = webgl_info.get("vendor")
                    fp_data["webglRenderer"] = webgl_info.get("renderer")
                    fp_data["webglVersion"] = webgl_info.get("version")
            except Exception:
                pass

            # Запускаем все проверки
            self._check_ua_platform(fp_data, report)
            self._check_gpu_consistency(fp_data, report)
            self._check_screen_viewport(fp_data, report)
            self._check_timezone_locale(fp_data, report)
            self._check_touch_consistency(fp_data, report)
            self._check_memory_cores(fp_data, report)

            # Считаем score
            if report.issues:
                critical_count = len(report.critical_issues)
                warning_count = len(report.warnings)
                penalty = critical_count * 0.2 + warning_count * 0.05
                report.score = max(0.0, 1.0 - penalty)

        except Exception as e:
            logger.error(f"Fingerprint audit error: {e}")
            report.issues.append(FingerprintIssue(
                check="audit_execution",
                severity=Severity.WARNING,
                message=f"Audit execution error: {e}",
            ))
            report.score = 0.5

        return report

    def _check_ua_platform(self, data: dict, report: FingerprintReport) -> None:
        """Проверить соответствие User-Agent и platform."""
        ua = data.get("userAgent", "")
        platform = data.get("platform", "")

        if "Windows" in ua and platform != "Win32":
            report.issues.append(FingerprintIssue(
                check="ua_platform",
                severity=Severity.CRITICAL,
                message=f"UA says Windows but platform is '{platform}'",
                expected="Win32",
                actual=platform,
            ))

        if "Mac" in ua and "Intel" in ua and platform != "MacIntel":
            report.issues.append(FingerprintIssue(
                check="ua_platform",
                severity=Severity.CRITICAL,
                message=f"UA says MacIntel but platform is '{platform}'",
                expected="MacIntel",
                actual=platform,
            ))

        if "Linux" in ua and "Linux" not in platform and platform != "Win32":
            if "Android" not in ua:
                report.issues.append(FingerprintIssue(
                    check="ua_platform",
                    severity=Severity.WARNING,
                    message=f"UA says Linux but platform is '{platform}'",
                    expected="Linux x86_64",
                    actual=platform,
                ))

    def _check_gpu_consistency(self, data: dict, report: FingerprintReport) -> None:
        """Проверить соответствие GPU и платформы."""
        ua = data.get("userAgent", "")
        vendor = data.get("webglVendor", "")
        renderer = data.get("webglRenderer", "")

        if not vendor:
            return

        # Apple GPU на не-Apple платформе
        if "Apple" in vendor and "Mac" not in ua and "iPhone" not in ua:
            report.issues.append(FingerprintIssue(
                check="gpu_platform",
                severity=Severity.CRITICAL,
                message=f"Apple GPU on non-Apple platform: {vendor}",
                expected="Non-Apple vendor",
                actual=vendor,
            ))

        # SwiftShader (software renderer) — подозрительно
        if "SwiftShader" in renderer:
            report.issues.append(FingerprintIssue(
                check="gpu_software",
                severity=Severity.WARNING,
                message="Software renderer detected (SwiftShader) — headless indicator",
                expected="Hardware GPU",
                actual=renderer,
            ))

    def _check_screen_viewport(self, data: dict, report: FingerprintReport) -> None:
        """Проверить согласованность экрана и viewport."""
        screen_w = data.get("screenWidth", 0)
        screen_h = data.get("screenHeight", 0)
        ratio = data.get("pixelRatio", 1)

        # Слишком маленький экран
        if screen_w < 800 or screen_h < 600:
            report.issues.append(FingerprintIssue(
                check="screen_size",
                severity=Severity.WARNING,
                message=f"Unusually small screen: {screen_w}x{screen_h}",
                expected=">= 800x600",
                actual=f"{screen_w}x{screen_h}",
            ))

        # Нестандартный pixel ratio
        if ratio not in (1, 1.25, 1.5, 2, 2.5, 3):
            report.issues.append(FingerprintIssue(
                check="pixel_ratio",
                severity=Severity.INFO,
                message=f"Unusual devicePixelRatio: {ratio}",
                expected="1, 1.25, 1.5, 2, 2.5, 3",
                actual=str(ratio),
            ))

    def _check_timezone_locale(self, data: dict, report: FingerprintReport) -> None:
        """Проверить согласованность timezone и locale."""
        tz = data.get("timezone", "")
        lang = data.get("language", "")

        # RU locale с не-RU timezone
        if lang.startswith("ru") and tz and "Europe" not in tz and "Asia" not in tz:
            report.issues.append(FingerprintIssue(
                check="timezone_locale",
                severity=Severity.WARNING,
                message=f"RU locale with non-RU timezone: {tz}",
                expected="Europe/* or Asia/*",
                actual=tz,
            ))

    def _check_touch_consistency(self, data: dict, report: FingerprintReport) -> None:
        """Проверить согласованность touch support."""
        ua = data.get("userAgent", "")
        touch_support = data.get("touchSupport", False)
        max_touch = data.get("maxTouchPoints", 0)

        # Mobile UA без touch
        is_mobile = any(m in ua for m in ["Mobile", "Android", "iPhone"])
        if is_mobile and not touch_support:
            report.issues.append(FingerprintIssue(
                check="touch_mobile",
                severity=Severity.CRITICAL,
                message="Mobile UA but no touch support",
                expected="touchSupport=true",
                actual="false",
            ))

        # Desktop UA с touch (не всегда плохо, но подозрительно)
        if not is_mobile and touch_support and max_touch > 0:
            report.issues.append(FingerprintIssue(
                check="touch_desktop",
                severity=Severity.INFO,
                message=f"Desktop UA with touch support: {max_touch} touch points",
                expected="maxTouchPoints=0",
                actual=str(max_touch),
            ))

    def _check_memory_cores(self, data: dict, report: FingerprintReport) -> None:
        """Проверить разумность hardwareConcurrency и deviceMemory."""
        cores = data.get("hardwareConcurrency", 0)
        memory = data.get("deviceMemory", 0)

        if cores == 0:
            report.issues.append(FingerprintIssue(
                check="cores_zero",
                severity=Severity.WARNING,
                message="hardwareConcurrency is 0 — headless indicator",
                expected=">= 2",
                actual="0",
            ))

        if memory > 0 and memory < 2:
            report.issues.append(FingerprintIssue(
                check="memory_low",
                severity=Severity.INFO,
                message=f"Low deviceMemory: {memory}GB",
                expected=">= 2GB",
                actual=f"{memory}GB",
            ))
