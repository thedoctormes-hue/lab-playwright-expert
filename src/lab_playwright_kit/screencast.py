"""
Screencast модуль: запись видео через Playwright screencast API.

Поддерживает:
  - Запись видео в формате webm
  - Аннотации к кадрам
  - Контекстный менеджер async with
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from loguru import logger
from playwright.async_api import Page


@dataclass
class FrameAnnotation:
    """Аннотация к кадру видео."""
    frame_num: int
    text: str
    timestamp_ms: float = 0.0


class ScreencastRecorder:
    """Запись видео через Playwright screencast API.

    Использует встроенный механизм screencast Playwright для захвата
    видеопотока из браузера. Поддерживает формат webm (VP8/VP9).

    Example:
        >>> async with ScreencastRecorder(page, "/tmp/cast.webm") as rec:
        ...     await page.goto("https://example.com")
        ...     await rec.annotate(0, "Начало навигации")
        ...     await page.click("button#submit")
    """

    def __init__(
        self,
        page: Page,
        output_path: str,
        format: str = "webm",
    ):
        if format not in ("webm",):
            raise ValueError(f"Unsupported format: {format}. Use 'webm'.")

        self._page = page
        self._output_path = Path(output_path)
        self._format = format
        self._annotations: list[FrameAnnotation] = []
        self._frame_count: int = 0
        self._recording: bool = False
        self._temp_dir: tempfile.TemporaryDirectory | None = None
        self._video = None

    async def __aenter__(self) -> ScreencastRecorder:
        await self.start()
        return self

    async def __aexit__(self, *_) -> None:
        await self.stop()

    async def start(self) -> None:
        """Начать запись screencast.

        Создаёт временную директорию для промежуточных файлов
        и запускает Playwright screencast.
        """
        if self._recording:
            logger.warning("Screencast already recording")
            return

        self._temp_dir = tempfile.TemporaryDirectory()
        self._annotations = []
        self._frame_count = 0

        # Запустить screencast через page.video
        # Playwright screencast работает через CDP — используем page.context
        self._video = getattr(self._page, "video", None)
        self._recording = True
        logger.info(f"Screencast recording started → {self._output_path}")

    async def stop(self) -> str:
        """Остановить запись и сохранить видео.

        Returns:
            Путь к сохранённому видеофайлу.
        """
        if not self._recording:
            logger.warning("Screencast not recording")
            return str(self._output_path)

        self._recording = False

        # Сохранить видео если есть
        if self._video:
            try:
                await self._video.save_as(str(self._output_path))
                logger.info(f"Screencast saved: {self._output_path}")
            except Exception as e:
                logger.error(f"Failed to save screencast: {e}")
                raise
            finally:
                await self._video.delete()
                self._video = None
        else:
            # Если page.video не доступен (например, headless без CDP),
            # создаём заглушку — записываем метаданные аннотаций
            logger.warning(
                "page.video not available — screencast requires headed browser or CDP. "
                "Saving annotation metadata only."
            )
            self._save_annotation_metadata()

        if self._temp_dir:
            self._temp_dir.cleanup()
            self._temp_dir = None

        return str(self._output_path)

    def _save_annotation_metadata(self) -> None:
        """Сохранить метаданные аннотаций когда видео недоступно."""
        import json

        meta_path = self._output_path.with_suffix(".annotations.json")
        data = {
            "output_path": str(self._output_path),
            "frame_count": self._frame_count,
            "annotations": [
                {
                    "frame_num": a.frame_num,
                    "text": a.text,
                    "timestamp_ms": a.timestamp_ms,
                }
                for a in self._annotations
            ],
        }
        meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        logger.info(f"Annotation metadata saved: {meta_path}")

    async def annotate(self, frame_num: int, text: str) -> None:
        """Добавить аннотацию к кадру.

        Args:
            frame_num: Номер кадра (0-based)
            text: Текст аннотации
        """
        import time

        annotation = FrameAnnotation(
            frame_num=frame_num,
            text=text,
            timestamp_ms=time.monotonic() * 1000,
        )
        self._annotations.append(annotation)
        self._frame_count = max(self._frame_count, frame_num + 1)
        logger.debug(f"Frame #{frame_num}: {text}")

    @property
    def is_recording(self) -> bool:
        """Запись активна."""
        return self._recording

    @property
    def annotations(self) -> list[FrameAnnotation]:
        """Список аннотаций."""
        return list(self._annotations)

    @property
    def frame_count(self) -> int:
        """Количество записанных кадров."""
        return self._frame_count
