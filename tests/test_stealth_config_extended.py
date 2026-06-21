"""
Расширенные тесты для StealthConfig.

Покрывает:
  - StealthConfig фабрики: minimal(), standard(), advanced(), full()
  - get_scripts() — корректность списка скриптов по уровням
  - get_user_agent() — random_ua=True/False
  - enabled=False — пустой список скриптов
  - _level_name() внутренняя функция
"""

from __future__ import annotations

from lab_playwright_kit.stealth import StealthConfig


# ─── Фабрика minimal() ────────────────────────────────────────────────────


class TestStealthConfigMinimal:
    def test_disabled_by_default_flags(self):
        cfg = StealthConfig.minimal()
        assert cfg.enabled is True
        assert cfg.mask_webdriver is True
        assert cfg.mask_plugins is False
        assert cfg.mask_languages is False
        assert cfg.fake_chrome is False
        assert cfg.fake_permissions is False
        assert cfg.fake_webgl is False

    def test_no_advanced_flags(self):
        cfg = StealthConfig.minimal()
        assert cfg.mask_vendor is False
        assert cfg.fake_csi is False
        assert cfg.fake_loadtimes is False
        assert cfg.fake_hardware is False
        assert cfg.block_webrtc is False
        assert cfg.random_ua is False

    def test_get_scripts_only_webdriver(self):
        cfg = StealthConfig.minimal()
        scripts = cfg.get_scripts()
        assert len(scripts) == 1


# ─── Фабрика standard() ──────────────────────────────────────────────────


class TestStealthConfigStandard:
    def test_standard_has_six_flags(self):
        cfg = StealthConfig.standard()
        assert cfg.mask_webdriver is True
        assert cfg.mask_plugins is True
        assert cfg.mask_languages is True
        assert cfg.fake_chrome is True
        assert cfg.fake_permissions is True
        assert cfg.fake_webgl is True

    def test_standard_no_advanced(self):
        cfg = StealthConfig.standard()
        assert cfg.mask_vendor is False
        assert cfg.fake_csi is False
        assert cfg.block_webrtc is False
        assert cfg.random_ua is False

    def test_get_scripts_returns_six(self):
        cfg = StealthConfig.standard()
        scripts = cfg.get_scripts()
        assert len(scripts) == 6


# ─── Фабрика advanced() ──────────────────────────────────────────────────


class TestStealthConfigAdvanced:
    def test_advanced_includes_standard(self):
        cfg = StealthConfig.advanced()
        assert cfg.mask_webdriver is True
        assert cfg.mask_plugins is True
        assert cfg.mask_languages is True
        assert cfg.fake_chrome is True
        assert cfg.fake_permissions is True
        assert cfg.fake_webgl is True

    def test_advanced_has_p0_flags(self):
        cfg = StealthConfig.advanced()
        assert cfg.mask_vendor is True
        assert cfg.fake_csi is True
        assert cfg.fake_loadtimes is True
        assert cfg.fake_hardware is True
        assert cfg.fake_dimensions is True
        assert cfg.fake_device_memory is True
        assert cfg.screen_depth is True
        assert cfg.media_codecs is True
        assert cfg.mask_iframe is True
        assert cfg.block_webrtc is True
        assert cfg.spoof_audio is True
        assert cfg.spoof_client_hints is True

    def test_advanced_no_random_ua(self):
        cfg = StealthConfig.advanced()
        assert cfg.random_ua is False

    def test_get_scripts_returns_18(self):
        cfg = StealthConfig.advanced()
        scripts = cfg.get_scripts()
        # 6 standard + 12 advanced = 18
        assert len(scripts) == 18


# ─── Фабрика full() ──────────────────────────────────────────────────────


class TestStealthConfigFull:
    def test_full_includes_advanced(self):
        cfg = StealthConfig.full()
        assert cfg.block_webrtc is True
        assert cfg.spoof_audio is True
        assert cfg.spoof_client_hints is True

    def test_full_has_random_ua(self):
        cfg = StealthConfig.full()
        assert cfg.random_ua is True

    def test_full_has_all_flags(self):
        cfg = StealthConfig.full()
        assert cfg.mask_webdriver is True
        assert cfg.mask_plugins is True
        assert cfg.mask_languages is True
        assert cfg.fake_chrome is True
        assert cfg.fake_permissions is True
        assert cfg.fake_webgl is True
        assert cfg.mask_vendor is True
        assert cfg.fake_csi is True
        assert cfg.fake_loadtimes is True
        assert cfg.fake_hardware is True
        assert cfg.fake_dimensions is True
        assert cfg.fake_device_memory is True
        assert cfg.screen_depth is True
        assert cfg.media_codecs is True
        assert cfg.mask_iframe is True
        assert cfg.block_webrtc is True
        assert cfg.spoof_audio is True
        assert cfg.spoof_client_hints is True
        assert cfg.random_ua is True

    def test_full_get_scripts_18(self):
        cfg = StealthConfig.full()
        scripts = cfg.get_scripts()
        # random_ua doesn't add a script, still 18
        assert len(scripts) == 18


# ─── get_user_agent() ────────────────────────────────────────────────────


class TestGetUserAgent:
    def test_no_random_ua_returns_none(self):
        cfg = StealthConfig.standard()
        assert cfg.get_user_agent() is None

    def test_random_ua_returns_string(self):
        cfg = StealthConfig.full()
        ua = cfg.get_user_agent()
        assert isinstance(ua, str)
        assert len(ua) > 0

    def test_random_ua_from_realistic_list(self):
        cfg = StealthConfig.full()
        from lab_playwright_kit.stealth import REALISTIC_UAS

        for _ in range(10):
            ua = cfg.get_user_agent()
            assert ua in REALISTIC_UAS

    def test_random_ua_varies(self):
        cfg = StealthConfig.full()
        uas = {cfg.get_user_agent() for _ in range(20)}
        # Should have at least 2 different UAs in 20 tries
        assert len(uas) >= 2


# ─── enabled=False ──────────────────────────────────────────────────────


class TestDisabledConfig:
    def test_get_scripts_empty(self):
        cfg = StealthConfig(enabled=False)
        assert cfg.get_scripts() == []

    def test_enabled_true_has_scripts(self):
        cfg = StealthConfig(enabled=True)
        scripts = cfg.get_scripts()
        assert len(scripts) > 0


# ─── Ручная конфигурация ─────────────────────────────────────────────────


class TestCustomConfig:
    def test_custom_flags(self):
        cfg = StealthConfig(
            enabled=True,
            mask_webdriver=True,
            mask_plugins=False,
            mask_languages=True,
            fake_chrome=False,
            fake_permissions=False,
            fake_webgl=False,
        )
        scripts = cfg.get_scripts()
        # webdriver + languages = 2
        assert len(scripts) == 2

    def test_all_flags_false(self):
        cfg = StealthConfig(
            enabled=True,
            mask_webdriver=False,
            mask_plugins=False,
            mask_languages=False,
            fake_chrome=False,
            fake_permissions=False,
            fake_webgl=False,
        )
        assert cfg.get_scripts() == []


# ─── _level_name ─────────────────────────────────────────────────────────


class TestLevelName:
    def test_full_level(self):
        from lab_playwright_kit.stealth import _level_name

        cfg = StealthConfig.full()
        assert _level_name(cfg) == "full"

    def test_advanced_level(self):
        from lab_playwright_kit.stealth import _level_name

        cfg = StealthConfig.advanced()
        assert _level_name(cfg) == "advanced"

    def test_standard_level(self):
        from lab_playwright_kit.stealth import _level_name

        cfg = StealthConfig.standard()
        assert _level_name(cfg) == "standard"

    def test_minimal_level(self):
        from lab_playwright_kit.stealth import _level_name

        cfg = StealthConfig.minimal()
        assert _level_name(cfg) == "minimal"

    def test_disabled_level(self):
        from lab_playwright_kit.stealth import _level_name

        cfg = StealthConfig(enabled=False)
        assert _level_name(cfg) == "disabled"

    def test_custom_level(self):
        from lab_playwright_kit.stealth import _level_name

        # Custom: enabled but none of the level-detecting flags set
        cfg = StealthConfig(
            enabled=True,
            mask_webdriver=False,
            fake_webgl=False,
            block_webrtc=False,
            random_ua=False,
        )
        assert _level_name(cfg) == "custom"
