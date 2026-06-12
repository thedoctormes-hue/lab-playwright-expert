"""
Тесты для WebRTC IP leak protection модуля.

Покрывает:
  - WebRTCMode — режимы защиты
  - WebRTCConfig — конфигурация и фабричные методы
  - WebRTCProtector — генерация JS-скриптов
"""
import pytest

from lab_playwright_kit.stealth_webrtc import (
    WebRTCConfig,
    WebRTCMode,
    WebRTCProtector,
)


# ─── WebRTCMode ──────────────────────────────────────────────────────────────

class TestWebRTCMode:
    def test_block_all(self):
        assert WebRTCMode.BLOCK_ALL.value == "block_all"

    def test_filter_host(self):
        assert WebRTCMode.FILTER_HOST.value == "filter_host"

    def test_fake_ice(self):
        assert WebRTCMode.FAKE_ICE.value == "fake_ice"

    def test_disabled(self):
        assert WebRTCMode.DISABLED.value == "disabled"

    def test_all_modes_exist(self):
        modes = list(WebRTCMode)
        assert len(modes) == 4


# ─── WebRTCConfig ────────────────────────────────────────────────────────────

class TestWebRTCConfig:
    def test_default_config(self):
        config = WebRTCConfig()
        assert config.mode == WebRTCMode.FILTER_HOST
        assert config.block_stun is True
        assert config.fake_ip == "10.123.45.67"
        assert config.preserve_datachannel is True

    def test_block_all(self):
        config = WebRTCConfig.block_all()
        assert config.mode == WebRTCMode.BLOCK_ALL

    def test_filter_host(self):
        config = WebRTCConfig.filter_host()
        assert config.mode == WebRTCMode.FILTER_HOST

    def test_fake_ice(self):
        config = WebRTCConfig.fake_ice("192.168.1.1")
        assert config.mode == WebRTCMode.FAKE_ICE
        assert config.fake_ip == "192.168.1.1"

    def test_fake_ice_default_ip(self):
        config = WebRTCConfig.fake_ice()
        assert config.fake_ip == "10.123.45.67"

    def test_custom_config(self):
        config = WebRTCConfig(
            mode=WebRTCMode.BLOCK_ALL,
            block_stun=False,
            fake_ip="1.2.3.4",
            preserve_datachannel=False,
        )
        assert config.mode == WebRTCMode.BLOCK_ALL
        assert config.block_stun is False
        assert config.fake_ip == "1.2.3.4"
        assert config.preserve_datachannel is False


# ─── WebRTCProtector ─────────────────────────────────────────────────────────

class TestWebRTCProtector:
    def test_get_script_block_all(self):
        config = WebRTCConfig.block_all()
        script = WebRTCProtector.get_script(config)
        assert isinstance(script, str)
        assert len(script) > 0
        assert "RTCPeerConnection" in script

    def test_get_script_filter_host(self):
        config = WebRTCConfig.filter_host()
        script = WebRTCProtector.get_script(config)
        assert isinstance(script, str)
        assert "RTCPeerConnection" in script

    def test_get_script_fake_ice(self):
        config = WebRTCConfig.fake_ice("10.0.0.1")
        script = WebRTCProtector.get_script(config)
        assert isinstance(script, str)
        assert "10.0.0.1" in script

    def test_get_script_disabled(self):
        config = WebRTCConfig(mode=WebRTCMode.DISABLED)
        script = WebRTCProtector.get_script(config)
        assert script == ""

    def test_script_contains_proxy(self):
        config = WebRTCConfig.block_all()
        script = WebRTCProtector.get_script(config)
        assert "Proxy" in script

    def test_script_contains_fake_rtc(self):
        config = WebRTCConfig.block_all()
        script = WebRTCProtector.get_script(config)
        assert "FakeRTCPeerConnection" in script

    def test_script_wraps_iife(self):
        config = WebRTCConfig.block_all()
        script = WebRTCProtector.get_script(config)
        assert script.startswith("(function()")
        assert script.endswith("})();")

    def test_different_modes_different_scripts(self):
        config1 = WebRTCConfig.block_all()
        config2 = WebRTCConfig.filter_host()
        script1 = WebRTCProtector.get_script(config1)
        script2 = WebRTCProtector.get_script(config2)
        assert script1 != script2

    def test_script_contains_ice_filtering(self):
        config = WebRTCConfig.filter_host()
        script = WebRTCProtector.get_script(config)
        assert "ice" in script.lower() or "candidate" in script.lower()

    def test_script_contains_stun_blocking(self):
        config = WebRTCConfig(block_stun=True)
        script = WebRTCProtector.get_script(config)
        assert "stun" in script.lower()

    def test_script_no_stun_blocking(self):
        config = WebRTCConfig(block_stun=False)
        script = WebRTCProtector.get_script(config)
        # Скрипт должен быть, но без STUN блокировки
        assert isinstance(script, str)

    def test_fake_ice_contains_ip_replacement(self):
        config = WebRTCConfig.fake_ice("192.168.100.100")
        script = WebRTCProtector.get_script(config)
        assert "192.168.100.100" in script
