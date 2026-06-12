"""
Тесты для StealthScorer — оценка уровня скрытности браузера.
"""
import pytest

from lab_playwright_kit.stealth_score import (
    RiskLevel, StealthCheck, StealthScoreResult, StealthScorer,
)


class TestRiskLevel:
    def test_values(self):
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.CRITICAL.value == "critical"


class TestStealthCheck:
    def test_passed(self):
        c = StealthCheck("wd", True, 1.0, 0.2, RiskLevel.LOW, "ok")
        assert c.passed and c.score == 1.0

    def test_failed(self):
        c = StealthCheck("wd", False, 0.0, 0.2, RiskLevel.CRITICAL, "det", "fix it")
        assert not c.passed and c.recommendation == "fix it"


class TestStealthScoreResult:
    def test_default(self):
        r = StealthScoreResult()
        assert r.score == 1.0 and r.passed_checks == 0

    def test_passed_count(self):
        r = StealthScoreResult(checks=[
            StealthCheck("a", True, 1.0, 0.2, RiskLevel.LOW),
            StealthCheck("b", False, 0.0, 0.2, RiskLevel.CRITICAL),
        ])
        assert r.passed_checks == 1 and r.total_checks == 2

    def test_summary(self):
        r = StealthScoreResult(checks=[
            StealthCheck("a", True, 1.0, 0.2, RiskLevel.LOW),
            StealthCheck("b", False, 0.0, 0.2, RiskLevel.CRITICAL),
        ])
        assert "1/2 checks passed" in r.summary


class TestStealthScorer:
    def test_init(self):
        assert StealthScorer() is not None

    def test_webdriver_detected(self):
        c = StealthScorer()._check_webdriver({"webdriver": True})
        assert not c.passed and c.risk == RiskLevel.CRITICAL

    def test_webdriver_ok(self):
        c = StealthScorer()._check_webdriver({"webdriver": False})
        assert c.passed and c.score == 1.0

    def test_plugins_zero(self):
        c = StealthScorer()._check_plugins({"plugins": []})
        assert not c.passed and c.risk == RiskLevel.HIGH

    def test_plugins_ok(self):
        c = StealthScorer()._check_plugins({"plugins": [{"name": f"P{i}"} for i in range(3)]})
        assert c.passed and c.score == 1.0

    def test_languages_empty(self):
        c = StealthScorer()._check_languages({"languages": []})
        assert not c.passed

    def test_languages_ok(self):
        c = StealthScorer()._check_languages({"languages": ["ru-RU"]})
        assert c.passed

    def test_webgl_none(self):
        c = StealthScorer()._check_webgl({"webgl": None})
        assert not c.passed and c.risk == RiskLevel.HIGH

    def test_webgl_swiftshader(self):
        c = StealthScorer()._check_webgl({"webgl": {"vendor": "Google Inc.", "renderer": "SwiftShader"}})
        assert not c.passed and c.risk == RiskLevel.CRITICAL

    def test_webgl_real_gpu(self):
        c = StealthScorer()._check_webgl({"webgl": {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, GeForce RTX 3080)"}})
        assert c.passed and c.score == 1.0

    def test_canvas_none(self):
        c = StealthScorer()._check_canvas({"canvas": None})
        assert not c.passed

    def test_canvas_ok(self):
        c = StealthScorer()._check_canvas({"canvas": "data:image/png;base64,..."})
        assert c.passed

    def test_screen_zero(self):
        c = StealthScorer()._check_screen({"screen": {"width": 0, "height": 0, "availWidth": 0, "availHeight": 0}})
        assert not c.passed

    def test_screen_normal(self):
        c = StealthScorer()._check_screen({"screen": {"width": 1920, "height": 1080, "availWidth": 1920, "availHeight": 1040}})
        assert c.passed and c.score == 1.0

    def test_weights_sum(self):
        assert abs(sum(StealthScorer.CHECK_WEIGHTS.values()) - 1.0) < 0.01

    def test_all_weights(self):
        expected = {"webdriver", "plugins", "languages", "permissions", "webgl", "canvas", "screen", "headers", "behavior"}
        assert set(StealthScorer.CHECK_WEIGHTS.keys()) == expected
