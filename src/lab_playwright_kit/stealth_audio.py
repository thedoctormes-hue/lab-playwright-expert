"""
AudioContext fingerprint spoofing модуль.

Защищает от фингерпринтинга через Web Audio API:
  - Подмена AudioContext.createOscillator() — фейковый FFT-спектр
  - Подмена AnalyserNode.getFloatFrequencyData() — реалистичный шум
  - Подмена AudioBuffer.getChannelData() — детерминированный результат
  - Подмена OfflineAudioContext для консистентности

Использование:
    >>> from lab_playwright_kit.stealth_audio import AudioConfig, AudioSpoofer
    >>> config = AudioConfig(noise_seed=42)
    >>> js = AudioSpoofer.get_script(config)
    >>> await page.add_init_script(js)

Принцип работы:
  Реальный AudioContext генерирует уникальный спектр на каждом устройстве
  (из-за различий в аудиодрайверах, сэмплрейте, буферизации).
  Антибот-системы используют это как стабильный идентификатор.
  Мы подменяем результаты на фейковые, но реалистичные значения.

Покрытие сигнатур:
  - AudioContext fingerprint (CreepJS, FingerprintJS)
  - OscillatorNode frequency analysis
  - FFT spectrum fingerprinting
"""
from __future__ import annotations

from dataclasses import dataclass

from loguru import logger
from playwright.async_api import Page


@dataclass
class AudioConfig:
    """Конфигурация AudioContext fingerprint spoofing.

    Attributes:
        noise_seed: Seed для генерации фейкового спектра.
                    Одинаковый seed = одинаковый fingerprint (стабильность).
        spoof_oscillator: Подменять createOscillator().
        spoof_analyser: Подменять AnalyserNode методы.
        spoof_buffer: Подменять AudioBuffer.getChannelData().
        spoof_offline: Подменять OfflineAudioContext.
    """
    noise_seed: int = 42
    spoof_oscillator: bool = True
    spoof_analyser: bool = True
    spoof_buffer: bool = True
    spoof_offline: bool = True

    @classmethod
    def full(cls, noise_seed: int = 42) -> AudioConfig:
        """Полная подмена всех Audio API."""
        return cls(
            noise_seed=noise_seed,
            spoof_oscillator=True,
            spoof_analyser=True,
            spoof_buffer=True,
            spoof_offline=True,
        )

    @classmethod
    def minimal(cls, noise_seed: int = 42) -> AudioConfig:
        """Минимальная подмена — только oscillator и analyser."""
        return cls(
            noise_seed=noise_seed,
            spoof_oscillator=True,
            spoof_analyser=True,
            spoof_buffer=False,
            spoof_offline=False,
        )


class AudioSpoofer:
    """Генератор JS-скриптов для AudioContext fingerprint spoofing.

    Подменяет результаты Web Audio API вызовов на фейковые,
    но реалистичные значения. Использует детерминированный
    генератор на основе noise_seed для стабильности fingerprint.

    Example:
        >>> config = AudioConfig.full(noise_seed=12345)
        >>> script = AudioSpoofer.get_script(config)
        >>> await page.add_init_script(script)
    """

    @staticmethod
    def get_script(config: AudioConfig) -> str:
        """Получить полный JS-скрипт для инъекции.

        Объединяет все компоненты подмены в один скрипт.

        Args:
            config: Конфигурация Audio спуфинга.

        Returns:
            JS-скрипт для инъекции через page.add_init_script().
        """
        parts = [
            AudioSpoofer._seed_generator(config),
            AudioSpoofer._spoof_oscillator(config),
            AudioSpoofer._spoof_analyser(config),
            AudioSpoofer._spoof_buffer(config),
            AudioSpoofer._spoof_offline(config),
        ]

        inner = "\n".join(p for p in parts if p.strip())
        return f"(function() {{\n{inner}\n}})();"

    @staticmethod
    def _seed_generator(config: AudioConfig) -> str:
        """Детерминированный PRNG на основе seed.

        Генерирует стабильный шум для фейкового спектра.
        Одинаковый seed = одинаковый результат на каждом запуске.
        """
        return f"""
            // ── Детерминированный PRNG (Mulberry32) ──
            const _AUDIO_SEED = {config.noise_seed};
            let _audioRngState = _AUDIO_SEED;
            function _audioRng() {{
                _audioRngState |= 0;
                _audioRngState = (_audioRngState + 0x6D2B79F5) | 0;
                let t = Math.imul(_audioRngState ^ (_audioRngState >>> 15), 1 | _audioRngState);
                t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
                return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
            }}
            // Генерация фейкового FFT-спектра (реалистичный шум -60..-20 dB)
            function _fakeFFTValue(binIndex, totalBins) {{
                const base = -40 + Math.sin(binIndex * 0.1) * 15;
                const noise = (_audioRng() - 0.5) * 10;
                return base + noise;
            }}
            // Генерация фейкового channel data (реалистичный аудиосигнал)
            function _fakeChannelValue(index, sampleRate) {{
                const t = index / sampleRate;
                return Math.sin(t * 440 * Math.PI * 2) * 0.3 +
                       Math.sin(t * 880 * Math.PI * 2) * 0.1 +
                       (_audioRng() - 0.5) * 0.05;
            }}
        """

    @staticmethod
    def _spoof_oscillator(config: AudioConfig) -> str:
        """Подмена AudioContext.createOscillator().

        Патчит OscillatorNode для возврата фейковых значений
        при анализе через AnalyserNode.
        """
        if not config.spoof_oscillator:
            return ""

        return """
            // ── Подмена OscillatorNode ──
            (function() {
                const OrigAudioContext = window.AudioContext || window.webkitAudioContext;
                if (!OrigAudioContext) return;

                const origCreateOscillator = OrigAudioContext.prototype.createOscillator;
                OrigAudioContext.prototype.createOscillator = function() {
                    const oscillator = origCreateOscillator.call(this);

                    // Патчим frequency.value для возврата фейкового значения
                    const origFrequency = Object.getOwnPropertyDescriptor(
                        OscillatorNode.prototype, 'frequency'
                    );
                    if (origFrequency && origFrequency.get) {
                        const origGetter = origFrequency.get;
                        Object.defineProperty(oscillator, 'frequency', {
                            get: function() {
                                const param = origGetter.call(this);
                                // Подменяем value на детерминированное значение
                                const origValue = param.value;
                                Object.defineProperty(param, 'value', {
                                    get: function() {
                                        // Возвращаем значение с небольшим отклонением
                                        return origValue + (Math.sin(origValue * 0.001) * 0.5);
                                    },
                                    set: function(v) { origValue = v; },
                                    configurable: true
                                });
                                return param;
                            },
                            configurable: true
                        });
                    }

                    return oscillator;
                };
            })();
        """

    @staticmethod
    def _spoof_analyser(config: AudioConfig) -> str:
        """Подмена AnalyserNode методов.

        Подменяет getFloatFrequencyData() и getByteFrequencyData()
        для возврата фейкового FFT-спектра.
        """
        if not config.spoof_analyser:
            return ""

        return """
            // ── Подмена AnalyserNode (FFT спектр) ──
            (function() {
                if (typeof AnalyserNode === 'undefined') return;

                const origGetFloatFrequencyData = AnalyserNode.prototype.getFloatFrequencyData;
                AnalyserNode.prototype.getFloatFrequencyData = function(array) {
                    // Заполняем массив фейковыми значениями FFT
                    for (let i = 0; i < array.length; i++) {
                        array[i] = _fakeFFTValue(i, array.length);
                    }
                };

                const origGetByteFrequencyData = AnalyserNode.prototype.getByteFrequencyData;
                if (origGetByteFrequencyData) {
                    AnalyserNode.prototype.getByteFrequencyData = function(array) {
                        for (let i = 0; i < array.length; i++) {
                            // Конвертируем dB (от -100 до 0) в byte (0..255)
                            const db = _fakeFFTValue(i, array.length);
                            array[i] = Math.max(0, Math.min(255, Math.round((db + 100) * 2.55)));
                        }
                    };
                }

                // Подмена getFloatTimeDomainData
                const origGetFloatTimeDomain = AnalyserNode.prototype.getFloatTimeDomainData;
                if (origGetFloatTimeDomain) {
                    AnalyserNode.prototype.getFloatTimeDomainData = function(array) {
                        for (let i = 0; i < array.length; i++) {
                            array[i] = _fakeChannelValue(i, this.context ? this.context.sampleRate : 44100);
                        }
                    };
                }

                // Подмена getByteTimeDomainData
                const origGetByteTimeDomain = AnalyserNode.prototype.getByteTimeDomainData;
                if (origGetByteTimeDomain) {
                    AnalyserNode.prototype.getByteTimeDomainData = function(array) {
                        for (let i = 0; i < array.length; i++) {
                            const val = _fakeChannelValue(i, this.context ? this.context.sampleRate : 44100);
                            array[i] = Math.max(0, Math.min(255, Math.round((val + 1) * 127.5)));
                        }
                    };
                }
            })();
        """

    @staticmethod
    def _spoof_buffer(config: AudioConfig) -> str:
        """Подмена AudioBuffer.getChannelData().

        Возвращает фейковые аудиоданные вместо реальных.
        """
        if not config.spoof_buffer:
            return ""

        return """
            // ── Подмена AudioBuffer.getChannelData ──
            (function() {
                if (typeof AudioBuffer === 'undefined') return;

                const origGetChannelData = AudioBuffer.prototype.getChannelData;
                AudioBuffer.prototype.getChannelData = function(channel) {
                    // Вызываем оригинал для получения реального буфера
                    const buffer = origGetChannelData.call(this, channel);

                    // Перезаписываем фейковыми данными
                    const sampleRate = this.sampleRate;
                    for (let i = 0; i < buffer.length; i++) {
                        buffer[i] = _fakeChannelValue(i, sampleRate);
                    }

                    return buffer;
                };

                // Подмена copyFromChannel
                const origCopyFromChannel = AudioBuffer.prototype.copyFromChannel;
                if (origCopyFromChannel) {
                    AudioBuffer.prototype.copyFromChannel = function(destination, channelNumber) {
                        origCopyFromChannel.call(this, destination, channelNumber);
                        const sampleRate = this.sampleRate;
                        for (let i = 0; i < destination.length; i++) {
                            destination[i] = _fakeChannelValue(i, sampleRate);
                        }
                    };
                }
            })();
        """

    @staticmethod
    def _spoof_offline(config: AudioConfig) -> str:
        """Подмена OfflineAudioContext.

        Патчит для консистентности с обычным AudioContext.
        """
        if not config.spoof_offline:
            return ""

        return """
            // ── Подмена OfflineAudioContext ──
            (function() {
                const OrigOffline = window.OfflineAudioContext || window.webkitOfflineAudioContext;
                if (!OrigOffline) return;

                // Патчим startRendering для возврата фейкового AudioBuffer
                const origStartRendering = OrigOffline.prototype.startRendering;
                OrigOffline.prototype.startRendering = function() {
                    const promise = origStartRendering.call(this);

                    // Патчим результат
                    return promise.then(function(buffer) {
                        // Перезаписываем channel data
                        for (let ch = 0; ch < buffer.numberOfChannels; ch++) {
                            const data = buffer.getChannelData(ch);
                            for (let i = 0; i < data.length; i++) {
                                data[i] = _fakeChannelValue(i, buffer.sampleRate);
                            }
                        }
                        return buffer;
                    });
                };
            })();
        """


async def apply_audio_spoofing(
    page: Page,
    config: AudioConfig | None = None,
) -> None:
    """Применить AudioContext fingerprint spoofing к странице.

    Инъектирует JS-скрипт через page.add_init_script() — скрипт
    выполняется ДО загрузки страницы.

    Args:
        page: Playwright Page объект.
        config: Конфигурация Audio спуфинга. По умолчанию — full().

    Example:
        >>> from lab_playwright_kit.stealth_audio import apply_audio_spoofing, AudioConfig
        >>> await apply_audio_spoofing(page, AudioConfig.full(noise_seed=42))
    """
    cfg = config or AudioConfig.full()
    script = AudioSpoofer.get_script(cfg)
    if script:
        await page.add_init_script(script)
        logger.debug(f"Audio spoofing applied: seed={cfg.noise_seed}")
