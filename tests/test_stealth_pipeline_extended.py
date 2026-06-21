"""
Расширенные тесты для StealthPipeline.

Покрывает:
  - PipelineResult (summary)
  - StealthPipeline.level() / minimal() / standard() / advanced() / full()
  - StealthPipeline.__init__ (custom configs)
  - StealthPipeline.level_name / stealth_config properties
  - _config_for_level
"""

from __future__ import annotations

import pytest

from lab_playwright_kit.stealth import StealthConfig
from lab_playwright_kit.stealth_pipeline import (
    PipelineResult,
    StealthPipeline,
    _config_for_level,
)


# ─── PipelineResult ────────────────────────────────────────────────────────


class TestPipelineResult:
    def test_defaults(self):
        r = PipelineResult()
        assert r.stealth_scripts == 0
        assert r.audio_applied is False
        assert r.webrtc_applied is False
        assert r.client_hints_applied is False
        assert r.user_agent is None
        assert r.level == "none"

    def test_summary_minimal(self):
        r = PipelineResult(stealth_scripts=5, level="standard")
        s = r.summary
        assert "level=standard" in s
        assert "scripts=5" in s
        assert "audio" not in s
        assert "webrtc" not in s

    def test_summary_full(self):
        r = PipelineResult(
            stealth_scripts=18,
            audio_applied=True,
            webrtc_applied=True,
            client_hints_applied=True,
            level="full",
            user_agent="Mozilla/5.0...",
        )
        s = r.summary
        assert "level=full" in s
        assert "scripts=18" in s
        assert "audio=✓" in s
        assert "webrtc=✓" in s
        assert "client_hints=✓" in s
        assert "ua=" in s


# ─── StealthPipeline factory methods ───────────────────────────────────────


class TestStealthPipelineFactory:
    def test_level_minimal(self):
        p = StealthPipeline.level("minimal")
        assert p._level == "minimal"

    def test_level_standard(self):
        p = StealthPipeline.level("standard")
        assert p._level == "standard"

    def test_level_advanced(self):
        p = StealthPipeline.level("advanced")
        assert p._level == "advanced"

    def test_level_full(self):
        p = StealthPipeline.level("full")
        assert p._level == "full"

    def test_level_invalid(self):
        with pytest.raises(ValueError, match="Unknown stealth level"):
            StealthPipeline.level("ultra")

    def test_minimal(self):
        p = StealthPipeline.minimal()
        assert p._level == "minimal"

    def test_standard(self):
        p = StealthPipeline.standard()
        assert p._level == "standard"

    def test_advanced(self):
        p = StealthPipeline.advanced()
        assert p._level == "advanced"

    def test_full(self):
        p = StealthPipeline.full()
        assert p._level == "full"


# ─── StealthPipeline init ──────────────────────────────────────────────────


class TestStealthPipelineInit:
    def test_default_init(self):
        p = StealthPipeline()
        assert p._level == "advanced"
        assert p._stealth is not None
        assert p._audio is None
        assert p._webrtc is None
        assert p._client_hints is None

    def test_custom_stealth_config(self):
        cfg = StealthConfig.full()
        p = StealthPipeline(stealth=cfg)
        assert p._stealth is cfg

    def test_auto_flags_minimal(self):
        p = StealthPipeline(level="minimal")
        assert p._auto_audio is False
        assert p._auto_webrtc is False
        assert p._auto_client_hints is False

    def test_auto_flags_full(self):
        p = StealthPipeline(level="full")
        assert p._auto_audio is True
        assert p._auto_webrtc is True
        assert p._auto_client_hints is True

    def test_auto_flags_advanced(self):
        p = StealthPipeline(level="advanced")
        assert p._auto_audio is False
        assert p._auto_webrtc is True
        assert p._auto_client_hints is True

    def test_properties(self):
        p = StealthPipeline.level("full")
        assert p.level_name == "full"
        assert p.stealth_config is not None


# ─── _config_for_level ────────────────────────────────────────────────────


class TestConfigForLevel:
    def test_minimal(self):
        cfg = _config_for_level("minimal")
        assert isinstance(cfg, StealthConfig)

    def test_standard(self):
        cfg = _config_for_level("standard")
        assert isinstance(cfg, StealthConfig)

    def test_advanced(self):
        cfg = _config_for_level("advanced")
        assert isinstance(cfg, StealthConfig)

    def test_full(self):
        cfg = _config_for_level("full")
        assert isinstance(cfg, StealthConfig)

    def test_unknown_defaults_advanced(self):
        cfg = _config_for_level("nonexistent")
        assert isinstance(cfg, StealthConfig)
