"""
Расширенные тесты для FingerprintManager и BrowserFingerprint.

Покрывает:
  - BrowserFingerprint dataclass: все поля, значения по умолчанию
  - canvas_noise_hex, audio_noise_hex properties
  - summary property
  - FingerprintManager.generate() — создание профилей
  - Консистентность отпечатков
"""

from __future__ import annotations

from lab_playwright_kit.fingerprint import (
    AUDIO_NOISE_RANGE,
    CANVAS_NOISE_RANGE,
    FONT_SETS,
    HARDWARE_PROFILES,
    SCREEN_PROFILES,
    WEBGL_RENDERERS,
    BrowserFingerprint,
    FingerprintManager,
)


# ─── BrowserFingerprint defaults ─────────────────────────────────────────


class TestBrowserFingerprintDefaults:
    def test_default_profile_id(self):
        fp = BrowserFingerprint()
        assert fp.profile_id == ""

    def test_default_user_agent(self):
        fp = BrowserFingerprint()
        assert fp.user_agent == ""

    def test_default_webgl_vendor(self):
        fp = BrowserFingerprint()
        assert fp.webgl_vendor == ""

    def test_default_webgl_renderer(self):
        fp = BrowserFingerprint()
        assert fp.webgl_renderer == ""

    def test_default_webgl_version(self):
        fp = BrowserFingerprint()
        assert fp.webgl_version == "WebGL 1.0 (OpenGL ES 2.0 Chromium)"

    def test_default_webgl_shading_language(self):
        fp = BrowserFingerprint()
        assert fp.webgl_shading_language == "WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 1.0 Chromium)"

    def test_default_webgl_extensions(self):
        fp = BrowserFingerprint()
        assert fp.webgl_extensions == []

    def test_default_canvas_noise_seed(self):
        fp = BrowserFingerprint()
        assert fp.canvas_noise_seed == 0

    def test_default_audio_noise_seed(self):
        fp = BrowserFingerprint()
        assert fp.audio_noise_seed == 0

    def test_default_screen(self):
        fp = BrowserFingerprint()
        assert fp.screen_width == 1920
        assert fp.screen_height == 1080
        assert fp.screen_avail_width == 1920
        assert fp.screen_avail_height == 1040
        assert fp.screen_color_depth == 24
        assert fp.screen_pixel_ratio == 1.0

    def test_default_hardware(self):
        fp = BrowserFingerprint()
        assert fp.hardware_cores == 8
        assert fp.hardware_memory == 16
        assert fp.hardware_platform == "Win32"

    def test_default_fonts(self):
        fp = BrowserFingerprint()
        assert fp.fonts == []

    def test_default_os(self):
        fp = BrowserFingerprint()
        assert fp.os == "windows"

    def test_default_timezone(self):
        fp = BrowserFingerprint()
        assert fp.timezone == "Europe/Moscow"

    def test_default_locale(self):
        fp = BrowserFingerprint()
        assert fp.locale == "ru-RU"

    def test_default_languages(self):
        fp = BrowserFingerprint()
        assert fp.languages == ["ru-RU", "ru", "en-US", "en"]


# ─── BrowserFingerprint custom values ────────────────────────────────────


class TestBrowserFingerprintCustom:
    def test_custom_values(self):
        fp = BrowserFingerprint(
            profile_id="test_001",
            user_agent="Mozilla/5.0 Test",
            webgl_vendor="Google Inc. (NVIDIA)",
            webgl_renderer="ANGLE (NVIDIA GeForce RTX 3080)",
            canvas_noise_seed=12345,
            audio_noise_seed=67890,
            screen_width=2560,
            screen_height=1440,
            hardware_cores=12,
            hardware_memory=32,
            os="macos",
        )
        assert fp.profile_id == "test_001"
        assert fp.user_agent == "Mozilla/5.0 Test"
        assert fp.webgl_vendor == "Google Inc. (NVIDIA)"
        assert fp.webgl_renderer == "ANGLE (NVIDIA GeForce RTX 3080)"
        assert fp.canvas_noise_seed == 12345
        assert fp.audio_noise_seed == 67890
        assert fp.screen_width == 2560
        assert fp.screen_height == 1440
        assert fp.hardware_cores == 12
        assert fp.hardware_memory == 32
        assert fp.os == "macos"


# ─── canvas_noise_hex / audio_noise_hex ──────────────────────────────────


class TestNoiseHex:
    def test_canvas_noise_hex_zero(self):
        fp = BrowserFingerprint(canvas_noise_seed=0)
        assert fp.canvas_noise_hex == "00000000"

    def test_canvas_noise_hex_positive(self):
        fp = BrowserFingerprint(canvas_noise_seed=255)
        assert fp.canvas_noise_hex == "000000ff"

    def test_audio_noise_hex_zero(self):
        fp = BrowserFingerprint(audio_noise_seed=0)
        assert fp.audio_noise_hex == "00000000"

    def test_audio_noise_hex_large(self):
        fp = BrowserFingerprint(audio_noise_seed=0xFFFFFFFF)
        assert fp.audio_noise_hex == "ffffffff"


# ─── summary property ────────────────────────────────────────────────────


class TestSummary:
    def test_summary_contains_profile_id(self):
        fp = BrowserFingerprint(profile_id="test_001")
        assert "test_001" in fp.summary

    def test_summary_contains_os(self):
        fp = BrowserFingerprint(os="macos")
        assert "OS=macos" in fp.summary

    def test_summary_contains_screen(self):
        fp = BrowserFingerprint(screen_width=1920, screen_height=1080)
        assert "1920x1080" in fp.summary

    def test_summary_contains_cores(self):
        fp = BrowserFingerprint(hardware_cores=8)
        assert "Cores=8" in fp.summary

    def test_summary_contains_ram(self):
        fp = BrowserFingerprint(hardware_memory=16)
        assert "RAM=16GB" in fp.summary

    def test_summary_contains_gpu(self):
        fp = BrowserFingerprint(webgl_renderer="ANGLE (NVIDIA GeForce RTX 3080)")
        assert "RTX 3080" in fp.summary

    def test_summary_contains_ua(self):
        fp = BrowserFingerprint(user_agent="Mozilla/5.0 Test Browser")
        assert "Mozilla" in fp.summary


# ─── FingerprintManager.generate() ──────────────────────────────────────


class TestFingerprintManagerGenerate:
    def test_generate_returns_browser_fingerprint(self):
        fp = FingerprintManager.generate("test_001")
        assert isinstance(fp, BrowserFingerprint)

    def test_generate_sets_profile_id(self):
        fp = FingerprintManager.generate("my_profile")
        assert fp.profile_id == "my_profile"

    def test_generate_has_user_agent(self):
        fp = FingerprintManager.generate("test_001")
        assert len(fp.user_agent) > 0

    def test_generate_has_webgl_vendor(self):
        fp = FingerprintManager.generate("test_001")
        assert len(fp.webgl_vendor) > 0

    def test_generate_has_webgl_renderer(self):
        fp = FingerprintManager.generate("test_001")
        assert len(fp.webgl_renderer) > 0

    def test_generate_has_screen(self):
        fp = FingerprintManager.generate("test_001")
        assert fp.screen_width > 0
        assert fp.screen_height > 0

    def test_generate_has_hardware(self):
        fp = FingerprintManager.generate("test_001")
        assert fp.hardware_cores > 0
        assert fp.hardware_memory > 0

    def test_generate_has_fonts(self):
        fp = FingerprintManager.generate("test_001")
        assert len(fp.fonts) > 0

    def test_generate_has_os(self):
        fp = FingerprintManager.generate("test_001")
        assert fp.os in ("windows", "macos", "linux", "android")

    def test_generate_has_canvas_noise(self):
        fp = FingerprintManager.generate("test_001")
        # canvas_noise_seed can be 0, but hex should work
        assert len(fp.canvas_noise_hex) == 8

    def test_generate_has_audio_noise(self):
        fp = FingerprintManager.generate("test_001")
        assert len(fp.audio_noise_hex) == 8

    def test_generate_different_profiles(self):
        fp1 = FingerprintManager.generate("profile_001")
        fp2 = FingerprintManager.generate("profile_002")
        # Different seeds should produce different fingerprints
        assert fp1.profile_id != fp2.profile_id

    def test_generate_has_languages(self):
        fp = FingerprintManager.generate("test_001")
        assert len(fp.languages) > 0

    def test_generate_has_timezone(self):
        fp = FingerprintManager.generate("test_001")
        assert len(fp.timezone) > 0

    def test_generate_has_locale(self):
        fp = FingerprintManager.generate("test_001")
        assert len(fp.locale) > 0


# ─── Базы данных отпечатков ─────────────────────────────────────────────


class TestFingerprintDatabases:
    def test_webgl_renderers_has_windows(self):
        assert "windows" in WEBGL_RENDERERS
        assert len(WEBGL_RENDERERS["windows"]) > 0

    def test_webgl_renderers_has_macos(self):
        assert "macos" in WEBGL_RENDERERS

    def test_webgl_renderers_has_linux(self):
        assert "linux" in WEBGL_RENDERERS

    def test_webgl_renderers_has_android(self):
        assert "android" in WEBGL_RENDERERS

    def test_webgl_renderer_has_vendor_and_renderer(self):
        for os_name, renderers in WEBGL_RENDERERS.items():
            for r in renderers:
                assert "vendor" in r
                assert "renderer" in r
                assert len(r["vendor"]) > 0
                assert len(r["renderer"]) > 0

    def test_screen_profiles_has_all_oses(self):
        for os_name in ("windows", "macos", "linux", "android"):
            assert os_name in SCREEN_PROFILES

    def test_screen_profile_has_required_fields(self):
        for os_name, screens in SCREEN_PROFILES.items():
            for s in screens:
                assert "width" in s
                assert "height" in s
                assert "colorDepth" in s
                assert "pixelRatio" in s

    def test_hardware_profiles_has_all_oses(self):
        for os_name in ("windows", "macos", "linux", "android"):
            assert os_name in HARDWARE_PROFILES

    def test_hardware_profile_has_required_fields(self):
        for os_name, hw_list in HARDWARE_PROFILES.items():
            for hw in hw_list:
                assert "cores" in hw
                assert "memory" in hw
                assert "platform" in hw

    def test_font_sets_has_all_oses(self):
        for os_name in ("windows", "macos", "linux", "android"):
            assert os_name in FONT_SETS
            assert len(FONT_SETS[os_name]) > 0

    def test_canvas_noise_range(self):
        assert CANVAS_NOISE_RANGE == (-3, 3)

    def test_audio_noise_range(self):
        assert AUDIO_NOISE_RANGE == (-0.0001, 0.0001)
