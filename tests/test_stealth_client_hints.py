"""
Тесты для User-Agent Client Hints spoofing модуля.

Покрывает:
  - ClientHintsData — структура данных
  - ClientHintsConfig — конфигурация и фабричные методы
  - ClientHintsSpoofer — генерация JS-скриптов
  - _parse_user_agent() — парсинг UA-строк
"""
import pytest

from lab_playwright_kit.stealth_client_hints import (
    ClientHintsConfig,
    ClientHintsData,
    ClientHintsSpoofer,
    _parse_user_agent,
)


# ─── ClientHintsData ─────────────────────────────────────────────────────────

class TestClientHintsData:
    def test_default_values(self):
        data = ClientHintsData()
        assert data.brand == "Chromium"
        assert data.major_version == "131"
        assert data.platform == "Windows"
        assert data.mobile is False
        assert data.arch == "x86"
        assert data.bitness == "64"

    def test_custom_values(self):
        data = ClientHintsData(
            brand="Firefox",
            major_version="133",
            platform="Linux",
            mobile=True,
        )
        assert data.brand == "Firefox"
        assert data.major_version == "133"
        assert data.platform == "Linux"
        assert data.mobile is True

    def test_brands_list(self):
        data = ClientHintsData()
        assert len(data.brands) >= 1
        assert data.brands[0]["brand"] == "Chromium"

    def test_full_brands_list(self):
        data = ClientHintsData()
        assert len(data.full_brands) >= 1


# ─── ClientHintsConfig ───────────────────────────────────────────────────────

class TestClientHintsConfig:
    def test_default_config(self):
        config = ClientHintsConfig()
        assert isinstance(config.hints, ClientHintsData)
        assert config.override_ua is False
        assert config.spoof_high_entropy is True

    def test_chrome_windows(self):
        config = ClientHintsConfig.chrome_windows("131")
        assert config.hints.brand == "Google Chrome"
        assert config.hints.major_version == "131"
        assert config.hints.platform == "Windows"
        assert config.hints.mobile is False

    def test_chrome_macos(self):
        config = ClientHintsConfig.chrome_macos("131")
        assert config.hints.brand == "Google Chrome"
        assert config.hints.platform == "macOS"

    def test_firefox_windows(self):
        config = ClientHintsConfig.firefox_windows("133")
        assert config.hints.brand == "Firefox"
        assert config.hints.major_version == "133"
        assert config.hints.platform == "Windows"

    def test_from_user_agent_chrome(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        config = ClientHintsConfig.from_user_agent(ua)
        assert config.hints.brand == "Google Chrome"
        assert config.hints.major_version == "131"
        assert config.hints.platform == "Windows"

    def test_from_user_agent_firefox(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"
        config = ClientHintsConfig.from_user_agent(ua)
        assert config.hints.brand == "Firefox"
        assert config.hints.major_version == "133"

    def test_from_user_agent_edge(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
        config = ClientHintsConfig.from_user_agent(ua)
        assert config.hints.brand == "Microsoft Edge"

    def test_from_user_agent_macos(self):
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        config = ClientHintsConfig.from_user_agent(ua)
        assert config.hints.platform == "macOS"

    def test_from_user_agent_android(self):
        ua = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
        config = ClientHintsConfig.from_user_agent(ua)
        assert config.hints.platform == "Android"
        assert config.hints.mobile is True

    def test_from_user_agent_iphone(self):
        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        config = ClientHintsConfig.from_user_agent(ua)
        assert config.hints.platform == "iOS"
        assert config.hints.mobile is True
        assert config.hints.model == "iPhone"


# ─── _parse_user_agent() ────────────────────────────────────────────────────

class TestParseUserAgent:
    def test_chrome_windows(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        data = _parse_user_agent(ua)
        assert data.brand == "Google Chrome"
        assert data.major_version == "131"
        assert data.platform == "Windows"
        assert data.bitness == "64"

    def test_firefox_windows(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"
        data = _parse_user_agent(ua)
        assert data.brand == "Firefox"
        assert data.major_version == "133"

    def test_unknown_ua(self):
        ua = "SomeUnknownBrowser/1.0"
        data = _parse_user_agent(ua)
        # Должны вернуться defaults
        assert isinstance(data, ClientHintsData)

    def test_arch_detection_x64(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        data = _parse_user_agent(ua)
        assert data.arch == "x86"
        assert data.bitness == "64"

    def test_arch_detection_arm(self):
        ua = "Mozilla/5.0 (Linux; arm64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        data = _parse_user_agent(ua)
        assert data.arch == "arm"
        assert data.bitness == "64"


# ─── ClientHintsSpoofer ─────────────────────────────────────────────────────

class TestClientHintsSpoofer:
    def test_get_script_chrome(self):
        config = ClientHintsConfig.chrome_windows("131")
        script = ClientHintsSpoofer.get_script(config)
        assert isinstance(script, str)
        assert len(script) > 0
        assert "userAgentData" in script

    def test_get_script_firefox(self):
        config = ClientHintsConfig.firefox_windows("133")
        script = ClientHintsSpoofer.get_script(config)
        assert isinstance(script, str)
        assert "Firefox" in script

    def test_script_contains_brands(self):
        config = ClientHintsConfig.chrome_windows("131")
        script = ClientHintsSpoofer.get_script(config)
        assert "brands" in script
        assert "Chromium" in script

    def test_script_contains_platform(self):
        config = ClientHintsConfig.chrome_windows("131")
        script = ClientHintsSpoofer.get_script(config)
        assert "Windows" in script

    def test_script_contains_getHighEntropyValues(self):
        config = ClientHintsConfig.chrome_windows("131")
        script = ClientHintsSpoofer.get_script(config)
        assert "getHighEntropyValues" in script

    def test_script_wraps_iife(self):
        config = ClientHintsConfig.chrome_windows("131")
        script = ClientHintsSpoofer.get_script(config)
        assert script.startswith("(function()")
        assert script.endswith("})();")

    def test_different_configs_different_scripts(self):
        config1 = ClientHintsConfig.chrome_windows("131")
        config2 = ClientHintsConfig.firefox_windows("133")
        script1 = ClientHintsSpoofer.get_script(config1)
        script2 = ClientHintsSpoofer.get_script(config2)
        assert script1 != script2
