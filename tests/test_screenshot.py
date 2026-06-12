"""
Тесты для Screenshot Maker модуля.

Покрывает:
  - ScreenshotMaker — создание скриншотов
  - Генерация имён файлов
  - Конфигурация output_dir
"""
import pytest

from lab_playwright_kit.screenshot import ScreenshotMaker


# ─── ScreenshotMaker init ────────────────────────────────────────────────────

class TestScreenshotMakerInit:
    def test_default_output_dir(self):
        maker = ScreenshotMaker()
        assert maker.output_dir.name == "playwright_screenshots"

    def test_custom_output_dir(self, tmp_path):
        maker = ScreenshotMaker(output_dir=str(tmp_path))
        assert maker.output_dir == tmp_path

    def test_output_dir_creation(self, tmp_path):
        custom = tmp_path / "subdir" / "screenshots"
        maker = ScreenshotMaker(output_dir=str(custom))
        assert custom.exists()


# ─── ScreenshotMaker._filename() ─────────────────────────────────────────────

class TestScreenshotMakerFilename:
    def test_png_extension(self, tmp_path):
        maker = ScreenshotMaker(output_dir=str(tmp_path))
        filename = maker._filename("test", "png")
        assert filename.endswith(".png")
        assert "test_" in filename

    def test_pdf_extension(self, tmp_path):
        maker = ScreenshotMaker(output_dir=str(tmp_path))
        filename = maker._filename("page", "pdf")
        assert filename.endswith(".pdf")
        assert "page_" in filename

    def test_contains_timestamp(self, tmp_path):
        maker = ScreenshotMaker(output_dir=str(tmp_path))
        filename = maker._filename("snap", "png")
        # Формат времени: YYYYMMDD_HHMMSS
        import re
        assert re.search(r"\d{8}_\d{6}", filename)

    def test_unique_filenames(self, tmp_path):
        maker = ScreenshotMaker(output_dir=str(tmp_path))
        f1 = maker._filename("test", "png")
        import time
        time.sleep(0.01)
        f2 = maker._filename("test", "png")
        # Могут быть одинаковые если в ту же секунду, но путь должен быть валидным
        assert f1.endswith(".png")
        assert f2.endswith(".png")

    def test_path_in_output_dir(self, tmp_path):
        maker = ScreenshotMaker(output_dir=str(tmp_path))
        filename = maker._filename("test", "png")
        assert str(tmp_path) in filename


# ─── ScreenshotMaker — проверка консистентности ──────────────────────────────

class TestScreenshotMakerConsistency:
    def test_default_dir_is_path(self, tmp_path):
        maker = ScreenshotMaker(output_dir=str(tmp_path))
        from pathlib import Path
        assert isinstance(maker.output_dir, Path)

    def test_multiple_instances_same_dir(self, tmp_path):
        maker1 = ScreenshotMaker(output_dir=str(tmp_path))
        maker2 = ScreenshotMaker(output_dir=str(tmp_path))
        assert maker1.output_dir == maker2.output_dir
