"""
Тесты для AudioContext fingerprint spoofing модуля.

Покрывает:
  - AudioConfig — конфигурация
  - AudioSpoofer — генерация JS-скриптов
"""
import pytest

from lab_playwright_kit.stealth_audio import AudioConfig, AudioSpoofer


# ─── AudioConfig ─────────────────────────────────────────────────────────────

class TestAudioConfig:
    def test_default_config(self):
        config = AudioConfig()
        assert config.noise_seed == 42
        assert config.spoof_oscillator is True
        assert config.spoof_analyser is True
        assert config.spoof_buffer is True
        assert config.spoof_offline is True

    def test_custom_seed(self):
        config = AudioConfig(noise_seed=12345)
        assert config.noise_seed == 12345

    def test_full_config(self):
        config = AudioConfig.full(noise_seed=99)
        assert config.noise_seed == 99
        assert config.spoof_oscillator is True
        assert config.spoof_analyser is True
        assert config.spoof_buffer is True
        assert config.spoof_offline is True

    def test_minimal_config(self):
        config = AudioConfig.minimal(noise_seed=77)
        assert config.noise_seed == 77
        assert config.spoof_oscillator is True
        assert config.spoof_analyser is True
        assert config.spoof_buffer is False
        assert config.spoof_offline is False

    def test_disable_all(self):
        config = AudioConfig(
            noise_seed=0,
            spoof_oscillator=False,
            spoof_analyser=False,
            spoof_buffer=False,
            spoof_offline=False,
        )
        assert config.spoof_oscillator is False
        assert config.spoof_analyser is False
        assert config.spoof_buffer is False
        assert config.spoof_offline is False


# ─── AudioSpoofer ────────────────────────────────────────────────────────────

class TestAudioSpoofer:
    def test_get_script_full(self):
        config = AudioConfig.full(noise_seed=42)
        script = AudioSpoofer.get_script(config)
        assert isinstance(script, str)
        assert len(script) > 0
        assert "function()" in script

    def test_get_script_minimal(self):
        config = AudioConfig.minimal(noise_seed=42)
        script = AudioSpoofer.get_script(config)
        assert isinstance(script, str)
        assert len(script) > 0

    def test_script_contains_seed(self):
        config = AudioConfig.full(noise_seed=12345)
        script = AudioSpoofer.get_script(config)
        assert "12345" in script

    def test_script_contains_prng(self):
        config = AudioConfig.full()
        script = AudioSpoofer.get_script(config)
        assert "_audioRng" in script or "Mulberry32" in script or "AUDIO_SEED" in script

    def test_script_contains_fft(self):
        config = AudioConfig.full()
        script = AudioSpoofer.get_script(config)
        assert "_fakeFFTValue" in script

    def test_script_contains_channel_data(self):
        config = AudioConfig.full()
        script = AudioSpoofer.get_script(config)
        assert "_fakeChannelValue" in script

    def test_script_wraps_iife(self):
        config = AudioConfig.full()
        script = AudioSpoofer.get_script(config)
        assert script.startswith("(function()")
        assert script.endswith("})();")

    def test_different_seeds_different_scripts(self):
        config1 = AudioConfig.full(noise_seed=1)
        config2 = AudioConfig.full(noise_seed=2)
        script1 = AudioSpoofer.get_script(config1)
        script2 = AudioSpoofer.get_script(config2)
        assert script1 != script2

    def test_same_seed_same_script(self):
        config1 = AudioConfig.full(noise_seed=42)
        config2 = AudioConfig.full(noise_seed=42)
        script1 = AudioSpoofer.get_script(config1)
        script2 = AudioSpoofer.get_script(config2)
        assert script1 == script2

    def test_minimal_has_less_code(self):
        full = AudioSpoofer.get_script(AudioConfig.full())
        minimal = AudioSpoofer.get_script(AudioConfig.minimal())
        assert len(minimal) < len(full)

    def test_script_contains_audiocontext(self):
        config = AudioConfig.full()
        script = AudioSpoofer.get_script(config)
        assert "AudioContext" in script

    def test_script_contains_analysernode(self):
        config = AudioConfig.full()
        script = AudioSpoofer.get_script(config)
        assert "AnalyserNode" in script
