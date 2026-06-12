"""
Тесты для HAR Recorder модуля.

Покрытие:
- HARRecorder: start_recording, stop_recording
- filter_by_type, filter_by_domain, filter_by_status
- get_statistics
- export_to_json
- create_empty_har
- Edge cases
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lab_playwright_kit.har_recorder import (
    HARRecorder,
    HARStats,
)


# ═══════════════════════════════════════════════════════════════════
# HARStats
# ═══════════════════════════════════════════════════════════════════

class TestHARStats:
    """Тесты HARStats dataclass."""

    def test_defaults(self):
        """Дефолтные значения."""
        stats = HARStats()
        assert stats.total_entries == 0
        assert stats.total_size_bytes == 0
        assert stats.total_time_ms == 0.0
        assert stats.by_type == {}
        assert stats.by_status == {}
        assert stats.domains == []

    def test_avg_time_empty(self):
        """Среднее время при пустой статистике."""
        stats = HARStats()
        assert stats.avg_time_ms == 0.0

    def test_avg_time_with_entries(self):
        """Среднее время с записями."""
        stats = HARStats(total_entries=4, total_time_ms=400.0)
        assert stats.avg_time_ms == 100.0


# ═══════════════════════════════════════════════════════════════════
# HARRecorder — инициализация
# ═══════════════════════════════════════════════════════════════════

class TestHARRecorderInit:
    """Тесты инициализации HARRecorder."""

    def test_init_with_output_path(self):
        """Инициализация с output_path."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context, "/tmp/test.har")
        assert recorder._har_file_path is None  # Устанавливается при start
        assert recorder.is_recording is False

    def test_init_without_output_path(self):
        """Инициализация без output_path."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)
        assert recorder._output_path is None
        assert recorder.is_recording is False


# ═══════════════════════════════════════════════════════════════════
# HARRecorder — start/stop recording
# ═══════════════════════════════════════════════════════════════════

class TestHARRecorderStartStop:
    """Тесты start_recording и stop_recording."""

    @pytest.mark.asyncio
    async def test_start_recording_with_path(self, tmp_path):
        """Начало записи с указанным путём."""
        mock_context = MagicMock()
        mock_impl = MagicMock()
        mock_impl._channel = AsyncMock()
        mock_context._impl_obj = mock_impl

        har_path = str(tmp_path / "test.har")
        recorder = HARRecorder(mock_context, har_path)
        await recorder.start_recording()

        assert recorder.is_recording is True
        assert recorder.har_file_path == Path(har_path)

    @pytest.mark.asyncio
    async def test_start_recording_without_path(self):
        """Начало записи без пути — создаётся временный файл."""
        mock_context = MagicMock()
        mock_impl = MagicMock()
        mock_impl._channel = AsyncMock()
        mock_context._impl_obj = mock_impl

        recorder = HARRecorder(mock_context)
        await recorder.start_recording()

        assert recorder.is_recording is True
        assert recorder.har_file_path is not None

    @pytest.mark.asyncio
    async def test_start_recording_already_started(self):
        """Двойной start — RuntimeError."""
        mock_context = MagicMock()
        mock_impl = MagicMock()
        mock_impl._channel = AsyncMock()
        mock_context._impl_obj = mock_impl

        recorder = HARRecorder(mock_context, "/tmp/test.har")
        await recorder.start_recording()

        with pytest.raises(RuntimeError, match="already started"):
            await recorder.start_recording()

    @pytest.mark.asyncio
    async def test_start_recording_invalid_content_policy(self):
        """Невалидный content_policy — ValueError."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context, "/tmp/test.har")

        with pytest.raises(ValueError, match="Invalid content_policy"):
            await recorder.start_recording(content_policy="invalid")

    @pytest.mark.asyncio
    async def test_stop_recording_not_started(self):
        """Stop без start — RuntimeError."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        with pytest.raises(RuntimeError, match="not started"):
            await recorder.stop_recording()

    @pytest.mark.asyncio
    async def test_stop_recording_returns_har(self, tmp_path):
        """Stop возвращает HAR-данные."""
        mock_context = MagicMock()
        mock_impl = MagicMock()
        mock_impl._channel = AsyncMock()
        mock_context._impl_obj = mock_impl

        har_path = str(tmp_path / "test.har")
        recorder = HARRecorder(mock_context, har_path)
        await recorder.start_recording()

        # Создать фейковый HAR-файл
        har_data = HARRecorder.create_empty_har()
        har_data["log"]["entries"] = [
            {
                "request": {"url": "https://example.com/api", "method": "GET"},
                "response": {"status": 200, "bodySize": 1024},
                "time": 150,
                "_resourceType": "xhr",
            }
        ]
        Path(har_path).write_text(json.dumps(har_data))

        result = await recorder.stop_recording()
        assert "log" in result
        assert recorder.is_recording is False

    @pytest.mark.asyncio
    async def test_stop_recording_empty_fallback(self):
        """Stop с пустым файлом — возвращает пустой HAR."""
        mock_context = MagicMock()
        mock_impl = MagicMock()
        mock_impl._channel = AsyncMock()
        mock_context._impl_obj = mock_impl

        recorder = HARRecorder(mock_context)
        await recorder.start_recording()

        result = await recorder.stop_recording()
        assert "log" in result
        assert result["log"]["entries"] == []


# ═══════════════════════════════════════════════════════════════════
# HARRecorder — фильтрация
# ═══════════════════════════════════════════════════════════════════

class TestHARRecorderFiltering:
    """Тесты фильтрации HAR-данных."""

    @pytest.fixture
    def sample_har(self):
        """Пример HAR-данных с разными типами запросов."""
        return {
            "log": {
                "version": "1.2",
                "creator": {"name": "test", "version": "0.1"},
                "entries": [
                    {
                        "request": {"url": "https://api.example.com/data", "method": "GET"},
                        "response": {"status": 200, "bodySize": 1024},
                        "time": 150,
                        "_resourceType": "xhr",
                    },
                    {
                        "request": {"url": "https://api.example.com/users", "method": "POST"},
                        "response": {"status": 201, "bodySize": 512},
                        "time": 200,
                        "_resourceType": "fetch",
                    },
                    {
                        "request": {"url": "https://example.com/", "method": "GET"},
                        "response": {"status": 200, "bodySize": 4096},
                        "time": 300,
                        "_resourceType": "document",
                    },
                    {
                        "request": {"url": "https://cdn.example.com/image.png", "method": "GET"},
                        "response": {"status": 200, "bodySize": 8192},
                        "time": 100,
                        "_resourceType": "image",
                    },
                    {
                        "request": {"url": "https://api.example.com/error", "method": "GET"},
                        "response": {"status": 500, "bodySize": 256},
                        "time": 50,
                        "_resourceType": "xhr",
                    },
                    {
                        "request": {"url": "https://other.com/script.js", "method": "GET"},
                        "response": {"status": 200, "bodySize": 2048},
                        "time": 120,
                        "_resourceType": "script",
                    },
                ],
            }
        }

    def test_filter_by_type_xhr(self, sample_har):
        """Фильтрация по типу xhr."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        results = recorder.filter_by_type(sample_har, "xhr")
        assert len(results) == 2
        assert all(e["_resourceType"] == "xhr" for e in results)

    def test_filter_by_type_fetch(self, sample_har):
        """Фильтрация по типу fetch."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        results = recorder.filter_by_type(sample_har, "fetch")
        assert len(results) == 1
        assert results[0]["request"]["method"] == "POST"

    def test_filter_by_type_document(self, sample_har):
        """Фильтрация по типу document."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        results = recorder.filter_by_type(sample_har, "document")
        assert len(results) == 1

    def test_filter_by_type_image(self, sample_har):
        """Фильтрация по типу image."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        results = recorder.filter_by_type(sample_har, "image")
        assert len(results) == 1

    def test_filter_by_type_no_match(self, sample_har):
        """Фильтрация без совпадений."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        results = recorder.filter_by_type(sample_har, "websocket")
        assert len(results) == 0

    def test_filter_by_domain(self, sample_har):
        """Фильтрация по домену."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        results = recorder.filter_by_domain(sample_har, "api.example.com")
        assert len(results) == 3  # data, users, error

    def test_filter_by_domain_cdn(self, sample_har):
        """Фильтрация по CDN домену."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        results = recorder.filter_by_domain(sample_har, "cdn.example.com")
        assert len(results) == 1

    def test_filter_by_domain_no_match(self, sample_har):
        """Фильтрация по несуществующему домену."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        results = recorder.filter_by_domain(sample_har, "nonexistent.com")
        assert len(results) == 0

    def test_filter_by_status_200(self, sample_har):
        """Фильтрация по статусу 200."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        results = recorder.filter_by_status(sample_har, 200)
        assert len(results) == 4

    def test_filter_by_status_500(self, sample_har):
        """Фильтрация по статусу 500."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        results = recorder.filter_by_status(sample_har, 500)
        assert len(results) == 1

    def test_filter_by_status_no_match(self, sample_har):
        """Фильтрация по несуществующему статусу."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        results = recorder.filter_by_status(sample_har, 404)
        assert len(results) == 0

    def test_get_har_entries(self, sample_har):
        """Получение списка записей."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        entries = recorder.get_har(sample_har)
        assert len(entries) == 6

    def test_get_har_empty(self):
        """Получение записей из пустого HAR."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        empty_har = HARRecorder.create_empty_har()
        entries = recorder.get_har(empty_har)
        assert entries == []


# ═══════════════════════════════════════════════════════════════════
# HARRecorder — статистика
# ═══════════════════════════════════════════════════════════════════

class TestHARRecorderStats:
    """Тесты статистики HAR."""

    @pytest.fixture
    def sample_har(self):
        """Пример HAR-данных."""
        return {
            "log": {
                "entries": [
                    {
                        "request": {"url": "https://api.example.com/data", "method": "GET"},
                        "response": {"status": 200, "bodySize": 1024},
                        "time": 150,
                        "_resourceType": "xhr",
                    },
                    {
                        "request": {"url": "https://example.com/", "method": "GET"},
                        "response": {"status": 200, "bodySize": 4096},
                        "time": 300,
                        "_resourceType": "document",
                    },
                    {
                        "request": {"url": "https://cdn.example.com/img.png", "method": "GET"},
                        "response": {"status": 200, "bodySize": 8192},
                        "time": 100,
                        "_resourceType": "image",
                    },
                ],
            }
        }

    def test_get_statistics(self, sample_har):
        """Подсчёт статистики."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        stats = recorder.get_statistics(sample_har)
        assert stats.total_entries == 3
        assert stats.total_time_ms == 550.0
        assert stats.total_size_bytes == 13312

    def test_get_statistics_by_type(self, sample_har):
        """Статистика по типам."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        stats = recorder.get_statistics(sample_har)
        assert stats.by_type["xhr"] == 1
        assert stats.by_type["document"] == 1
        assert stats.by_type["image"] == 1

    def test_get_statistics_by_status(self, sample_har):
        """Статистика по статусам."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        stats = recorder.get_statistics(sample_har)
        assert stats.by_status["200"] == 3

    def test_get_statistics_domains(self, sample_har):
        """Статистика по доменам."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        stats = recorder.get_statistics(sample_har)
        assert "api.example.com" in stats.domains
        assert "example.com" in stats.domains
        assert "cdn.example.com" in stats.domains

    def test_get_statistics_empty(self):
        """Статистика пустого HAR."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        empty_har = HARRecorder.create_empty_har()
        stats = recorder.get_statistics(empty_har)
        assert stats.total_entries == 0
        assert stats.avg_time_ms == 0.0


# ═══════════════════════════════════════════════════════════════════
# HARRecorder — экспорт
# ═══════════════════════════════════════════════════════════════════

class TestHARRecorderExport:
    """Тесты экспорта HAR."""

    def test_export_to_json_pretty(self, tmp_path):
        """Экспорт с форматированием."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        har_data = {
            "log": {
                "entries": [
                    {
                        "request": {"url": "https://example.com"},
                        "response": {"status": 200},
                    }
                ]
            }
        }

        output_path = str(tmp_path / "export.har")
        result = recorder.export_to_json(har_data, output_path, pretty=True)

        assert result == output_path
        assert Path(output_path).exists()

        # Проверить форматирование
        content = Path(output_path).read_text()
        data = json.loads(content)
        assert "log" in data
        # Pretty print содержит отступы
        assert "    " in content or "\n" in content

    def test_export_to_json_compact(self, tmp_path):
        """Экспорт без форматирования."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        har_data = HARRecorder.create_empty_har()
        output_path = str(tmp_path / "compact.har")
        recorder.export_to_json(har_data, output_path, pretty=False)

        content = Path(output_path).read_text()
        data = json.loads(content)
        assert "log" in data

    def test_export_creates_directories(self, tmp_path):
        """Экспорт создаёт недостающие директории."""
        mock_context = MagicMock()
        recorder = HARRecorder(mock_context)

        har_data = HARRecorder.create_empty_har()
        output_path = str(tmp_path / "subdir" / "nested" / "export.har")
        recorder.export_to_json(har_data, output_path)

        assert Path(output_path).exists()


# ═══════════════════════════════════════════════════════════════════
# HARRecorder — create_empty_har
# ═══════════════════════════════════════════════════════════════════

class TestHARRecorderEmpty:
    """Тесты create_empty_har."""

    def test_create_empty_har(self):
        """Создание пустого HAR."""
        har = HARRecorder.create_empty_har()
        assert "log" in har
        assert har["log"]["version"] == "1.2"
        assert har["log"]["creator"]["name"] == "lab-playwright-kit"
        assert har["log"]["entries"] == []

    def test_create_empty_har_is_valid_json(self):
        """Пустой HAR — валидный JSON."""
        har = HARRecorder.create_empty_har()
        json_str = json.dumps(har)
        parsed = json.loads(json_str)
        assert parsed == har
