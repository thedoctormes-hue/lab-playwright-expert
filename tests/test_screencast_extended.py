"""
Extended tests for screencast.py — FrameAnnotation, ScreencastRecorder.
Covers: dataclasses, ScreencastRecorder methods.
"""

from unittest.mock import MagicMock, patch

import pytest

from lab_playwright_kit.screencast import (
    FrameAnnotation,
    ScreencastRecorder,
)


class TestFrameAnnotation:
    def test_defaults(self):
        ann = FrameAnnotation()
        assert ann.frame_number == 0
        assert ann.timestamp == 0.0
        assert ann.text == ""
        assert ann.x == 0
        assert ann.y == 0
        assert ann.color == "red"

    def test_full(self):
        ann = FrameAnnotation(
            frame_number=42,
            timestamp=1.5,
            text="Click here",
            x=100,
            y=200,
            color="blue",
        )
        assert ann.frame_number == 42
        assert ann.timestamp == 1.5
        assert ann.text == "Click here"
        assert ann.x == 100
        assert ann.y == 200
        assert ann.color == "blue"

    def test_to_dict(self):
        ann = FrameAnnotation(frame_number=1, timestamp=0.5, text="Step 1")
        d = ann.to_dict()
        assert d["frame_number"] == 1
        assert d["timestamp"] == 0.5
        assert d["text"] == "Step 1"


class TestScreencastRecorder:
    def test_init(self):
        recorder = ScreencastRecorder()
        assert recorder.frames == []
        assert recorder.annotations == []
        assert recorder.fps == 30
        assert recorder.width == 1280
        assert recorder.height == 720

    def test_init_custom(self):
        recorder = ScreencastRecorder(fps=60, width=1920, height=1080)
        assert recorder.fps == 60
        assert recorder.width == 1920
        assert recorder.height == 1080

    def test_add_frame(self):
        recorder = ScreencastRecorder()
        recorder.add_frame(b"frame_data")
        assert len(recorder.frames) == 1

    def test_add_frame_chain(self):
        recorder = ScreencastRecorder()
        result = recorder.add_frame(b"frame1").add_frame(b"frame2")
        assert len(result.frames) == 2

    def test_add_annotation(self):
        recorder = ScreencastRecorder()
        ann = FrameAnnotation(frame_number=1, text="Click")
        recorder.add_annotation(ann)
        assert len(recorder.annotations) == 1

    def test_add_annotation_chain(self):
        recorder = ScreencastRecorder()
        ann1 = FrameAnnotation(frame_number=1, text="Step 1")
        ann2 = FrameAnnotation(frame_number=2, text="Step 2")
        recorder.add_annotation(ann1).add_annotation(ann2)
        assert len(recorder.annotations) == 2

    def test_frame_count_empty(self):
        recorder = ScreencastRecorder()
        assert recorder.frame_count == 0

    def test_frame_count_with_frames(self):
        recorder = ScreencastRecorder()
        recorder.add_frame(b"f1")
        recorder.add_frame(b"f2")
        recorder.add_frame(b"f3")
        assert recorder.frame_count == 3

    def test_duration(self):
        recorder = ScreencastRecorder(fps=30)
        for _ in range(90):
            recorder.add_frame(b"frame")
        assert recorder.duration == 3.0

    def test_duration_empty(self):
        recorder = ScreencastRecorder()
        assert recorder.duration == 0.0

    def test_get_annotations_for_frame(self):
        recorder = ScreencastRecorder()
        recorder.add_annotation(FrameAnnotation(frame_number=1, text="A"))
        recorder.add_annotation(FrameAnnotation(frame_number=1, text="B"))
        recorder.add_annotation(FrameAnnotation(frame_number=2, text="C"))
        anns = recorder.get_annotations_for_frame(1)
        assert len(anns) == 2

    def test_get_annotations_for_frame_empty(self):
        recorder = ScreencastRecorder()
        assert recorder.get_annotations_for_frame(999) == []

    def test_clear(self):
        recorder = ScreencastRecorder()
        recorder.add_frame(b"f1")
        recorder.add_annotation(FrameAnnotation())
        recorder.clear()
        assert recorder.frame_count == 0
        assert len(recorder.annotations) == 0

    def test_to_dict(self):
        recorder = ScreencastRecorder(fps=30)
        recorder.add_frame(b"f1")
        recorder.add_annotation(FrameAnnotation(frame_number=0, text="Start"))
        d = recorder.to_dict()
        assert d["frame_count"] == 1
        assert d["fps"] == 30
        assert d["width"] == 1280
        assert len(d["annotations"]) == 1

    @pytest.mark.asyncio
    async def test_start_stop(self):
        recorder = ScreencastRecorder()
        mock_page = MagicMock()
        mock_page.video = None
        await recorder.start(mock_page)
        assert recorder._recording is True
        await recorder.stop()
        assert recorder._recording is False

    @pytest.mark.asyncio
    async def test_export_to_mp4(self, tmp_path):
        recorder = ScreencastRecorder()
        recorder.add_frame(b"fake_frame_data")
        filepath = str(tmp_path / "test.mp4")
        with patch("lab_playwright_kit.screencast.cv2") as mock_cv2:
            mock_cv2.VideoWriter.return_value = MagicMock()
            mock_cv2.VideoWriter_fourcc.return_value = 0
            result = await recorder.export_to_mp4(filepath)
            assert result is not None
