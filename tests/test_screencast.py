"""
Тесты для Screencast Recorder модуля.

Покрывает:
  - ScreencastRecorder — запись видео
  - FrameAnnotation — аннотации к кадрам
  - Свойства и состояние
"""
import asyncio

import pytest

from lab_playwright_kit.screencast import FrameAnnotation, ScreencastRecorder


# ─── FrameAnnotation ─────────────────────────────────────────────────────────

class TestFrameAnnotation:
    def test_create(self):
        ann = FrameAnnotation(frame_num=10, text="Click button")
        assert ann.frame_num == 10
        assert ann.text == "Click button"
        assert ann.timestamp_ms == 0.0

    def test_create_with_timestamp(self):
        ann = FrameAnnotation(frame_num=5, text="Navigate", timestamp_ms=1234.5)
        assert ann.timestamp_ms == 1234.5


# ─── ScreencastRecorder init ─────────────────────────────────────────────────

class TestScreencastRecorderInit:
    def test_init_defaults(self, tmp_path):
        path = str(tmp_path / "test.webm")
        rec = ScreencastRecorder(page=None, output_path=path)
        assert rec._format == "webm"
        assert rec._recording is False
        assert rec._frame_count == 0
        assert rec._annotations == []

    def test_init_custom_format(self, tmp_path):
        path = str(tmp_path / "test.webm")
        rec = ScreencastRecorder(page=None, output_path=path, format="webm")
        assert rec._format == "webm"

    def test_invalid_format_raises(self, tmp_path):
        path = str(tmp_path / "test.avi")
        with pytest.raises(ValueError, match="Unsupported format"):
            ScreencastRecorder(page=None, output_path=path, format="avi")


# ─── ScreencastRecorder properties ───────────────────────────────────────────

class TestScreencastRecorderProperties:
    def test_is_recording_default(self, tmp_path):
        path = str(tmp_path / "test.webm")
        rec = ScreencastRecorder(page=None, output_path=path)
        assert rec.is_recording is False

    def test_annotations_default(self, tmp_path):
        path = str(tmp_path / "test.webm")
        rec = ScreencastRecorder(page=None, output_path=path)
        assert rec.annotations == []

    def test_frame_count_default(self, tmp_path):
        path = str(tmp_path / "test.webm")
        rec = ScreencastRecorder(page=None, output_path=path)
        assert rec.frame_count == 0


# ─── ScreencastRecorder annotate() ───────────────────────────────────────────

class TestScreencastRecorderAnnotate:
    def test_annotate_adds(self, tmp_path):
        path = str(tmp_path / "test.webm")
        rec = ScreencastRecorder(page=None, output_path=path)
        asyncio.run(rec.annotate(0, "Start"))
        assert len(rec.annotations) == 1
        assert rec.annotations[0].text == "Start"
        assert rec.annotations[0].frame_num == 0

    def test_annotate_multiple(self, tmp_path):
        path = str(tmp_path / "test.webm")
        rec = ScreencastRecorder(page=None, output_path=path)
        asyncio.run(rec.annotate(0, "Start"))
        asyncio.run(rec.annotate(5, "Click"))
        asyncio.run(rec.annotate(10, "End"))
        assert len(rec.annotations) == 3

    def test_annotate_updates_frame_count(self, tmp_path):
        path = str(tmp_path / "test.webm")
        rec = ScreencastRecorder(page=None, output_path=path)
        asyncio.run(rec.annotate(0, "Start"))
        assert rec.frame_count == 1
        asyncio.run(rec.annotate(10, "End"))
        assert rec.frame_count == 11

    def test_annotate_same_frame(self, tmp_path):
        path = str(tmp_path / "test.webm")
        rec = ScreencastRecorder(page=None, output_path=path)
        asyncio.run(rec.annotate(5, "First"))
        asyncio.run(rec.annotate(5, "Second"))
        assert len(rec.annotations) == 2
        assert rec.frame_count == 6


# ─── ScreencastRecorder start/stop ───────────────────────────────────────────

class TestScreencastRecorderStartStop:
    def test_start_sets_recording(self, tmp_path):
        path = str(tmp_path / "test.webm")
        rec = ScreencastRecorder(page=None, output_path=path)
        asyncio.run(rec.start())
        assert rec.is_recording is True

    def test_stop_clears_recording(self, tmp_path):
        path = str(tmp_path / "test.webm")
        rec = ScreencastRecorder(page=None, output_path=path)
        asyncio.run(rec.start())
        asyncio.run(rec.stop())
        assert rec.is_recording is False

    def test_double_start_warning(self, tmp_path):
        path = str(tmp_path / "test.webm")
        rec = ScreencastRecorder(page=None, output_path=path)
        asyncio.run(rec.start())
        # Второй start не должен выбросить ошибку
        asyncio.run(rec.start())
        assert rec.is_recording is True

    def test_stop_when_not_recording(self, tmp_path):
        path = str(tmp_path / "test.webm")
        rec = ScreencastRecorder(page=None, output_path=path)
        result = asyncio.run(rec.stop())
        assert result == path
