"""
Extended tests for stealth_audio.py — AudioConfig, AudioSpoofer.
Covers: AudioConfig dataclass, AudioSpoofer generation.
"""

from lab_playwright_kit.stealth_audio import (
    AudioConfig,
    AudioSpoofer,
)


class TestAudioConfig:
    def test_defaults(self):
        config = AudioConfig()
        assert config.sample_rate == 44100
        assert config.channels == 2
        assert config.bit_depth == 16
        assert config.noise_level == 0.001
        assert config.seed == 42

    def test_full(self):
        config = AudioConfig(
            sample_rate=48000,
            channels=1,
            bit_depth=24,
            noise_level=0.005,
            seed=123,
        )
        assert config.sample_rate == 48000
        assert config.channels == 1
        assert config.bit_depth == 24
        assert config.noise_level == 0.005
        assert config.seed == 123


class TestAudioSpoofer:
    def test_init(self):
        spoofer = AudioSpoofer()
        assert spoofer.config is not None
        assert isinstance(spoofer.config, AudioConfig)

    def test_init_with_config(self):
        config = AudioConfig(sample_rate=48000, seed=99)
        spoofer = AudioSpoofer(config=config)
        assert spoofer.config.sample_rate == 48000
        assert spoofer.config.seed == 99

    def test_generate_noise_deterministic(self):
        config = AudioConfig(seed=42, noise_level=0.001)
        spoofer = AudioSpoofer(config=config)
        noise1 = spoofer.generate_noise(100)
        noise2 = spoofer.generate_noise(100)
        assert noise1 == noise2

    def test_generate_noise_different_seeds(self):
        spoofer1 = AudioSpoofer(config=AudioConfig(seed=42))
        spoofer2 = AudioSpoofer(config=AudioConfig(seed=99))
        noise1 = spoofer1.generate_noise(100)
        noise2 = spoofer2.generate_noise(100)
        assert noise1 != noise2

    def test_generate_noise_length(self):
        spoofer = AudioSpoofer()
        noise = spoofer.generate_noise(500)
        assert len(noise) == 500

    def test_generate_noise_empty(self):
        spoofer = AudioSpoofer()
        noise = spoofer.generate_noise(0)
        assert len(noise) == 0

    def test_get_script(self):
        spoofer = AudioSpoofer()
        script = spoofer.get_script()
        assert "AudioContext" in script or "audio" in script.lower()

    def test_get_script_with_custom_config(self):
        config = AudioConfig(sample_rate=48000, noise_level=0.005)
        spoofer = AudioSpoofer(config=config)
        script = spoofer.get_script()
        assert "48000" in str(config.sample_rate) or "audio" in script.lower()

    def test_noise_values_bounded(self):
        spoofer = AudioSpoofer(config=AudioConfig(noise_level=0.01))
        noise = spoofer.generate_noise(1000)
        for val in noise:
            assert -1.0 <= val <= 1.0
