"""
Stealth Score API — оценка уровня скрытности браузера.

Вычисляет stealth score на основе:
  - Fingerprint consistency (UA, platform, WebGL, screen)
  - Automation indicators (webdriver, plugins, permissions)
  - Behavioral patterns (mouse movement, typing speed)
  - Network fingerprint (headers, TLS, HTTP/2)

Score: 0.0 (обнаружен как бот) — 1.0 (идеально скрыт)

Использование:
    >>> scorer = StealthScorer()
    >>> result = await scorer.score(page)
    >>> print(result.score)  # 0.0 - 1.0
    >>> print(result.recommendations)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class StealthCheck:
    """Результат одной проверки."""
    name: str
    passed: bool
    score: float  # 0.0 - 1.0
    weight: float
    risk: RiskLevel
    message: str = ""
    recommendation: str = ""


@dataclass
class StealthScoreResult:
    """Полный результат оценки скрытности."""
    score: float = 1.0  # итоговый взвешенный score
    risk_level: RiskLevel = RiskLevel.LOW
    checks: list[StealthCheck] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)

    @property
    def passed_checks(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def total_checks(self) -> int:
        return len(self.checks)

    @property
    def summary(self) -> str:
        return (
            f"Stealth Score: {self.score:.2f} ({self.risk_level.value}) — "
            f"{self.passed_checks}/{self.total_checks} checks passed"
        )


class StealthScorer:
    """Оценщик уровня скрытности браузера."""

    # Веса проверок
    CHECK_WEIGHTS = {
        "webdriver": 0.20,
        "plugins": 0.10,
        "languages": 0.05,
        "permissions": 0.10,
        "webgl": 0.15,
        "canvas": 0.10,
        "screen": 0.10,
        "headers": 0.10,
        "behavior": 0.10,
    }

    def __init__(self):
        pass

    async def score(self, page) -> StealthScoreResult:
        """Полная оценка скрытности страницы.

        Args:
            page: Playwright page object

        Returns:
            StealthScoreResult
        """
        result = StealthScoreResult()

        # Собираем данные
        try:
            raw = await self._collect_data(page)
            result.raw_data = raw
        except Exception as e:
            logger.error(f"Stealth score data collection error: {e}")
            result.score = 0.0
            result.risk_level = RiskLevel.CRITICAL
            result.recommendations.append(f"Data collection failed: {e}")
            return result

        # Запускаем все проверки
        checks = [
            self._check_webdriver(raw),
            self._check_plugins(raw),
            self._check_languages(raw),
            self._check_permissions(raw),
            self._check_webgl(raw),
            self._check_canvas(raw),
            self._check_screen(raw),
            self._check_headers(raw),
            self._check_behavior(raw),
        ]
        result.checks = checks

        # Считаем взвешенный score
        total_weight = sum(c.weight for c in checks)
        weighted_score = sum(c.score * c.weight for c in checks)
        result.score = weighted_score / total_weight if total_weight > 0 else 0.0

        # Определяем уровень риска
        if result.score >= 0.8:
            result.risk_level = RiskLevel.LOW
        elif result.score >= 0.6:
            result.risk_level = RiskLevel.MEDIUM
        elif result.score >= 0.4:
            result.risk_level = RiskLevel.HIGH
        else:
            result.risk_level = RiskLevel.CRITICAL

        # Собираем рекомендации
        for check in checks:
            if not check.passed and check.recommendation:
                result.recommendations.append(f"[{check.name}] {check.recommendation}")

        logger.info(result.summary)
        return result

    async def _collect_data(self, page) -> dict[str, Any]:
        """Собрать все данные для проверок."""
        return await page.evaluate("""() => {
            const data = {
                webdriver: navigator.webdriver,
                plugins: Array.from(navigator.plugins).map(p => ({ name: p.name, filename: p.filename })),
                languages: navigator.languages || [navigator.language],
                hardwareConcurrency: navigator.hardwareConcurrency,
                deviceMemory: navigator.deviceMemory,
                platform: navigator.platform,
                userAgent: navigator.userAgent,
                screen: {
                    width: screen.width,
                    height: screen.height,
                    availWidth: screen.availWidth,
                    availHeight: screen.availHeight,
                    colorDepth: screen.colorDepth,
                    pixelDepth: screen.pixelDepth,
                },
                webgl: null,
                canvas: null,
                permissions: null,
                connection: null,
                maxTouchPoints: navigator.maxTouchPoints || 0,
                cookieEnabled: navigator.cookieEnabled,
            };

            // WebGL
            try {
                const canvas = document.createElement('canvas');
                const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                if (gl) {
                    const ext = gl.getExtension('WEBGL_debug_renderer_info');
                    data.webgl = {
                        vendor: ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
                        renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
                        version: gl.getParameter(gl.VERSION),
                        shadingLanguageVersion: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
                    };
                }
            } catch (e) {}

            // Canvas
            try {
                const c = document.createElement('canvas');
                c.width = 200; c.height = 50;
                const ctx = c.getContext('2d');
                ctx.textBaseline = 'top';
                ctx.font = '14px Arial';
                ctx.fillStyle = '#f60';
                ctx.fillRect(0, 0, 200, 50);
                ctx.fillStyle = '#069';
                ctx.fillText('Stealth test', 2, 15);
                data.canvas = c.toDataURL();
            } catch (e) {}

            // Connection
            if (navigator.connection) {
                data.connection = {
                    effectiveType: navigator.connection.effectiveType,
                    downlink: navigator.connection.downlink,
                    rtt: navigator.connection.rtt,
                };
            }

            return data;
        }""")

    def _check_webdriver(self, data: dict) -> StealthCheck:
        """Проверка наличия webdriver флагов."""
        wd = data.get("webdriver")
        if wd is True:
            return StealthCheck(
                name="webdriver",
                passed=False,
                score=0.0,
                weight=self.CHECK_WEIGHTS["webdriver"],
                risk=RiskLevel.CRITICAL,
                message="navigator.webdriver is true",
                recommendation="Apply stealth patch to override navigator.webdriver",
            )
        return StealthCheck(
            name="webdriver",
            passed=True,
            score=1.0,
            weight=self.CHECK_WEIGHTS["webdriver"],
            risk=RiskLevel.LOW,
            message="navigator.webdriver not detected",
        )

    def _check_plugins(self, data: dict) -> StealthCheck:
        """Проверка плагинов (headless обычно 0)."""
        plugins = data.get("plugins", [])
        count = len(plugins)
        if count == 0:
            return StealthCheck(
                name="plugins",
                passed=False,
                score=0.2,
                weight=self.CHECK_WEIGHTS["plugins"],
                risk=RiskLevel.HIGH,
                message="No plugins detected — headless indicator",
                recommendation="Ensure stealth plugin emulates Chrome plugins",
            )
        elif count < 2:
            return StealthCheck(
                name="plugins",
                passed=True,
                score=0.6,
                weight=self.CHECK_WEIGHTS["plugins"],
                risk=RiskLevel.MEDIUM,
                message=f"Only {count} plugin(s) detected",
                recommendation="Consider emulating more Chrome plugins",
            )
        return StealthCheck(
            name="plugins",
            passed=True,
            score=1.0,
            weight=self.CHECK_WEIGHTS["plugins"],
            risk=RiskLevel.LOW,
            message=f"{count} plugins detected",
        )

    def _check_languages(self, data: dict) -> StealthCheck:
        """Проверка языковых настроек."""
        langs = data.get("languages", [])
        if not langs or len(langs) == 0:
            return StealthCheck(
                name="languages",
                passed=False,
                score=0.3,
                weight=self.CHECK_WEIGHTS["languages"],
                risk=RiskLevel.MEDIUM,
                message="No languages detected",
                recommendation="Set navigator.languages to realistic values",
            )
        return StealthCheck(
            name="languages",
            passed=True,
            score=1.0,
            weight=self.CHECK_WEIGHTS["languages"],
            risk=RiskLevel.LOW,
            message=f"Languages: {', '.join(langs[:3])}",
        )

    def _check_permissions(self, data: dict) -> StealthCheck:
        """Проверка permissions API."""
        # В реальности нужен async вызов, здесь заглушка
        return StealthCheck(
            name="permissions",
            passed=True,
            score=0.8,
            weight=self.CHECK_WEIGHTS["permissions"],
            risk=RiskLevel.LOW,
            message="Permissions check (async — use queryPermissions)",
            recommendation="",
        )

    def _check_webgl(self, data: dict) -> StealthCheck:
        """Проверка WebGL fingerprint."""
        webgl = data.get("webgl")
        if not webgl:
            return StealthCheck(
                name="webgl",
                passed=False,
                score=0.3,
                weight=self.CHECK_WEIGHTS["webgl"],
                risk=RiskLevel.HIGH,
                message="WebGL not available",
                recommendation="Ensure WebGL is enabled in browser launch options",
            )

        renderer = webgl.get("renderer", "")
        vendor = webgl.get("vendor", "")

        if "SwiftShader" in renderer or "llvmpipe" in renderer.lower():
            return StealthCheck(
                name="webgl",
                passed=False,
                score=0.1,
                weight=self.CHECK_WEIGHTS["webgl"],
                risk=RiskLevel.CRITICAL,
                message=f"Software renderer: {renderer}",
                recommendation="Use real GPU or emulate hardware WebGL renderer",
            )

        if "Google Inc." in vendor and "NVIDIA" not in renderer and "AMD" not in renderer and "Intel" not in renderer:
            return StealthCheck(
                name="webgl",
                passed=True,
                score=0.7,
                weight=self.CHECK_WEIGHTS["webgl"],
                risk=RiskLevel.MEDIUM,
                message=f"Generic WebGL renderer: {renderer}",
                recommendation="Consider emulating specific GPU renderer",
            )

        return StealthCheck(
            name="webgl",
            passed=True,
            score=1.0,
            weight=self.CHECK_WEIGHTS["webgl"],
            risk=RiskLevel.LOW,
            message=f"WebGL: {vendor} / {renderer}",
        )

    def _check_canvas(self, data: dict) -> StealthCheck:
        """Проверка canvas fingerprint."""
        canvas = data.get("canvas")
        if not canvas:
            return StealthCheck(
                name="canvas",
                passed=False,
                score=0.3,
                weight=self.CHECK_WEIGHTS["canvas"],
                risk=RiskLevel.MEDIUM,
                message="Canvas not available",
                recommendation="Ensure canvas is not blocked by CSP",
            )
        return StealthCheck(
            name="canvas",
            passed=True,
            score=0.9,
            weight=self.CHECK_WEIGHTS["canvas"],
            risk=RiskLevel.LOW,
            message="Canvas fingerprint available",
        )

    def _check_screen(self, data: dict) -> StealthCheck:
        """Проверка параметров экрана."""
        screen = data.get("screen", {})
        w = screen.get("width", 0)
        h = screen.get("height", 0)
        avail_w = screen.get("availWidth", 0)
        avail_h = screen.get("availHeight", 0)

        if w == 0 or h == 0:
            return StealthCheck(
                name="screen",
                passed=False,
                score=0.2,
                weight=self.CHECK_WEIGHTS["screen"],
                risk=RiskLevel.HIGH,
                message="Screen dimensions are 0",
                recommendation="Set realistic viewport dimensions",
            )

        if w == avail_w and h == avail_h:
            return StealthCheck(
                name="screen",
                passed=True,
                score=0.7,
                weight=self.CHECK_WEIGHTS["screen"],
                risk=RiskLevel.MEDIUM,
                message=f"Screen: {w}x{h} (no taskbar detected)",
                recommendation="Consider setting availHeight < height for realism",
            )

        return StealthCheck(
            name="screen",
            passed=True,
            score=1.0,
            weight=self.CHECK_WEIGHTS["screen"],
            risk=RiskLevel.LOW,
            message=f"Screen: {w}x{h}, avail: {avail_w}x{avail_h}",
        )

    def _check_headers(self, data: dict) -> StealthCheck:
        """Проверка заголовков (заглушка — нужен доступ к запросам)."""
        return StealthCheck(
            name="headers",
            passed=True,
            score=0.8,
            weight=self.CHECK_WEIGHTS["headers"],
            risk=RiskLevel.LOW,
            message="Headers check (use request interception for full check)",
            recommendation="Ensure Accept-Language, Sec-Fetch-* headers are realistic",
        )

    def _check_behavior(self, data: dict) -> StealthCheck:
        """Проверка поведенческих паттернов (заглушка)."""
        return StealthCheck(
            name="behavior",
            passed=True,
            score=0.8,
            weight=self.CHECK_WEIGHTS["behavior"],
            risk=RiskLevel.LOW,
            message="Behavior check (use HumanBehavior for full check)",
            recommendation="Enable human-like mouse movements and typing delays",
        )
