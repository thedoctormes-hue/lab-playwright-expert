"""
Extended tests for har_recorder.py — HARStats, HARRecorder.

Covers: HARStats properties, HARRecorder methods (mocked BrowserContext).
"""

import json

import pytest

from lab_playwright_kit.har_recorder import (
    HARRecorder,
    HARStats,
)


class TestHARStats:
    def test_defaults(self):
        stats = HARStats()
        assert stats.total_entries == 0
        assert stats.total_size_bytes == 0
        assert stats.total_time_ms == 0.0
        assert stats.by_type == {}
        assert stats.by_status == {}
        assert stats.domains == []

    def test_avg_time_ms_zero(self):
        stats = HARStats()
        assert stats.avg_time_ms == 0.0

    def test_avg_time_ms_with_entries(self):
        stats = HARStats(total_entries=10, total_time_ms=500.0)
        assert stats.avg_time_ms == 50.0

    def test_avg_time_ms_single(self):
        stats = HARStats(total_entries=1, total_time_ms=100.0)
        assert stats.avg_time_ms == 100.0


class TestHARRecorderMakeHar:
    def test_make_har_returns_empty(self):
        """Static method create_empty_har should return valid structure."""
        har = HARRecorder.create_empty_har()
        assert "log" in har
        assert "version" in har["log"]
        assert "creator" in har["log"]
        assert "entries" in har["log"]
        assert har["log"]["entries"] == []

    def test_make_har_version(self):
        har = HARRecorder.create_empty_har()
        assert har["log"]["version"] == "1.2"

    def test_make_har_creator_name(self):
        har = HARRecorder.create_empty_har()
        assert har["log"]["creator"]["name"] == "lab-playwright-kit"


class TestHARRecorderWithMockHar:
    def _make_har_data(self, entries=None):
        if entries is None:
            entries = []
        return {
            "log": {
                "version": "1.2",
                "creator": {"name": "test", "version": "0.1"},
                "entries": entries,
            }
        }

    def _make_entry(
        self,
        url="https://example.com",
        method="GET",
        status=200,
        resource_type="document",
        time=100,
        body_size=500,
        mime_type="text/html",
    ):
        return {
            "request": {"method": method, "url": url},
            "response": {
                "status": status,
                "bodySize": body_size,
                "content": {"mimeType": mime_type},
            },
            "_resourceType": resource_type,
            "time": time,
        }

    def test_get_har(self):
        recorder = HARRecorder.__new__(HARRecorder)
        entries = [self._make_entry(), self._make_entry()]
        har = self._make_har_data(entries)
        result = recorder.get_har(har)
        assert len(result) == 2

    def test_get_har_empty(self):
        recorder = HARRecorder.__new__(HARRecorder)
        result = recorder.get_har({"log": {"entries": []}})
        assert result == []

    def test_filter_by_type(self):
        recorder = HARRecorder.__new__(HARRecorder)
        entries = [
            self._make_entry(resource_type="xhr"),
            self._make_entry(resource_type="document"),
            self._make_entry(resource_type="xhr"),
        ]
        har = self._make_har_data(entries)
        result = recorder.filter_by_type(har, "xhr")
        assert len(result) == 2

    def test_filter_by_type_case_insensitive(self):
        recorder = HARRecorder.__new__(HARRecorder)
        entries = [self._make_entry(resource_type="XHR")]
        har = self._make_har_data(entries)
        result = recorder.filter_by_type(har, "xhr")
        assert len(result) == 1

    def test_filter_by_type_no_match(self):
        recorder = HARRecorder.__new__(HARRecorder)
        entries = [self._make_entry(resource_type="image")]
        har = self._make_har_data(entries)
        result = recorder.filter_by_type(har, "xhr")
        assert result == []

    def test_filter_by_domain(self):
        recorder = HARRecorder.__new__(HARRecorder)
        entries = [
            self._make_entry(url="https://example.com/page1"),
            self._make_entry(url="https://other.com/page"),
            self._make_entry(url="https://example.com/page2"),
        ]
        har = self._make_har_data(entries)
        result = recorder.filter_by_domain(har, "example.com")
        assert len(result) == 2

    def test_filter_by_domain_no_match(self):
        recorder = HARRecorder.__new__(HARRecorder)
        entries = [self._make_entry(url="https://example.com/")]
        har = self._make_har_data(entries)
        result = recorder.filter_by_domain(har, "nonexistent.com")
        assert result == []

    def test_filter_by_status(self):
        recorder = HARRecorder.__new__(HARRecorder)
        entries = [
            self._make_entry(status=200),
            self._make_entry(status=404),
            self._make_entry(status=500),
        ]
        har = self._make_har_data(entries)
        result = recorder.filter_by_status(har, 200)
        assert len(result) == 1

    def test_filter_by_status_404(self):
        recorder = HARRecorder.__new__(HARRecorder)
        entries = [self._make_entry(status=404)]
        har = self._make_har_data(entries)
        result = recorder.filter_by_status(har, 404)
        assert len(result) == 1

    def test_get_statistics(self):
        recorder = HARRecorder.__new__(HARRecorder)
        entries = [
            self._make_entry(
                url="https://example.com/a", resource_type="document", time=100, body_size=500
            ),
            self._make_entry(
                url="https://example.com/b", resource_type="xhr", time=200, body_size=1000
            ),
            self._make_entry(
                url="https://other.com/c", resource_type="image", time=50, body_size=200
            ),
        ]
        har = self._make_har_data(entries)
        stats = recorder.get_statistics(har)
        assert stats.total_entries == 3
        assert stats.total_time_ms == 350.0
        assert stats.total_size_bytes == 1700
        assert stats.by_type["document"] == 1
        assert stats.by_type["xhr"] == 1
        assert stats.by_type["image"] == 1
        assert "200" in stats.by_status
        assert "example.com" in stats.domains
        assert "other.com" in stats.domains

    def test_get_statistics_empty(self):
        recorder = HARRecorder.__new__(HARRecorder)
        har = self._make_har_data([])
        stats = recorder.get_statistics(har)
        assert stats.total_entries == 0
        assert stats.total_time_ms == 0.0
        assert stats.total_size_bytes == 0
        assert stats.avg_time_ms == 0.0
        assert stats.domains == []

    def test_get_statistics_with_negative_body_size(self):
        recorder = HARRecorder.__new__(HARRecorder)
        entries = [self._make_entry(body_size=-1)]
        har = self._make_har_data(entries)
        stats = recorder.get_statistics(har)
        assert stats.total_size_bytes == 0  # negative clamped to 0

    def test_export_to_json(self, tmp_path):
        recorder = HARRecorder.__new__(HARRecorder)
        har = self._make_har_data([self._make_entry()])
        filepath = str(tmp_path / "test.har")
        result = recorder.export_to_json(har, filepath)
        assert result == filepath
        with open(filepath) as f:
            data = json.load(f)
        assert "log" in data
        assert len(data["log"]["entries"]) == 1

    def test_export_to_json_creates_dirs(self, tmp_path):
        recorder = HARRecorder.__new__(HARRecorder)
        har = self._make_har_data([])
        nested = str(tmp_path / "sub" / "dir" / "test.har")
        recorder.export_to_json(har, nested)
        assert __import__("os").path.exists(nested)

    def test_export_to_json_pretty(self, tmp_path):
        recorder = HARRecorder.__new__(HARRecorder)
        har = self._make_har_data([])
        filepath = str(tmp_path / "pretty.har")
        recorder.export_to_json(har, filepath, pretty=True)
        with open(filepath) as f:
            content = f.read()
        assert "  " in content  # has indentation

    def test_export_to_json_compact(self, tmp_path):
        recorder = HARRecorder.__new__(HARRecorder)
        har = self._make_har_data([])
        filepath = str(tmp_path / "compact.har")
        recorder.export_to_json(har, filepath, pretty=False)
        with open(filepath) as f:
            content = f.read()
        # Compact JSON should not have extra whitespace between keys
        lines = content.strip().split("\n")
        assert len(lines) <= 2  # very compact

    @pytest.mark.asyncio
    async def test_start_recording_already_started(self):
        recorder = HARRecorder.__new__(HARRecorder)
        recorder._is_recording = True
        with pytest.raises(RuntimeError, match="already started"):
            await recorder.start_recording()

    @pytest.mark.asyncio
    async def test_start_recording_invalid_content_policy(self):
        recorder = HARRecorder.__new__(HARRecorder)
        recorder._is_recording = False
        with pytest.raises(ValueError, match="Invalid content_policy"):
            await recorder.start_recording(content_policy="invalid")

    @pytest.mark.asyncio
    async def test_stop_recording_not_started(self):
        recorder = HARRecorder.__new__(HARRecorder)
        recorder._is_recording = False
        with pytest.raises(RuntimeError, match="not started"):
            await recorder.stop_recording()

    def test_is_recording_default(self):
        recorder = HARRecorder.__new__(HARRecorder)
        recorder._is_recording = False
        assert recorder.is_recording is False

    def test_is_recording_active(self):
        recorder = HARRecorder.__new__(HARRecorder)
        recorder._is_recording = True
        assert recorder.is_recording is True

    def test_har_file_path_default(self):
        recorder = HARRecorder.__new__(HARRecorder)
        recorder._har_file_path = None
        assert recorder.har_file_path is None

    def test_har_file_path_set(self):
        recorder = HARRecorder.__new__(HARRecorder)
        from pathlib import Path

        recorder._har_file_path = Path("/tmp/test.har")
        assert recorder.har_file_path == Path("/tmp/test.har")
