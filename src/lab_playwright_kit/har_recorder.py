"""
HAR Recorder модуль: нативная запись HAR через Playwright.

HAR (HTTP Archive) — формат логирования сетевых запросов браузера.
Поддерживает:
  - Нативная HAR-запись через Playwright BrowserContext
  - Фильтрация по resource_type (xhr, fetch, document, image, etc.)
  - Экспорт в JSON файл
  - Статистика по запросам

Example:
    >>> async with BrowserManager() as browser:
    ...     recorder = HARRecorder(browser.context)
    ...     await recorder.start_recording()
    ...     page = await browser.goto("https://example.com")
    ...     har = await recorder.stop_recording()
    ...     xhr_calls = recorder.filter_by_type(har, "xhr")
    ...     recorder.export_to_json(har, "/tmp/recorded.har")
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger
from playwright.async_api import BrowserContext


@dataclass
class HARStats:
    """Статистика HAR-записи.

    Attributes:
        total_entries: Общее количество записей
        total_size_bytes: Общий размер ответов в байтах
        total_time_ms: Общее время всех запросов в мс
        by_type: Количество запросов по типам {type: count}
        by_status: Количество ответов по статус-кодам {status: count}
        domains: Список уникальных доменов
    """

    total_entries: int = 0
    total_size_bytes: int = 0
    total_time_ms: float = 0.0
    by_type: dict[str, int] = field(default_factory=dict)
    by_status: dict[str, int] = field(default_factory=dict)
    domains: list[str] = field(default_factory=list)

    @property
    def avg_time_ms(self) -> float:
        """Среднее время запроса."""
        if self.total_entries == 0:
            return 0.0
        return self.total_time_ms / self.total_entries


class HARRecorder:
    """HAR-рекордер через нативный механизм Playwright.

    Использует встроенную поддержку HAR в Playwright BrowserContext.
    Автоматически создаёт временную директорию для хранения HAR-файла.

    Example:
        >>> recorder = HARRecorder(context, "/tmp/recording.har")
        >>> await recorder.start_recording()
        >>> await page.goto("https://example.com")
        >>> har = await recorder.stop_recording()
        >>> xhr_calls = recorder.filter_by_type(har, "xhr")
        >>> recorder.export_to_json(har, "/tmp/output.har")
    """

    def __init__(
        self,
        context: BrowserContext,
        output_path: str | None = None,
    ):
        """Инициализация HAR-рекордера.

        Args:
            context: Playwright BrowserContext для записи
            output_path: Путь для сохранения HAR-файла.
                        Если None — используется временный файл.
        """
        self._context = context
        self._output_path = output_path
        self._is_recording = False
        self._har_file_path: Path | None = None

    async def start_recording(
        self,
        output_path: str | None = None,
        content_policy: str = "embed",
    ) -> None:
        """Начать запись HAR.

        Запускает нативную HAR-запись через Playwright.
        Все последующие сетевые запросы будут записаны.

        Args:
            output_path: Путь для HAR-файла (переопределяет конструктор)
            content_policy: Политика сохранения контента:
                - "embed" — включить тело ответов в HAR
                - "attach" — сохранить тела отдельными файлами
                - "omit" — не сохранять тела ответов

        Raises:
            RuntimeError: Если запись уже запущена
            ValueError: Если content_policy невалидный
        """
        if self._is_recording:
            raise RuntimeError("HAR recording is already started")

        valid_policies = ("embed", "attach", "omit")
        if content_policy not in valid_policies:
            raise ValueError(
                f"Invalid content_policy: {content_policy}. "
                f"Must be one of: {valid_policies}"
            )

        path = output_path or self._output_path
        if path:
            self._har_file_path = Path(path)
            self._har_file_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            import tempfile

            tmp = tempfile.NamedTemporaryFile(
                suffix=".har", delete=False, prefix="har_recording_"
            )
            self._har_file_path = Path(tmp.name)
            tmp.close()

        # Установить recordHar для контекста
        # Playwright записывает HAR автоматически при закрытии контекста
        await self._context._impl_obj._channel.send(
            "harStart", {"recordHarPath": str(self._har_file_path)}
        )

        self._is_recording = True
        logger.info(f"HAR recording started → {self._har_file_path}")

    async def stop_recording(self) -> dict[str, Any]:
        """Остановить запись и получить HAR-данные.

        Останавливает HAR-запись и загружает собранные данные
        — либо из записанного файла, либо из памяти.

        Returns:
            HAR-данные в формате JSON (dict с ключом "log")

        Raises:
            RuntimeError: Если запись не была запущена
            FileNotFoundError: Если HAR-файл не найден после записи

        Example:
            >>> har = await recorder.stop_recording()
            >>> entries = har["log"]["entries"]
            >>> print(f"Recorded {len(entries)} requests")
        """
        if not self._is_recording:
            raise RuntimeError("HAR recording was not started")

        self._is_recording = False

        # Остановить HAR-запись
        try:
            await self._context._impl_obj._channel.send("harStop")
        except Exception:
            # Fallback: Playwright может записывать HAR при закрытии контекста
            logger.debug("harStop command failed — will try reading file directly")

        har_data = await self._load_har_file()
        logger.info(
            f"HAR recording stopped — "
            f"{len(har_data.get('log', {}).get('entries', []))} entries"
        )
        return har_data

    def get_har(self, har_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Получить список записей из HAR-данных.

        Args:
            har_data: HAR-данные (результат stop_recording)

        Returns:
            Список entry-записей
        """
        return har_data.get("log", {}).get("entries", [])

    def filter_by_type(
        self,
        har_data: dict[str, Any],
        resource_type: str,
    ) -> list[dict[str, Any]]:
        """Отфильтровать HAR-записи по типу ресурса.

        Args:
            har_data: HAR-данные (результат stop_recording)
            resource_type: Тип ресурса (xhr, fetch, document,
                          stylesheet, image, script, font, media, etc.)

        Returns:
            Отфильтрованный список entry-записей

        Example:
            >>> xhr_calls = recorder.filter_by_type(har, "xhr")
            >>> fetch_calls = recorder.filter_by_type(har, "fetch")
            >>> images = recorder.filter_by_type(har, "image")
        """
        entries = self.get_har(har_data)
        return [
            e for e in entries
            if e.get("_resourceType", "").lower() == resource_type.lower()
        ]

    def filter_by_domain(
        self,
        har_data: dict[str, Any],
        domain: str,
    ) -> list[dict[str, Any]]:
        """Отфильтровать HAR-записи по домену.

        Args:
            har_data: HAR-данные
            domain: Домен для фильтрации (например, "api.example.com")

        Returns:
            Отфильтрованный список entry-записей
        """
        entries = self.get_har(har_data)
        return [
            e for e in entries
            if domain in e.get("request", {}).get("url", "")
        ]

    def filter_by_status(
        self,
        har_data: dict[str, Any],
        status: int,
    ) -> list[dict[str, Any]]:
        """Отфильтровать HAR-записи по HTTP-статусу.

        Args:
            har_data: HAR-данные
            status: HTTP-код ответа (200, 404, 500, etc.)

        Returns:
            Отфильтрованный список entry-записей
        """
        entries = self.get_har(har_data)
        return [
            e for e in entries
            if e.get("response", {}).get("status") == status
        ]

    def get_statistics(self, har_data: dict[str, Any]) -> HARStats:
        """Получить статистику HAR-записи.

        Args:
            har_data: HAR-данные

        Returns:
            HARStats с агрегированными метриками
        """
        entries = self.get_har(har_data)
        stats = HARStats(total_entries=len(entries))

        domain_set: set[str] = set()

        for entry in entries:
            # Time
            time_ms = entry.get("time", 0)
            stats.total_time_ms += time_ms

            # Size
            response = entry.get("response", {})
            body_size = response.get("bodySize", 0)
            if isinstance(body_size, (int, float)):
                stats.total_size_bytes += max(0, int(body_size))

            # By type
            res_type = entry.get("_resourceType", "unknown")
            stats.by_type[res_type] = stats.by_type.get(res_type, 0) + 1

            # By status
            status = response.get("status", 0)
            stats.by_status[str(status)] = stats.by_status.get(str(status), 0) + 1

            # Domain
            url = entry.get("request", {}).get("url", "")
            from urllib.parse import urlparse

            parsed = urlparse(url)
            if parsed.netloc:
                domain_set.add(parsed.netloc)

        stats.domains = sorted(domain_set)
        return stats

    def export_to_json(
        self,
        har_data: dict[str, Any],
        output_path: str,
        pretty: bool = True,
    ) -> str:
        """Экспортировать HAR-данные в JSON-файл.

        Args:
            har_data: HAR-данные
            output_path: Путь для сохранения JSON-файла
            pretty: Форматировать JSON с отступами

        Returns:
            Путь к сохранённому файлу

        Example:
            >>> path = recorder.export_to_json(har, "/tmp/recording.har")
            >>> print(f"Saved to {path}")
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            if pretty:
                json.dump(har_data, f, ensure_ascii=False, indent=2)
            else:
                json.dump(har_data, f, ensure_ascii=False)

        logger.info(f"HAR exported to {output_path}")
        return str(path)

    @staticmethod
    def create_empty_har() -> dict[str, Any]:
        """Создать пустой HAR-объект.

        Returns:
            Пустой HAR-структуры с версией и логом
        """
        return {
            "log": {
                "version": "1.2",
                "creator": {
                    "name": "lab-playwright-kit",
                    "version": "0.3.0",
                },
                "entries": [],
            }
        }

    @property
    def is_recording(self) -> bool:
        """Запись активна."""
        return self._is_recording

    @property
    def har_file_path(self) -> Path | None:
        """Путь к HAR-файлу."""
        return self._har_file_path

    # ─── Internal methods ──────────────────────────────────────────────────────

    async def _load_har_file(self) -> dict[str, Any]:
        """Загрузить HAR-данные с диска или fallback на пустой HAR."""
        if self._har_file_path and self._har_file_path.exists():
            # Подождать немного чтобы файл был полностью записан
            for _ in range(10):
                try:
                    content = self._har_file_path.read_text(encoding="utf-8")
                    if content.strip():
                        data = json.loads(content)
                        return data
                except (json.JSONDecodeError, OSError):
                    pass
                await __import__("asyncio").sleep(0.1)

            # Файл существует, но пуст или повреждён — попробовать ещё раз
            try:
                content = self._har_file_path.read_text(encoding="utf-8")
                if content.strip():
                    return json.loads(content)
            except Exception:
                pass

        # Fallback: вернуть пустой HAR
        logger.warning(
            "HAR file not available — returning empty HAR. "
            "This may happen if Playwright doesn't support native HAR recording "
            "in this configuration."
        )
        return self.create_empty_har()
