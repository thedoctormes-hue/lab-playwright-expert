"""
Тесты для новых модулей: ScreencastRecorder, ARIASnapshot, ClockController.
"""
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from lab_playwright_kit.aria_snapshot import ARIASnapshot, SnapshotDiff
from lab_playwright_kit.clock import ClockController
from lab_playwright_kit.screencast import ScreencastRecorder


# ═══════════════════════════════════════════════════════════════════
# ScreencastRecorder
# ═══════════════════════════════════════════════════════════════════

class TestScreencastRecorder:
    """Тесты ScreencastRecorder."""

    def test_init_default(self):
        """Инициализация с дефолтными параметрами."""
        mock_page = MagicMock()
        rec = ScreencastRecorder(mock_page, "/tmp/test.webm")
        assert rec._output_path == Path("/tmp/test.webm")
        assert rec._format == "webm"
        assert rec.is_recording is False

    def test_init_invalid_format(self):
        """Невалидный формат — ValueError."""
        mock_page = MagicMock()
        with pytest.raises(ValueError, match="Unsupported format"):
            ScreencastRecorder(mock_page, "/tmp/test.mp4", format="mp4")

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Запуск и остановка записи."""
        mock_page = MagicMock()
        mock_page.video = None
        rec = ScreencastRecorder(mock_page, "/tmp/test.webm")

        await rec.start()
        assert rec.is_recording is True

        result = await rec.stop()
        assert rec.is_recording is False
        assert result == "/tmp/test.webm"

    @pytest.mark.asyncio
    async def test_double_start(self):
        """Двойный start — warning, не ошибка."""
        mock_page = MagicMock()
        mock_page.video = None
        rec = ScreencastRecorder(mock_page, "/tmp/test.webm")

        await rec.start()
        await rec.start()  # Должно предупредить, не упасть
        assert rec.is_recording is True

    @pytest.mark.asyncio
    async def test_stop_without_start(self):
        """Stop без start — warning, не ошибка."""
        mock_page = MagicMock()
        rec = ScreencastRecorder(mock_page, "/tmp/test.webm")
        result = await rec.stop()
        assert result == "/tmp/test.webm"

    @pytest.mark.asyncio
    async def test_annotate(self):
        """Добавление аннотации."""
        mock_page = MagicMock()
        mock_page.video = None
        rec = ScreencastRecorder(mock_page, "/tmp/test.webm")
        await rec.start()

        await rec.annotate(0, "First frame")
        await rec.annotate(5, "Click button")

        assert len(rec.annotations) == 2
        assert rec.annotations[0].text == "First frame"
        assert rec.annotations[0].frame_num == 0
        assert rec.annotations[1].text == "Click button"
        assert rec.annotations[1].frame_num == 5
        assert rec.frame_count == 6

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Работа как контекстный менеджер."""
        mock_page = MagicMock()
        mock_page.video = None

        async with ScreencastRecorder(mock_page, "/tmp/test.webm") as rec:
            assert rec.is_recording is True
            await rec.annotate(0, "test")

        assert rec.is_recording is False
        assert len(rec.annotations) == 1

    @pytest.mark.asyncio
    async def test_save_annotation_metadata(self):
        """Сохранение метаданных аннотаций когда видео недоступно."""
        mock_page = MagicMock()
        mock_page.video = None
        rec = ScreencastRecorder(mock_page, "/tmp/test.webm")
        await rec.start()
        await rec.annotate(0, "Test annotation")
        await rec.stop()

        meta_path = Path("/tmp/test.annotations.json")
        assert meta_path.exists()
        data = json.loads(meta_path.read_text())
        assert data["frame_count"] == 1
        assert len(data["annotations"]) == 1
        assert data["annotations"][0]["text"] == "Test annotation"

        # Очистка
        meta_path.unlink()

    @pytest.mark.asyncio
    async def test_with_video_save(self):
        """Сохранение видео через page.video."""
        mock_page = MagicMock()
        mock_video = AsyncMock()
        mock_page.video = mock_video

        rec = ScreencastRecorder(mock_page, "/tmp/test.webm")
        await rec.start()
        await rec.stop()

        mock_video.save_as.assert_called_once_with("/tmp/test.webm")
        mock_video.delete.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# ARIASnapshot
# ═══════════════════════════════════════════════════════════════════

class TestARIASnapshot:
    """Тесты ARIASnapshot."""

    @pytest.mark.asyncio
    async def test_capture_full_page(self):
        """Получение snapshot всей страницы."""
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.aria_snapshot = AsyncMock(return_value="- heading: Test")
        mock_page.locator.return_value = mock_locator

        result = await ARIASnapshot.capture(mock_page)
        assert result == "- heading: Test"
        mock_page.locator.assert_called_once_with("body")

    @pytest.mark.asyncio
    async def test_capture_with_selector(self):
        """Получение snapshot с селектором."""
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.aria_snapshot = AsyncMock(return_value="- button: Submit")
        mock_page.locator.return_value = mock_locator

        result = await ARIASnapshot.capture(mock_page, "#main")
        assert result == "- button: Submit"
        mock_page.locator.assert_called_once_with("#main")

    @pytest.mark.asyncio
    async def test_capture_none_result(self):
        """Snapshot вернул None — пустая строка."""
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.aria_snapshot = AsyncMock(return_value=None)
        mock_page.locator.return_value = mock_locator

        result = await ARIASnapshot.capture(mock_page)
        assert result == ""

    def test_compare_identical(self):
        """Сравнение одинаковых snapshot — без изменений."""
        snap = "- heading: Title\n- button: Submit"
        diff = ARIASnapshot.compare(snap, snap)
        assert diff.has_changes is False
        assert len(diff.added) == 0
        assert len(diff.removed) == 0

    def test_compare_added(self):
        """Обнаружение добавленных элементов."""
        before = "- heading: Title"
        after = "- heading: Title\n- button: Submit"
        diff = ARIASnapshot.compare(before, after)
        assert diff.has_changes is True
        assert len(diff.added) == 1
        assert "button" in diff.added[0]

    def test_compare_removed(self):
        """Обнаружение удалённых элементов."""
        before = "- heading: Title\n- button: Submit"
        after = "- heading: Title"
        diff = ARIASnapshot.compare(before, after)
        assert diff.has_changes is True
        assert len(diff.removed) == 1
        assert "button" in diff.removed[0]

    def test_compare_changed(self):
        """Обнаружение изменённых значений."""
        before = "- heading: Old Title"
        after = "- heading: New Title"
        diff = ARIASnapshot.compare(before, after)
        assert diff.has_changes is True
        assert len(diff.changed) == 1
        assert diff.changed[0]["key"] == "heading"
        assert diff.changed[0]["before"] == "Old Title"
        assert diff.changed[0]["after"] == "New Title"

    def test_compare_empty(self):
        """Сравнение пустых snapshot."""
        diff = ARIASnapshot.compare("", "")
        assert diff.has_changes is False

    def test_to_yaml_normalization(self):
        """Нормализация YAML."""
        raw = "- heading: Title\n\n\n- button: Submit\n"
        result = ARIASnapshot.to_yaml(raw)
        assert "- heading: Title" in result
        assert "- button: Submit" in result

    def test_to_yaml_empty(self):
        """Пустой YAML."""
        assert ARIASnapshot.to_yaml("") == ""

    def test_from_yaml_valid(self):
        """Десериализация валидного YAML."""
        yaml_str = "- heading: Title\n- button: Submit"
        result = ARIASnapshot.from_yaml(yaml_str)
        assert "- heading: Title" in result

    def test_from_yaml_empty(self):
        """Пустой YAML — пустая строка."""
        assert ARIASnapshot.from_yaml("") == ""
        assert ARIASnapshot.from_yaml("   ") == ""

    def test_from_yaml_invalid(self):
        """Невалидный YAML — ValueError."""
        with pytest.raises(ValueError) as exc_info:
            ARIASnapshot.from_yaml("just some random text")
        assert "valid ARIA snapshot" in str(exc_info.value)

    def test_snapshot_diff_summary(self):
        """Форматирование summary."""
        diff = SnapshotDiff(
            added=["a", "b"],
            removed=["c"],
            changed=[{"key": "x", "before": "1", "after": "2"}],
        )
        assert "Added: 2" in diff.summary
        assert "Removed: 1" in diff.summary
        assert "Changed: 1" in diff.summary


# ═══════════════════════════════════════════════════════════════════
# ClockController
# ═══════════════════════════════════════════════════════════════════

class TestClockController:
    """Тесты ClockController."""

    @pytest.mark.asyncio
    async def test_freeze(self):
        """Заморозка времени."""
        mock_page = MagicMock()
        mock_page.clock.install = AsyncMock()
        mock_page.clock.freeze = AsyncMock()

        ctrl = ClockController()
        await ctrl.freeze(mock_page, 1704067200000)

        mock_page.clock.install.assert_called_once()
        mock_page.clock.freeze.assert_called_once_with(1704067200000)

    @pytest.mark.asyncio
    async def test_advance(self):
        """Продвижение времени."""
        mock_page = MagicMock()
        mock_page.clock.install = AsyncMock()
        mock_page.clock.run_for = AsyncMock()

        ctrl = ClockController()
        await ctrl.advance(mock_page, 5000)

        mock_page.clock.run_for.assert_called_once_with(5000)

    @pytest.mark.asyncio
    async def test_set_fixed(self):
        """Установка фиксированного времени."""
        mock_page = MagicMock()
        mock_page.clock.install = AsyncMock()
        mock_page.clock.set_fixed_time = AsyncMock()

        ctrl = ClockController()
        await ctrl.set_fixed(mock_page, 1704067200000)

        mock_page.clock.set_fixed_time.assert_called_once_with(1704067200000)

    @pytest.mark.asyncio
    async def test_reset(self):
        """Сброс к реальному времени."""
        mock_page = MagicMock()
        mock_page.clock.resume = AsyncMock()

        ctrl = ClockController()
        await ctrl.reset(mock_page)

        mock_page.clock.resume.assert_called_once()

    @pytest.mark.asyncio
    async def test_fast_forward(self):
        """Быстрое продвижение."""
        mock_page = MagicMock()
        mock_page.clock.install = AsyncMock()
        mock_page.clock.fast_forward = AsyncMock()

        ctrl = ClockController()
        await ctrl.fast_forward(mock_page, 10000)

        mock_page.clock.fast_forward.assert_called_once_with(10000)

    @pytest.mark.asyncio
    async def test_run_for(self):
        """Выполнение таймеров."""
        mock_page = MagicMock()
        mock_page.clock.install = AsyncMock()
        mock_page.clock.run_for = AsyncMock()

        ctrl = ClockController()
        await ctrl.run_for(mock_page, 3000)

        mock_page.clock.run_for.assert_called_once_with(3000)

    @pytest.mark.asyncio
    async def test_install_once(self):
        """Clock устанавливается только один раз."""
        mock_page = MagicMock()
        mock_page.clock.install = AsyncMock()
        mock_page.clock.freeze = AsyncMock()
        mock_page.clock.run_for = AsyncMock()

        ctrl = ClockController()
        await ctrl.freeze(mock_page, 1000)
        await ctrl.advance(mock_page, 5000)

        # install вызван только один раз
        mock_page.clock.install.assert_called_once()

    @pytest.mark.asyncio
    async def test_pre_installed(self):
        """Если clock уже установлен — install не вызывается."""
        mock_page = MagicMock()
        mock_page.clock.install = AsyncMock()
        mock_page.clock.freeze = AsyncMock()

        ctrl = ClockController(installed=True)
        await ctrl.freeze(mock_page, 1000)

        mock_page.clock.install.assert_not_called()
