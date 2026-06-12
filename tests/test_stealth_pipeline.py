"""
Тесты для StealthPipeline — единого антидетект-пайплайна.

Покрывает:
  - Создание пайплайна по уровням (minimal, standard, advanced, full)
  - Кастомная конфигурация
  - PipelineResult
  - Интеграция с BrowserManager
  - Валидация уровней
"""
from __future__ import annotations

import pytest

from lab_playwright_kit.stealth import StealthConfig
from lab_playwright_kit.stealth_audio import AudioConfig
from lab_playwright_kit.stealth_webrtc import WebRTCConfig
from lab_playwright_kit.stealth_client_hints import ClientHintsConfig
from lab_playwright_kit.stealth_pipeline import (
    PipelineResult,
    StealthPipeline,
    _config_for_level,
)


# ─── Тесты создания пайплайна ───────────────────────────────────────────────

class TestStealthPipelineCreation:
    """Тесты создания StealthPipeline."""

    def test_level_minimal(self):
        p = StealthPipeline.level("minimal")
        assert p.level_name == "minimal"
        assert p.stealth_config.mask_webdriver is True
        assert p.stealth_config.mask_plugins is False

    def test_level_standard(self):
        p = StealthPipeline.level("standard")
        assert p.level_name == "standard"
        assert p.stealth_config.mask_plugins is True
        assert p.stealth_config.fake_webgl is True

    def test_level_advanced(self):
        p = StealthPipeline.level("advanced")
        assert p.level_name == "advanced"
        assert p.stealth_config.block_webrtc is True
        assert p.stealth_config.spoof_audio is True

    def test_level_full(self):
        p = StealthPipeline.level("full")
        assert p.level_name == "full"
        assert p.stealth_config.random_ua is True
        assert p.stealth_config.block_webrtc is True

    def test_classmethod_minimal(self):
        p = StealthPipeline.minimal()
        assert p.level_name == "minimal"

    def test_classmethod_standard(self):
        p = StealthPipeline.standard()
        assert p.level_name == "standard"

    def test_classmethod_advanced(self):
        p = StealthPipeline.advanced()
        assert p.level_name == "advanced"

    def test_classmethod_full(self):
        p = StealthPipeline.full()
        assert p.level_name == "full"

    def test_invalid_level_raises(self):
        with pytest.raises(ValueError, match="Unknown stealth level"):
            StealthPipeline.level("ultra")

    def test_custom_stealth_config(self):
        cfg = StealthConfig.advanced()
        p = StealthPipeline(stealth=cfg)
        assert p.stealth_config is cfg

    def test_custom_audio_config(self):
        audio = AudioConfig.full(noise_seed=123)
        p = StealthPipeline(audio=audio)
        assert p._audio is audio

    def test_custom_webrtc_config(self):
        webrtc = WebRTCConfig.block_all()
        p = StealthPipeline(webrtc=webrtc)
        assert p._webrtc is webrtc

    def test_custom_client_hints_config(self):
        ch = ClientHintsConfig.chrome_macos()
        p = StealthPipeline(client_hints=ch)
        assert p._client_hints is ch


# ─── Тесты PipelineResult ────────────────────────────────────────────────────

class TestPipelineResult:
    """Тесты PipelineResult."""

    def test_default_result(self):
        r = PipelineResult()
        assert r.stealth_scripts == 0
        assert r.audio_applied is False
        assert r.webrtc_applied is False
        assert r.client_hints_applied is False
        assert r.user_agent is None
        assert r.level == "none"

    def test_summary_minimal(self):
        r = PipelineResult(level="minimal", stealth_scripts=1)
        s = r.summary
        assert "level=minimal" in s
        assert "scripts=1" in s

    def test_summary_full(self):
        r = PipelineResult(
            level="full",
            stealth_scripts=18,
            audio_applied=True,
            webrtc_applied=True,
            client_hints_applied=True,
        )
        s = r.summary
        assert "level=full" in s
        assert "scripts=18" in s
        assert "audio=✓" in s
        assert "webrtc=✓" in s
        assert "client_hints=✓" in s

    def test_summary_with_ua(self):
        r = PipelineResult(level="full", user_agent="Mozilla/5.0...")
        s = r.summary
        assert "ua=Mozilla/5.0..." in s


# ─── Тесты конфигурации по уровням ──────────────────────────────────────────

class TestConfigForLevel:
    """Тесты _config_for_level."""

    def test_minimal_scripts_count(self):
        cfg = _config_for_level("minimal")
        scripts = cfg.get_scripts()
        assert len(scripts) == 1  # только webdriver

    def test_standard_scripts_count(self):
        cfg = _config_for_level("standard")
        scripts = cfg.get_scripts()
        assert len(scripts) == 6  # webdriver + plugins + languages + chrome + permissions + webgl

    def test_advanced_scripts_count(self):
        cfg = _config_for_level("advanced")
        scripts = cfg.get_scripts()
        assert len(scripts) == 18  # standard + P0 векторы

    def test_full_scripts_count(self):
        cfg = _config_for_level("full")
        scripts = cfg.get_scripts()
        assert len(scripts) == 18  # advanced + random_ua (UA не скрипт)

    def test_unknown_level_defaults_to_advanced(self):
        cfg = _config_for_level("unknown")
        assert cfg.block_webrtc is True  # advanced feature


# ─── Тесты интеграции с BrowserManager ──────────────────────────────────────

class TestBrowserManagerIntegration:
    """Тесты интеграции StealthPipeline с BrowserManager."""

    def test_browser_manager_with_stealth_string(self):
        from lab_playwright_kit.browser import BrowserManager
        bm = BrowserManager(stealth="advanced")
        assert bm._stealth is not None
        assert bm._stealth.level_name == "advanced"

    def test_browser_manager_with_stealth_object(self):
        from lab_playwright_kit.browser import BrowserManager
        pipeline = StealthPipeline.full()
        bm = BrowserManager(stealth=pipeline)
        assert bm._stealth is pipeline

    def test_browser_manager_without_stealth(self):
        from lab_playwright_kit.browser import BrowserManager
        bm = BrowserManager()
        assert bm._stealth is None

    def test_browser_manager_stealth_none_explicit(self):
        from lab_playwright_kit.browser import BrowserManager
        bm = BrowserManager(stealth=None)
        assert bm._stealth is None