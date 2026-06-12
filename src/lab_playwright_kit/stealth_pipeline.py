"""
StealthPipeline — единый антидетект-пайплайн.

Объединяет все модули маскировки в один фасад:
  - stealth.py        → JS-инъекции (webdriver, plugins, chrome, webgl, etc.)
  - stealth_audio.py  → AudioContext fingerprint spoofing
  - stealth_webrtc.py → WebRTC IP leak protection
  - stealth_client_hints.py → User-Agent Client Hints spoofing
  - stealth_benchmark.py    → автоматический бенчмарк

Использование:
    >>> from lab_playwright_kit.stealth_pipeline import StealthPipeline
    >>> pipeline = StealthPipeline.level("advanced")
    >>> await pipeline.apply(page)
    >>> result = await pipeline.benchmark()

Уровни:
  - minimal:  только webdriver
  - standard:  webdriver + plugins + languages + chrome + permissions + webgl
  - advanced:  standard + все P0 векторы
  - full:      advanced + random_ua + audio + webrtc + client_hints

Покрытие сигнатур по уровням:
  minimal:  ~15%
  standard: ~35%
  advanced: ~70%
  full:     ~90%+
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from playwright.async_api import Page

from lab_playwright_kit.stealth import StealthConfig, apply_stealth
from lab_playwright_kit.stealth_audio import AudioConfig, apply_audio_spoofing
from lab_playwright_kit.stealth_webrtc import WebRTCConfig, apply_webrtc_protection
from lab_playwright_kit.stealth_client_hints import ClientHintsConfig, apply_client_hints
from lab_playwright_kit.stealth_benchmark import BenchmarkResult, StealthBenchmark


@dataclass
class PipelineResult:
    """Результат применения StealthPipeline.

    Attributes:
        stealth_scripts: Количество применённых JS-скриптов
        audio_applied: AudioContext spoofing применён
        webrtc_applied: WebRTC protection применена
        client_hints_applied: Client Hints spoofing применён
        user_agent: Использованный User-Agent (если был)
        level: Уровень защиты
    """
    stealth_scripts: int = 0
    audio_applied: bool = False
    webrtc_applied: bool = False
    client_hints_applied: bool = False
    user_agent: str | None = None
    level: str = "none"

    @property
    def summary(self) -> str:
        parts = [f"level={self.level}", f"scripts={self.stealth_scripts}"]
        if self.audio_applied:
            parts.append("audio=✓")
        if self.webrtc_applied:
            parts.append("webrtc=✓")
        if self.client_hints_applied:
            parts.append("client_hints=✓")
        if self.user_agent:
            parts.append(f"ua={self.user_agent[:30]}...")
        return f"StealthPipeline({', '.join(parts)})"


class StealthPipeline:
    """Единый антидетект-пайплайн.

    Применяет все слои маскировки к странице в правильном порядке:
    1. Stealth JS-скрипты (базовая маскировка)
    2. AudioContext spoofing
    3. WebRTC IP leak protection
    4. User-Agent Client Hints spoofing

    Каждый слой можно включить/независимо через конфигурацию,
    или использовать предустановленные уровни.

    Example:
        >>> pipeline = StealthPipeline.level("full")
        >>> result = await pipeline.apply(page)
        >>> print(result.summary)
        StealthPipeline(level=full, scripts=18, audio=✓, webrtc=✓, client_hints=✓)

        >>> # Кастомная конфигурация
        >>> pipeline = StealthPipeline(
        ...     stealth=StealthConfig.advanced(),
        ...     audio=AudioConfig.full(noise_seed=42),
        ...     webrtc=WebRTCConfig.block_all(),
        ... )
        >>> await pipeline.apply(page)

        >>> # Бенчмарк
        >>> bench_result = await pipeline.benchmark()
        >>> print(f"Score: {bench_result.score}/100")
    """

    def __init__(
        self,
        stealth: StealthConfig | None = None,
        audio: AudioConfig | None = None,
        webrtc: WebRTCConfig | None = None,
        client_hints: ClientHintsConfig | None = None,
        level: str = "advanced",
    ):
        """Инициализация пайплайна.

        Args:
            stealth: Конфигурация stealth JS-скриптов.
            audio: Конфигурация AudioContext spoofing.
            webrtc: Конфигурация WebRTC protection.
            client_hints: Конфигурация Client Hints spoofing.
            level: Уровень защиты (minimal, standard, advanced, full).
                    Используется если не указаны конкретные конфиги.
        """
        self._level = level

        if stealth is not None:
            self._stealth = stealth
        else:
            self._stealth = _config_for_level(level)

        self._audio = audio
        self._webrtc = webrtc
        self._client_hints = client_hints

        # Флаги автоопределения: если конфиг не передан явно,
        # определяем из уровня
        self._auto_audio = audio is None and level in ("full",)
        self._auto_webrtc = webrtc is None and level in ("full", "advanced")
        self._auto_client_hints = client_hints is None and level in ("full", "advanced")

    @classmethod
    def level(cls, name: str) -> StealthPipeline:
        """Создать пайплайн с предустановленным уровнем.

        Args:
            name: Уровень защиты — minimal, standard, advanced, full.

        Returns:
            StealthPipeline с соответствующей конфигурацией.

        Raises:
            ValueError: Если указан неизвестный уровень.
        """
        if name not in ("minimal", "standard", "advanced", "full"):
            raise ValueError(f"Unknown stealth level: {name}. Use: minimal, standard, advanced, full")
        return cls(level=name)

    @classmethod
    def minimal(cls) -> StealthPipeline:
        """Минимальный уровень — только webdriver."""
        return cls(level="minimal")

    @classmethod
    def standard(cls) -> StealthPipeline:
        """Стандартный уровень — базовые 6 скриптов."""
        return cls(level="standard")

    @classmethod
    def advanced(cls) -> StealthPipeline:
        """Продвинутый уровень — все P0 векторы."""
        return cls(level="advanced")

    @classmethod
    def full(cls) -> StealthPipeline:
        """Полный уровень — максимальная маскировка."""
        return cls(level="full")

    async def apply(self, page: Page) -> PipelineResult:
        """Применить весь пайплайн к странице.

        Порядок применения:
        1. Stealth JS-скрипты (через apply_stealth)
        2. AudioContext spoofing
        3. WebRTC protection
        4. Client Hints spoofing

        Args:
            page: Playwright Page объект.

        Returns:
            PipelineResult с информацией о применённых слоях.
        """
        result = PipelineResult(level=self._level)

        # 1. Базовый stealth (JS-скрипты)
        scripts = self._stealth.get_scripts()
        result.stealth_scripts = len(scripts)
        await apply_stealth(page, self._stealth)
        result.user_agent = self._stealth.get_user_agent()

        # 2. AudioContext spoofing
        if self._audio is not None or self._auto_audio:
            audio_cfg = self._audio or AudioConfig.full()
            await apply_audio_spoofing(page, audio_cfg)
            result.audio_applied = True
            logger.debug("StealthPipeline: audio spoofing applied")

        # 3. WebRTC protection
        if self._webrtc is not None or self._auto_webrtc:
            webrtc_cfg = self._webrtc or WebRTCConfig.filter_host()
            await apply_webrtc_protection(page, webrtc_cfg)
            result.webrtc_applied = True
            logger.debug("StealthPipeline: WebRTC protection applied")

        # 4. Client Hints spoofing
        if self._client_hints is not None or self._auto_client_hints:
            ch_cfg = self._client_hints or ClientHintsConfig.chrome_windows()
            await apply_client_hints(page, ch_cfg)
            result.client_hints_applied = True
            logger.debug("StealthPipeline: client hints spoofing applied")

        logger.info(f"StealthPipeline applied: {result.summary}")
        return result

    async def benchmark(
        self,
        url: str = StealthBenchmark.DEFAULT_URL,
        timeout_ms: int = 30000,
    ) -> BenchmarkResult:
        """Запустить бенчмарк stealth-маскировки.

        Запускает headless Chromium, применяет текущую конфигурацию
        и навигирует на bot.sannysoft.com для оценки.

        Args:
            url: URL тестовой страницы.
            timeout_ms: Таймаут загрузки.

        Returns:
            BenchmarkResult с результатами.
        """
        benchmark = StealthBenchmark(
            config=self._stealth,
            url=url,
            timeout_ms=timeout_ms,
        )
        return await benchmark.run()

    @property
    def stealth_config(self) -> StealthConfig:
        """Текущая stealth-конфигурация."""
        return self._stealth

    @property
    def level_name(self) -> str:
        """Название текущего уровня."""
        return self._level


# ─── Вспомогательные функции ─────────────────────────────────────────────────

def _config_for_level(level: str) -> StealthConfig:
    """Получить StealthConfig для уровня."""
    match level:
        case "minimal":
            return StealthConfig.minimal()
        case "standard":
            return StealthConfig.standard()
        case "advanced":
            return StealthConfig.advanced()
        case "full":
            return StealthConfig.full()
        case _:
            return StealthConfig.advanced()


# ─── Удобные функции ─────────────────────────────────────────────────────────

async def apply_stealth_full(page: Page) -> PipelineResult:
    """Применить полный stealth к странице (shortcut).

    Args:
        page: Playwright Page объект.

    Returns:
        PipelineResult с результатами.
    """
    pipeline = StealthPipeline.full()
    return await pipeline.apply(page)


async def apply_stealth_advanced(page: Page) -> PipelineResult:
    """Применить advanced stealth к странице (shortcut).

    Args:
        page: Playwright Page объект.

    Returns:
        PipelineResult с результатами.
    """
    pipeline = StealthPipeline.advanced()
    return await pipeline.apply(page)
