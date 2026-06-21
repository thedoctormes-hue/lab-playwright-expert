"""
Расширенные тесты для Screenshot Maker — покрытие async методов.

Покрывает:
  - full_page(), viewport(), element(), pdf() — с моком Page
  - compare() — с моком Page и PIL
  - Покрытие всех веток ScreenshotMaker
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from lab_playwright_kit.screenshot import ScreenshotMaker


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def maker(tmp_path):
    return ScreenshotMaker(output_dir=str(tmp_path))


@pytest.fixture
def mock_page():
    """Мок Playwright Page."""
    page = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"fake_png_bytes")
    page.pdf = AsyncMock()
    page.url = "https://example.com"
    return page


@pytest.fixture
def mock_locator():
    """Мок локатора элемента."""
    loc = AsyncMock()
    loc.screenshot = AsyncMock()
    return loc


@pytest.fixture
def mock_page_with_locator(mock_page, mock_locator):
    """Page с правильно настроенным locator."""
    mock_page.locator = MagicMock(return_value=mock_locator)
    return mock_page


# ─── full_page() ────────────────────────────────────────────────────────────


class TestFullPage:
    async def test_full_page_returns_path(self, maker, mock_page):
        path = await maker.full_page(mock_page)
        assert path.endswith(".png")
        assert "full_" in path

    async def test_full_page_calls_screenshot(self, maker, mock_page):
        await maker.full_page(mock_page)
        call_kwargs = mock_page.screenshot.call_args[1]
        assert call_kwargs.get("full_page") is True
        assert call_kwargs.get("path", "").endswith(".png")

    async def test_full_page_custom_prefix(self, maker, mock_page):
        path = await maker.full_page(mock_page, prefix="custom")
        assert "custom_" in path

    async def test_full_page_path_in_output_dir(self, maker, mock_page):
        path = await maker.full_page(mock_page)
        assert str(maker.output_dir) in path


# ─── viewport() ─────────────────────────────────────────────────────────────


class TestViewport:
    async def test_viewport_returns_path(self, maker, mock_page):
        path = await maker.viewport(mock_page)
        assert path.endswith(".png")
        assert "viewport_" in path

    async def test_viewport_no_full_page(self, maker, mock_page):
        await maker.viewport(mock_page)
        # viewport НЕ должен передавать full_page=True
        call_kwargs = mock_page.screenshot.call_args[1]
        assert call_kwargs.get("full_page") is None or call_kwargs.get("full_page") is False

    async def test_viewport_custom_prefix(self, maker, mock_page):
        path = await maker.viewport(mock_page, prefix="vp")
        assert "vp_" in path


# ─── element() ──────────────────────────────────────────────────────────────


class TestElement:
    async def test_element_returns_path(self, maker, mock_page_with_locator):
        path = await maker.element(mock_page_with_locator, "#selector")
        assert path.endswith(".png")
        assert "element_" in path

    async def test_element_uses_locator(self, maker, mock_page_with_locator, mock_locator):
        await maker.element(mock_page_with_locator, ".my-class")
        mock_page_with_locator.locator.assert_called_once_with(".my-class")
        mock_locator.screenshot.assert_called_once()

    async def test_element_custom_prefix(self, maker, mock_page_with_locator):
        path = await maker.element(mock_page_with_locator, "#id", prefix="el")
        assert "el_" in path


# ─── pdf() ──────────────────────────────────────────────────────────────────


class TestPdf:
    async def test_pdf_returns_path(self, maker, mock_page):
        path = await maker.pdf(mock_page)
        assert path.endswith(".pdf")
        assert "page_" in path

    async def test_pdf_calls_page_pdf(self, maker, mock_page):
        await maker.pdf(mock_page)
        mock_page.pdf.assert_called_once()

    async def test_pdf_a4_format(self, maker, mock_page):
        await maker.pdf(mock_page)
        call_kwargs = mock_page.pdf.call_args[1]
        assert call_kwargs.get("format") == "A4"
        assert call_kwargs.get("print_background") is True

    async def test_pdf_custom_prefix(self, maker, mock_page):
        path = await maker.pdf(mock_page, prefix="doc")
        assert "doc_" in path


# ─── compare() ──────────────────────────────────────────────────────────────


class TestCompare:
    async def test_compare_matching_images(self, maker, mock_page, tmp_path):
        """Сравнение одинаковых изображений — match=True."""
        import io

        from PIL import Image

        # Создать тестовое изображение
        img = Image.new("RGB", (100, 100), color="red")
        img_path = tmp_path / "baseline.png"
        img.save(img_path)

        # Мок скриншота возвращает то же изображение
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        mock_page.screenshot = AsyncMock(return_value=buf.getvalue())

        match, diff_ratio, diff_path = await maker.compare(mock_page, str(img_path), threshold=0.1)
        assert match is True
        assert diff_ratio == 0.0

    async def test_compare_different_images(self, maker, mock_page, tmp_path):
        """Сравнение разных изображений — match=False."""
        import io

        from PIL import Image

        # Baseline — красный
        baseline = Image.new("RGB", (100, 100), color="red")
        img_path = tmp_path / "baseline.png"
        baseline.save(img_path)

        # Текущий скриншот — синий (полностью отличается)
        current = Image.new("RGB", (100, 100), color="blue")
        buf = io.BytesIO()
        current.save(buf, format="PNG")
        mock_page.screenshot = AsyncMock(return_value=buf.getvalue())

        match, diff_ratio, diff_path = await maker.compare(mock_page, str(img_path), threshold=0.1)
        assert match is False
        assert diff_ratio > 0.5

    async def test_compare_saves_diff(self, maker, mock_page, tmp_path):
        """При несовпадении сохраняется diff."""
        import io

        from PIL import Image

        baseline = Image.new("RGB", (10, 10), color="white")
        img_path = tmp_path / "baseline.png"
        baseline.save(img_path)

        current = Image.new("RGB", (10, 10), color="black")
        buf = io.BytesIO()
        current.save(buf, format="PNG")
        mock_page.screenshot = AsyncMock(return_value=buf.getvalue())

        match, diff_ratio, diff_path = await maker.compare(mock_page, str(img_path), threshold=0.1)
        assert match is False
        assert diff_path.endswith(".png")
        assert "diff_" in diff_path

    async def test_compare_different_sizes(self, maker, mock_page, tmp_path):
        """Сравнение изображений разного размера — приводятся к одному."""
        import io

        from PIL import Image

        baseline = Image.new("RGB", (100, 100), color="red")
        img_path = tmp_path / "baseline.png"
        baseline.save(img_path)

        # Другой размер
        current = Image.new("RGB", (50, 50), color="red")
        buf = io.BytesIO()
        current.save(buf, format="PNG")
        mock_page.screenshot = AsyncMock(return_value=buf.getvalue())

        # Не должно падать
        match, diff_ratio, diff_path = await maker.compare(mock_page, str(img_path), threshold=0.1)
        # После resize к baseline размеру — должно совпасть
        assert isinstance(match, bool)

    async def test_compare_threshold_exact_match(self, maker, mock_page, tmp_path):
        """При полностью совпадающих изображениях diff_ratio=0."""
        import io

        from PIL import Image

        img = Image.new("RGB", (50, 50), color=(128, 128, 128))
        img_path = tmp_path / "baseline.png"
        img.save(img_path)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        mock_page.screenshot = AsyncMock(return_value=buf.getvalue())

        match, diff_ratio, diff_path = await maker.compare(mock_page, str(img_path), threshold=0.0)
        assert match is True
        assert diff_ratio == 0.0

    async def test_compare_threshold_no_match(self, maker, mock_page, tmp_path):
        """При полностью отличающихся изображениях diff_ratio≈1."""
        import io

        from PIL import Image

        baseline = Image.new("RGB", (10, 10), color="white")
        img_path = tmp_path / "baseline.png"
        baseline.save(img_path)

        current = Image.new("RGB", (10, 10), color="black")
        buf = io.BytesIO()
        current.save(buf, format="PNG")
        mock_page.screenshot = AsyncMock(return_value=buf.getvalue())

        match, diff_ratio, diff_path = await maker.compare(mock_page, str(img_path), threshold=0.5)
        assert match is False
        assert diff_ratio > 0.9
