"""
Тесты для FingerprintManager и BrowserFingerprint.

Покрывает:
  - BrowserFingerprint: to_dict/from_dict roundtrip, properties, summary
  - FingerprintManager.generate(): все OS/browser комбинации, seed, детерминизм
  - FingerprintManager.generate_many(): 批量ная генерация
  - Валидация данных: типы полей, диапазоны, консистентность
"""
import pytest

from lab_playwright_kit.fingerprint import (
    WEBGL_RENDERERS,
    SCREEN_PROFILES,
    HARDWARE_PROFILES,
    FONT_SETS,
    BrowserFingerprint,
    FingerprintManager,
)


# ─── BrowserFingerprint ─────────────────────────────────────────────────────

class TestBrowserFingerprint:
    """Тесты dataclass BrowserFingerprint."""

    def test_default_creation(self):
        """Создание с дефолтными значениями."""
        fp = BrowserFingerprint()
        assert fp.profile_id == ""
        assert fp.user_agent == ""
        assert fp.os == "windows"
        assert fp.screen_width == 1920
        assert fp.screen_height == 1080
        assert fp.hardware_cores == 8
        assert fp.hardware_memory == 16

    def test_custom_creation(self):
        """Создание с кастомными значениями."""
        fp = BrowserFingerprint(
            profile_id="test_001",
            os="macos",
            screen_width=2560,
            screen_height=1664,
            hardware_cores=12,
            hardware_memory=32,
        )
        assert fp.profile_id == "test_001"
        assert fp.os == "macos"
        assert fp.screen_width == 2560
        assert fp.screen_height == 1664
        assert fp.hardware_cores == 12
        assert fp.hardware_memory == 32

    def test_canvas_noise_hex(self):
        """canvas_noise_hex — 8-символьная hex строка."""
        fp = BrowserFingerprint(canvas_noise_seed=0xDEADBEEF)
        assert fp.canvas_noise_hex == "deadbeef"

    def test_canvas_noise_hex_zero(self):
        """canvas_noise_hex при seed=0."""
        fp = BrowserFingerprint(canvas_noise_seed=0)
        assert fp.canvas_noise_hex == "00000000"

    def test_audio_noise_hex(self):
        """audio_noise_hex — 8-символьная hex строка."""
        fp = BrowserFingerprint(audio_noise_seed=0xCAFEBABE)
        assert fp.audio_noise_hex == "cafebabe"

    def test_to_dict(self):
        """to_dict содержит все поля."""
        fp = BrowserFingerprint(profile_id="test", os="linux")
        d = fp.to_dict()
        assert isinstance(d, dict)
        assert d["profile_id"] == "test"
        assert d["os"] == "linux"
        assert "user_agent" in d
        assert "webgl_vendor" in d
        assert "webgl_renderer" in d
        assert "screen_width" in d
        assert "hardware_cores" in d
        assert "fonts" in d
        assert len(d) == 24  # Все поля dataclass

    def test_from_dict_roundtrip(self):
        """from_dict(to_dict()) — roundtrip сохраняет данные."""
        fp = BrowserFingerprint(
            profile_id="roundtrip",
            os="macos",
            screen_width=3024,
            screen_height=1964,
            canvas_noise_seed=12345,
        )
        d = fp.to_dict()
        fp2 = BrowserFingerprint.from_dict(d)
        assert fp2.profile_id == "roundtrip"
        assert fp2.os == "macos"
        assert fp2.screen_width == 3024
        assert fp2.screen_height == 1964
        assert fp2.canvas_noise_seed == 12345

    def test_from_dict_ignores_extra_keys(self):
        """from_dict игнорирует лишние ключи."""
        d = BrowserFingerprint(profile_id="x").to_dict()
        d["extra_field"] = "should_be_ignored"
        fp = BrowserFingerprint.from_dict(d)
        assert fp.profile_id == "x"
        assert not hasattr(fp, "extra_field")

    def test_summary(self):
        """summary содержит profile_id, OS, GPU, Screen, Cores."""
        fp = BrowserFingerprint(
            profile_id="sum_test",
            os="windows",
            webgl_renderer="ANGLE (NVIDIA GeForce RTX 3080)",
            screen_width=1920,
            screen_height=1080,
            hardware_cores=8,
            hardware_memory=16,
        )
        s = fp.summary
        assert "sum_test" in s
        assert "OS=windows" in s
        assert "1920x1080" in s
        assert "Cores=8" in s

    def test_summary_truncates_long_ua(self):
        """summary обрезает длинный UA."""
        fp = BrowserFingerprint(
            profile_id="long_ua",
            user_agent="A" * 100,
        )
        s = fp.summary
        assert "..." in s

    def test_languages_default(self):
        """Дефолтный languages — ru-RU, ru, en-US, en."""
        fp = BrowserFingerprint()
        assert fp.languages == ["ru-RU", "ru", "en-US", "en"]

    def test_webgl_extensions_default_empty(self):
        """Дефолтный webgl_extensions — пустой список."""
        fp = BrowserFingerprint()
        assert fp.webgl_extensions == []

    def test_fonts_default_empty(self):
        """Дефолтный fonts — пустой список."""
        fp = BrowserFingerprint()
        assert fp.fonts == []


# ─── FingerprintManager.generate() ──────────────────────────────────────────

class TestFingerprintManagerGenerate:
    """Тесты FingerprintManager.generate()."""

    def _validate_fp(self, fp, expected_os=None):
        """Общая валидация отпечатка."""
        assert isinstance(fp, BrowserFingerprint)
        assert fp.profile_id != ""
        assert fp.user_agent != ""
        assert fp.webgl_vendor != ""
        assert fp.webgl_renderer != ""
        assert fp.screen_width > 0
        assert fp.screen_height > 0
        assert fp.screen_color_depth in (24, 30)
        assert fp.hardware_cores > 0
        assert fp.hardware_memory > 0
        assert fp.hardware_platform != ""
        assert len(fp.fonts) > 0
        assert fp.timezone != ""
        assert fp.locale != ""
        assert len(fp.languages) > 0
        if expected_os:
            assert fp.os == expected_os

    def test_generate_windows(self):
        """Генерация для Windows."""
        fp = FingerprintManager.generate("test_win", os="windows")
        self._validate_fp(fp, "windows")
        assert fp.hardware_platform == "Win32"

    def test_generate_macos(self):
        """Генерация для macOS."""
        fp = FingerprintManager.generate("test_mac", os="macos")
        self._validate_fp(fp, "macos")
        assert fp.hardware_platform == "MacIntel"

    def test_generate_linux(self):
        """Generación для Linux."""
        fp = FingerprintManager.generate("test_linux", os="linux")
        self._validate_fp(fp, "linux")
        assert "Linux" in fp.hardware_platform

    def test_generate_android(self):
        """Генерация для Android."""
        fp = FingerprintManager.generate("test_android", os="android")
        self._validate_fp(fp, "android")
        assert "Linux armv81" in fp.hardware_platform

    def test_generate_chrome_browser(self):
        """Генерация с браузером chrome."""
        fp = FingerprintManager.generate("test", os="windows", browser="chrome")
        assert "Chrome" in fp.user_agent or "chromium" in fp.user_agent.lower()

    def test_generate_firefox_browser(self):
        """Генерация с браузером firefox."""
        fp = FingerprintManager.generate("test_ff", os="windows", browser="firefox")
        assert "Firefox" in fp.user_agent

    def test_generate_edge_browser(self):
        """Генерация с браузером edge."""
        fp = FingerprintManager.generate("test_edge", os="windows", browser="edge")
        assert "Edg" in fp.user_agent

    def test_generate_safari_mac(self):
        """Генерация Safari для macOS."""
        fp = FingerprintManager.generate("test_safari", os="macos", browser="safari")
        assert "Safari" in fp.user_agent

    def test_generate_detinistic_with_seed(self):
        """Одинаковый seed → одинаковый отпечаток."""
        fp1 = FingerprintManager.generate("det_test", seed=42)
        fp2 = FingerprintManager.generate("det_test", seed=42)
        assert fp1.user_agent == fp2.user_agent
        assert fp1.webgl_renderer == fp2.webgl_renderer
        assert fp1.screen_width == fp2.screen_width
        assert fp1.canvas_noise_seed == fp2.canvas_noise_seed
        assert fp1.hardware_cores == fp2.hardware_cores

    def test_generate_detinistic_with_profile_name(self):
        """Одинаковый profile_name → одинаковый отпечаток (seed из имени)."""
        fp1 = FingerprintManager.generate("same_name", os="windows")
        fp2 = FingerprintManager.generate("same_name", os="windows")
        assert fp1.user_agent == fp2.user_agent
        assert fp1.webgl_renderer == fp2.webgl_renderer
        assert fp1.canvas_noise_seed == fp2.canvas_noise_seed

    def test_generate_unique_per_name(self):
        """Разные имена → разные отпечатки."""
        fp1 = FingerprintManager.generate("name_a", os="windows")
        fp2 = FingerprintManager.generate("name_b", os="windows")
        assert fp1.canvas_noise_seed != fp2.canvas_noise_seed

    def test_generate_unique_per_call_without_name(self):
        """Без profile_name — каждый вызов уникален."""
        fp1 = FingerprintManager.generate()
        fp2 = FingerprintManager.generate()
        assert fp1.canvas_noise_seed != fp2.canvas_noise_seed

    def test_generate_webgl_from_database(self):
        """WebGL renderer из базы данных."""
        fp = FingerprintManager.generate("test", os="windows")
        valid_renderers = {r["renderer"] for r in WEBGL_RENDERERS["windows"]}
        assert fp.webgl_renderer in valid_renderers

    def test_generate_screen_from_database(self):
        """Screen из базы данных."""
        fp = FingerprintManager.generate("test", os="macos")
        valid_resolutions = {(s["width"], s["height"]) for s in SCREEN_PROFILES["macos"]}
        assert (fp.screen_width, fp.screen_height) in valid_resolutions

    def test_generate_hardware_from_database(self):
        """Hardware из базы данных."""
        fp = FingerprintManager.generate("test", os="linux")
        valid_configs = {(h["cores"], h["memory"]) for h in HARDWARE_PROFILES["linux"]}
        assert (fp.hardware_cores, fp.hardware_memory) in valid_configs

    def test_generate_fonts_from_database(self):
        """Fonts из базы данных."""
        fp = FingerprintManager.generate("test", os="windows")
        valid_fonts = set(FONT_SETS["windows"])
        for font in fp.fonts:
            assert font in valid_fonts

    def test_generate_webgl_extensions_populated(self):
        """webgl_extensions не пустой список."""
        fp = FingerprintManager.generate("test")
        assert len(fp.webgl_extensions) > 0
        assert "WEBGL_debug_renderer_info" in fp.webgl_extensions

    def test_generate_brand_version_set(self):
        """brand_version установлен для chrome."""
        fp = FingerprintManager.generate("test", browser="chrome")
        assert "Chromium" in fp.brand_version or "Google Chrome" in fp.brand_version

    def test_generate_profile_id_auto(self):
        """Без profile_name — автоматический profile_id."""
        fp = FingerprintManager.generate()
        assert fp.profile_id.startswith("fp_")

    def test_generate_all_presets(self):
        """Все пресеты из PROFILE_PRESETS генерируются без ошибок."""
        for preset_name in FingerprintManager.PROFILE_PRESETS:
            fp = FingerprintManager.generate(
                profile_name=f"test_{preset_name}",
                **FingerprintManager.PROFILE_PRESETS[preset_name],
            )
            self._validate_fp(fp)

    def test_generate_android_screen_large(self):
        """Android экраны всегда портретные (width < height)."""
        for _ in range(10):
            fp = FingerprintManager.generate("android_test", os="android")
            assert fp.screen_width < fp.screen_height or fp.screen_width == fp.screen_height

    def test_generate_screen_pixel_ratio_positive(self):
        """pixelRatio всегда положительный."""
        for _ in range(20):
            fp = FingerprintManager.generate()
            assert fp.screen_pixel_ratio > 0

    def test_generate_canvas_noise_seed_range(self):
        """canvas_noise_seed в диапазоне 0..2^32."""
        for _ in range(20):
            fp = FingerprintManager.generate()
            assert 0 <= fp.canvas_noise_seed <= 2**32


# ─── FingerprintManager.generate_many() ─────────────────────────────────────

class TestFingerprintManagerGenerateMany:
    """Тесты FingerprintManager.generate_many()."""

    def test_generate_many_count(self):
        """generate_many возвращает правильное количество."""
        fps = FingerprintManager.generate_many(5, preset="chrome_win")
        assert len(fps) == 5

    def test_generate_many_unique(self):
        """Все отпечатки уникальны."""
        fps = FingerprintManager.generate_many(10, preset="chrome_win")
        seeds = {fp.canvas_noise_seed for fp in fps}
        assert len(seeds) == 10

    def test_generate_many_names(self):
        """Имена профилей: prefix_0000, prefix_0001, ..."""
        fps = FingerprintManager.generate_many(3, prefix="agent")
        assert fps[0].profile_id == "agent_0000"
        assert fps[1].profile_id == "agent_0001"
        assert fps[2].profile_id == "agent_0002"

    def test_generate_many_empty(self):
        """generate_many(0) — пустой список."""
        fps = FingerprintManager.generate_many(0)
        assert fps == []

    def test_generate_many_preset_macos(self):
        """generate_many с preset chrome_mac."""
        fps = FingerprintManager.generate_many(3, preset="chrome_mac")
        for fp in fps:
            assert fp.os == "macos"


# ─── Базы данных ────────────────────────────────────────────────────────────

class TestDatabases:
    """Валидация баз данных отпечатков."""

    def test_webgl_renderers_all_os(self):
        """WEBGL_RENDERERS содержит все 4 ОС."""
        assert set(WEBGL_RENDERERS.keys()) == {"windows", "macos", "linux", "android"}
        for os_name, renderers in WEBGL_RENDERERS.items():
            assert len(renderers) > 0
            for r in renderers:
                assert "vendor" in r
                assert "renderer" in r
                assert len(r["vendor"]) > 0
                assert len(r["renderer"]) > 0

    def test_screen_profiles_all_os(self):
        """SCREEN_PROFILES содержит все 4 ОС."""
        assert set(SCREEN_PROFILES.keys()) == {"windows", "macos", "linux", "android"}
        for os_name, screens in SCREEN_PROFILES.items():
            assert len(screens) > 0
            for s in screens:
                assert s["width"] > 0
                assert s["height"] > 0
                assert s["colorDepth"] > 0
                assert s["pixelRatio"] > 0

    def test_hardware_profiles_all_os(self):
        """HARDWARE_PROFILES содержит все 4 ОС."""
        assert set(HARDWARE_PROFILES.keys()) == {"windows", "macos", "linux", "android"}
        for os_name, hw_list in HARDWARE_PROFILES.items():
            assert len(hw_list) > 0
            for hw in hw_list:
                assert hw["cores"] > 0
                assert hw["memory"] > 0
                assert len(hw["platform"]) > 0

    def test_font_sets_all_os(self):
        """FONT_SETS содержит все 4 ОС."""
        assert set(FONT_SETS.keys()) == {"windows", "macos", "linux", "android"}
        for os_name, fonts in FONT_SETS.items():
            assert len(fonts) > 0
