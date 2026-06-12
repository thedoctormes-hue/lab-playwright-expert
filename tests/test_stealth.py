"""
Тесты для stealth.py — антидетект конфигурация.

Покрывает:
  - StealthConfig: создание, пресеты (minimal/standard/advanced/full), get_scripts(), get_user_agent()
  - STEALTH_SCRIPTS: наличие всех ключей, непустые скрипты
  - REALISTIC_UAS: наличие, формат
  - apply_stealth: вызов с разными конфигурациями
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from lab_playwright_kit.stealth import (
    REALISTIC_UAS,
    STEALTH_SCRIPTS,
    StealthConfig,
    _level_name,
    apply_stealth,
)


# ─── STEALTH_SCRIPTS ─────────────────────────────────────────────────────────

class TestStealthScripts:
    """Тесты словаря STEALTH_SCRIPTS."""

    def test_all_keys_present(self):
        """Все ожидаемые ключи присутствуют."""
        expected_keys = [
            "webdriver", "plugins", "languages", "chrome_runtime",
            "permissions", "webgl", "navigator_vendor", "chrome_csi",
            "chrome_loadtimes", "hardware_concurrency", "outer_dimensions",
            "device_memory", "screen_depth", "media_codecs",
            "iframe_content_window", "webrtc_leak", "audio_spoof",
            "client_hints",
        ]
        for key in expected_keys:
            assert key in STEALTH_SCRIPTS, f"Missing key: {key}"

    def test_scripts_non_empty(self):
        """Все скрипты непустые."""
        for key, script in STEALTH_SCRIPTS.items():
            assert len(script.strip()) > 0, f"Empty script: {key}"

    def test_webdriver_script_content(self):
        """webdriver скрипт содержит определение."""
        assert "webdriver" in STEALTH_SCRIPTS["webdriver"]
        assert "undefined" in STEALTH_SCRIPTS["webdriver"]

    def test_plugins_script_content(self):
        """plugins скрипт содержит плагины."""
        assert "Chrome PDF Plugin" in STEALTH_SCRIPTS["plugins"]

    def test_languages_script_content(self):
        """languages скрипт содержит ru-RU."""
        assert "ru-RU" in STEALTH_SCRIPTS["languages"]

    def test_webrtc_script_content(self):
        """webrtc_leak содержит RTCPeerConnection."""
        assert "RTCPeerConnection" in STEALTH_SCRIPTS["webrtc_leak"]

    def test_script_count(self):
        """Не менее 18 скриптов."""
        assert len(STEALTH_SCRIPTS) >= 18


# ─── REALISTIC_UAS ──────────────────────────────────────────────────────────

class TestRealisticUAs:
    """Тесты списка User-Agent строк."""

    def test_not_empty(self):
        assert len(REALISTIC_UAS) > 0

    def test_all_strings(self):
        """Все элементы — непустые строки."""
        for ua in REALISTIC_UAS:
            assert isinstance(ua, str)
            assert len(ua) > 0

    def test_contains_chrome(self):
        """Есть Chrome UA."""
        assert any("Chrome" in ua for ua in REALISTIC_UAS)

    def test_contains_firefox(self):
        """Есть Firefox UA."""
        assert any("Firefox" in ua for ua in REALISTIC_UAS)

    def test_contains_mozilla(self):
        """Все начинаются с Mozilla/5.0."""
        for ua in REALISTIC_UAS:
            assert ua.startswith("Mozilla/5.0"), f"Bad UA: {ua}"

    def test_contains_windows_or_mac(self):
        """Есть Windows и macOS."""
        has_windows = any("Windows" in ua for ua in REALISTIC_UAS)
        has_mac = any("Mac" in ua for ua in REALISTIC_UAS)
        assert has_windows or has_mac

    def test_minimum_count(self):
        """Не менее 5 UA."""
        assert len(REALISTIC_UAS) >= 5


# ─── StealthConfig ──────────────────────────────────────────────────────────

class TestStealthConfigDefaults:
    """Тесты значений по умолчанию."""

    def test_default_enabled(self):
        cfg = StealthConfig()
        assert cfg.enabled is True

    def test_default_standard_on(self):
        """Standard флаги включены по умолчанию."""
        cfg = StealthConfig()
        assert cfg.mask_webdriver is True
        assert cfg.mask_plugins is True
        assert cfg.mask_languages is True
        assert cfg.fake_chrome is True
        assert cfg.fake_permissions is True
        assert cfg.fake_webgl is True

    def test_default_advanced_off(self):
        """Advanced флаги выключены по умолчанию."""
        cfg = StealthConfig()
        assert cfg.mask_vendor is False
        assert cfg.fake_csi is False
        assert cfg.block_webrtc is False

    def test_default_random_ua_off(self):
        cfg = StealthConfig()
        assert cfg.random_ua is False


class TestStealthConfigPresets:
    """Тесты пресетов конфигурации."""

    def test_minimal(self):
        cfg = StealthConfig.minimal()
        assert cfg.mask_webdriver is True
        assert cfg.mask_plugins is False
        assert cfg.fake_chrome is False
        assert cfg.fake_webgl is False
        assert cfg.block_webrtc is False
        assert cfg.random_ua is False

    def test_standard(self):
        cfg = StealthConfig.standard()
        assert cfg.mask_webdriver is True
        assert cfg.mask_plugins is True
        assert cfg.mask_languages is True
        assert cfg.fake_chrome is True
        assert cfg.fake_permissions is True
        assert cfg.fake_webgl is True
        # Advanced выключены
        assert cfg.mask_vendor is False
        assert cfg.fake_csi is False
        assert cfg.block_webrtc is False
        assert cfg.random_ua is False

    def test_advanced(self):
        cfg = StealthConfig.advanced()
        assert cfg.mask_webdriver is True
        assert cfg.mask_plugins is True
        assert cfg.fake_chrome is True
        assert cfg.mask_vendor is True
        assert cfg.fake_csi is True
        assert cfg.block_webrtc is True
        assert cfg.spoof_audio is True
        assert cfg.spoof_client_hints is True
        assert cfg.random_ua is False  # advanced без random_ua

    def test_full(self):
        cfg = StealthConfig.full()
        assert cfg.mask_webdriver is True
        assert cfg.block_webrtc is True
        assert cfg.spoof_audio is True
        assert cfg.random_ua is True  # full = advanced + random_ua

    def test_minimal_scripts_count(self):
        """minimal — 1 скрипт (webdriver)."""
        cfg = StealthConfig.minimal()
        scripts = cfg.get_scripts()
        assert len(scripts) == 1

    def test_standard_scripts_count(self):
        """standard — 6 скриптов."""
        cfg = StealthConfig.standard()
        scripts = cfg.get_scripts()
        assert len(scripts) == 6

    def test_advanced_scripts_count(self):
        """advanced — 18 скриптов (все)."""
        cfg = StealthConfig.advanced()
        scripts = cfg.get_scripts()
        assert len(scripts) == 18

    def test_full_scripts_count(self):
        """full — 18 скриптов (random_ua не добавляет скрипт)."""
        cfg = StealthConfig.full()
        scripts = cfg.get_scripts()
        assert len(scripts) == 18

    def test_disabled_scripts_empty(self):
        """enabled=False — пустой список."""
        cfg = StealthConfig(enabled=False)
        assert cfg.get_scripts() == []


class TestStealthConfigGetUserAgent:
    """Тесты get_user_agent()."""

    def test_no_random_ua(self):
        """Без random_ua — None."""
        cfg = StealthConfig()
        assert cfg.get_user_agent() is None

    def test_random_ua_returns_from_list(self):
        """С random_ua — возвращает из REALISTIC_UAS."""
        cfg = StealthConfig(random_ua=True)
        ua = cfg.get_user_agent()
        assert ua in REALISTIC_UAS

    def test_random_ua_returns_string(self):
        """С random_ua — непустая строка."""
        cfg = StealthConfig(random_ua=True)
        ua = cfg.get_user_agent()
        assert isinstance(ua, str)
        assert len(ua) > 0


class TestStealthConfigGetScripts:
    """Тесты get_scripts()."""

    def test_returns_list(self):
        cfg = StealthConfig()
        scripts = cfg.get_scripts()
        assert isinstance(scripts, list)

    def test_all_scripts_from_dict(self):
        """Все скрипты из STEALTH_SCRIPTS."""
        cfg = StealthConfig.advanced()
        scripts = cfg.get_scripts()
        for script in scripts:
            assert script in STEALTH_SCRIPTS.values()

    def test_no_duplicates(self):
        """Нет дубликатов."""
        cfg = StealthConfig.advanced()
        scripts = cfg.get_scripts()
        assert len(scripts) == len(set(scripts))

    def test_custom_config(self):
        """Кастомная конфигурация — webdriver + csi + webgl = 7 скриптов (standard включены по умолчанию)."""
        cfg = StealthConfig(mask_webdriver=True, fake_csi=True, fake_webgl=True)
        scripts = cfg.get_scripts()
        # webdriver, plugins, languages, chrome_runtime, permissions, webgl, csi = 7
        assert len(scripts) == 7


# ─── _level_name ─────────────────────────────────────────────────────────────

class TestLevelName:
    """Тесты _level_name()."""

    def test_disabled(self):
        cfg = StealthConfig(enabled=False)
        assert _level_name(cfg) == "disabled"

    def test_full(self):
        cfg = StealthConfig.full()
        assert _level_name(cfg) == "full"

    def test_advanced(self):
        cfg = StealthConfig.advanced()
        assert _level_name(cfg) == "advanced"

    def test_standard(self):
        cfg = StealthConfig.standard()
        assert _level_name(cfg) == "standard"

    def test_minimal(self):
        cfg = StealthConfig.minimal()
        assert _level_name(cfg) == "minimal"

    def test_custom(self):
        """Кастомная конфигурация без webdriver — 'custom'."""
        cfg = StealthConfig(mask_webdriver=False, fake_csi=False, fake_webgl=False)
        assert _level_name(cfg) == "custom"


# ─── apply_stealth ───────────────────────────────────────────────────────────

class TestApplyStealth:
    """Тесты apply_stealth()."""

    @pytest.mark.asyncio
    async def test_apply_stealth_default(self):
        """apply_stealth с дефолтной конфигурацией."""
        page = AsyncMock()
        page.add_init_script = AsyncMock()
        await apply_stealth(page)
        # full() = 18 скриптов
        assert page.add_init_script.call_count == 18

    @pytest.mark.asyncio
    async def test_apply_stealth_minimal(self):
        """apply_stealth с minimal."""
        page = AsyncMock()
        page.add_init_script = AsyncMock()
        await apply_stealth(page, StealthConfig.minimal())
        assert page.add_init_script.call_count == 1

    @pytest.mark.asyncio
    async def test_apply_stealth_standard(self):
        """apply_stealth с standard."""
        page = AsyncMock()
        page.add_init_script = AsyncMock()
        await apply_stealth(page, StealthConfig.standard())
        assert page.add_init_script.call_count == 6

    @pytest.mark.asyncio
    async def test_apply_stealth_advanced(self):
        """apply_stealth с advanced."""
        page = AsyncMock()
        page.add_init_script = AsyncMock()
        await apply_stealth(page, StealthConfig.advanced())
        assert page.add_init_script.call_count == 18

    @pytest.mark.asyncio
    async def test_apply_stealth_disabled(self):
        """apply_stealth с disabled — 0 скриптов."""
        page = AsyncMock()
        page.add_init_script = AsyncMock()
        await apply_stealth(page, StealthConfig(enabled=False))
        assert page.add_init_script.call_count == 0

    @pytest.mark.asyncio
    async def test_apply_stealth_passes_scripts(self):
        """Скрипты передаются в add_init_script."""
        page = AsyncMock()
        page.add_init_script = AsyncMock()
        await apply_stealth(page, StealthConfig.minimal())
        # Первый вызов — webdriver скрипт
        call_args = page.add_init_script.call_args_list[0]
        assert "webdriver" in call_args[0][0]
