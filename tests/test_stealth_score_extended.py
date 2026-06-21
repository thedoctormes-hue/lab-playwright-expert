"""
Расширенные тесты для StealthScorer и data classes.

Покрывает:
  - RiskLevel enum
  - StealthCheck dataclass
  - StealthScoreResult (passed_checks, total_checks, summary)
  - StealthScorer.CHECK_WEIGHTS
  - StealthScorer._check_webdriver
  - StealthScorer._check_plugins
  - StealthScorer._check_languages
  - StealthScorer._check_webgl
  - StealthScorer._check_canvas
  - StealthScorer._check_screen
"""

from __future__ import annotations

from lab_playwright_kit.stealth_score import (
    RiskLevel,
    StealthCheck,
    StealthScorer,
    StealthScoreResult,
)


# ─── RiskLevel ─────────────────────────────────────────────────────────────


class TestRiskLevel:
    def test_values(self):
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_str_enum(self):
        assert RiskLevel.LOW == "low"
        assert RiskLevel.HIGH == "high"


# ─── StealthCheck ──────────────────────────────────────────────────────────


class TestStealthCheck:
    def test_defaults(self):
        c = StealthCheck(
            name="webdriver",
            passed=True,
            score=1.0,
            weight=0.2,
            risk=RiskLevel.LOW,
        )
        assert c.name == "webdriver"
        assert c.passed is True
        assert c.score == 1.0
        assert c.weight == 0.2
        assert c.risk == RiskLevel.LOW
        assert c.message == ""
        assert c.recommendation == ""

    def test_all_fields(self):
        c = StealthCheck(
            name="plugins",
            passed=False,
            score=0.0,
            weight=0.1,
            risk=RiskLevel.HIGH,
            message="No plugins",
            recommendation="Apply stealth plugin",
        )
        assert c.message == "No plugins"
        assert c.recommendation == "Apply stealth plugin"


# ─── StealthScoreResult ────────────────────────────────────────────────────


class TestStealthScoreResult:
    def test_defaults(self):
        r = StealthScoreResult()
        assert r.score == 1.0
        assert r.risk_level == RiskLevel.LOW
        assert r.checks == []
        assert r.recommendations == []
        assert r.raw_data == {}

    def test_passed_checks(self):
        r = StealthScoreResult(
            checks=[
                StealthCheck(name="a", passed=True, score=1.0, weight=0.1, risk=RiskLevel.LOW),
                StealthCheck(name="b", passed=False, score=0.0, weight=0.1, risk=RiskLevel.HIGH),
                StealthCheck(name="c", passed=True, score=0.8, weight=0.1, risk=RiskLevel.LOW),
            ]
        )
        assert r.passed_checks == 2
        assert r.total_checks == 3

    def test_total_checks_empty(self):
        r = StealthScoreResult()
        assert r.total_checks == 0
        assert r.passed_checks == 0

    def test_summary(self):
        r = StealthScoreResult(
            score=0.85,
            risk_level=RiskLevel.LOW,
            checks=[
                StealthCheck(name="a", passed=True, score=1.0, weight=0.1, risk=RiskLevel.LOW),
                StealthCheck(name="b", passed=False, score=0.0, weight=0.1, risk=RiskLevel.HIGH),
            ],
        )
        s = r.summary
        assert "0.85" in s
        assert "low" in s
        assert "1/2" in s


# ─── StealthScorer CHECK_WEIGHTS ──────────────────────────────────────────


class TestStealthScorerWeights:
    def test_all_weights_sum(self):
        total = sum(StealthScorer.CHECK_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01

    def test_has_all_checks(self):
        expected = {
            "webdriver",
            "plugins",
            "languages",
            "permissions",
            "webgl",
            "canvas",
            "screen",
            "headers",
            "behavior",
        }
        assert set(StealthScorer.CHECK_WEIGHTS.keys()) == expected

    def test_webdriver_highest_weight(self):
        w = StealthScorer.CHECK_WEIGHTS
        assert w["webdriver"] == 0.20
        assert w["webdriver"] >= max(v for k, v in w.items() if k != "webdriver")


# ─── StealthScorer._check_webdriver ───────────────────────────────────────


class TestCheckWebdriver:
    def test_pass(self):
        scorer = StealthScorer()
        check = scorer._check_webdriver({"webdriver": None})
        assert check.passed is True
        assert check.score == 1.0
        assert check.risk == RiskLevel.LOW

    def test_fail(self):
        scorer = StealthScorer()
        check = scorer._check_webdriver({"webdriver": True})
        assert check.passed is False
        assert check.score == 0.0
        assert check.risk == RiskLevel.CRITICAL
        assert "stealth patch" in check.recommendation

    def test_missing_key(self):
        scorer = StealthScorer()
        check = scorer._check_webdriver({})
        assert check.passed is True


# ─── StealthScorer._check_plugins ─────────────────────────────────────────


class TestCheckPlugins:
    def test_no_plugins(self):
        scorer = StealthScorer()
        check = scorer._check_plugins({"plugins": []})
        assert check.passed is False
        assert check.score == 0.2
        assert check.risk == RiskLevel.HIGH

    def test_one_plugin(self):
        scorer = StealthScorer()
        check = scorer._check_plugins({"plugins": [{"name": "Chrome PDF"}]})
        assert check.passed is True
        assert check.score == 0.6
        assert check.risk == RiskLevel.MEDIUM

    def test_many_plugins(self):
        scorer = StealthScorer()
        plugins = [{"name": f"Plugin {i}"} for i in range(5)]
        check = scorer._check_plugins({"plugins": plugins})
        assert check.passed is True
        assert check.score == 1.0
        assert check.risk == RiskLevel.LOW


# ─── StealthScorer._check_languages ───────────────────────────────────────


class TestCheckLanguages:
    def test_ok(self):
        scorer = StealthScorer()
        check = scorer._check_languages({"languages": ["ru", "en"]})
        assert check.passed is True
        assert check.score == 1.0

    def test_empty(self):
        scorer = StealthScorer()
        check = scorer._check_languages({"languages": []})
        assert check.passed is False
        assert check.score == 0.3

    def test_missing(self):
        scorer = StealthScorer()
        check = scorer._check_languages({})
        assert check.passed is False


# ─── StealthScorer._check_webgl ───────────────────────────────────────────


class TestCheckWebgl:
    def test_no_webgl(self):
        scorer = StealthScorer()
        check = scorer._check_webgl({"webgl": None})
        assert check.passed is False
        assert check.score == 0.3

    def test_swiftshader(self):
        scorer = StealthScorer()
        check = scorer._check_webgl({"webgl": {"vendor": "Google", "renderer": "SwiftShader"}})
        assert check.passed is False
        assert check.score == 0.1
        assert check.risk == RiskLevel.CRITICAL

    def test_llvmpipe(self):
        scorer = StealthScorer()
        check = scorer._check_webgl({"webgl": {"vendor": "Google", "renderer": "llvmpipe"}})
        assert check.passed is False
        assert check.score == 0.1

    def test_real_gpu(self):
        scorer = StealthScorer()
        check = scorer._check_webgl(
            {"webgl": {"vendor": "Google Inc.", "renderer": "NVIDIA GeForce GTX 1080"}}
        )
        assert check.passed is True
        assert check.score == 1.0

    def test_generic_vendor(self):
        scorer = StealthScorer()
        check = scorer._check_webgl({"webgl": {"vendor": "Google Inc.", "renderer": "ANGLE"}})
        assert check.passed is True
        assert check.score == 0.7
        assert check.risk == RiskLevel.MEDIUM


# ─── StealthScorer._check_canvas ──────────────────────────────────────────


class TestCheckCanvas:
    def test_ok(self):
        scorer = StealthScorer()
        check = scorer._check_canvas({"canvas": "data:image/png;base64,..."})
        assert check.passed is True
        assert check.score == 0.9

    def test_missing(self):
        scorer = StealthScorer()
        check = scorer._check_canvas({"canvas": None})
        assert check.passed is False
        assert check.score == 0.3


# ─── StealthScorer._check_screen ──────────────────────────────────────────


class TestCheckScreen:
    def test_zero_dimensions(self):
        scorer = StealthScorer()
        check = scorer._check_screen({"screen": {"width": 0, "height": 0}})
        assert check.passed is False
        assert check.score == 0.2

    def test_no_taskbar(self):
        scorer = StealthScorer()
        check = scorer._check_screen(
            {
                "screen": {
                    "width": 1920,
                    "height": 1080,
                    "availWidth": 1920,
                    "availHeight": 1080,
                }
            }
        )
        assert check.passed is True
        assert check.score == 0.7

    def test_with_taskbar(self):
        scorer = StealthScorer()
        check = scorer._check_screen(
            {
                "screen": {
                    "width": 1920,
                    "height": 1080,
                    "availWidth": 1920,
                    "availHeight": 1040,
                }
            }
        )
        assert check.passed is True
        assert check.score == 1.0
