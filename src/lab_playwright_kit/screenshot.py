"""
Скриншоты, PDF, визуальный захват.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from loguru import logger
from playwright.async_api import Page


class ScreenshotMaker:
    """Создание скриншотов и PDF через Playwright."""

    def __init__(self, output_dir: str = "/tmp/playwright_screenshots"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _filename(self, prefix: str, suffix: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return str(self.output_dir / f"{prefix}_{ts}.{suffix}")

    async def full_page(self, page: Page, prefix: str = "full") -> str:
        """Скриншот всей страницы."""
        path = self._filename(prefix, "png")
        await page.screenshot(path=path, full_page=True)
        logger.info(f"Full page screenshot: {path}")
        return path

    async def viewport(self, page: Page, prefix: str = "viewport") -> str:
        """Скриншот видимой области."""
        path = self._filename(prefix, "png")
        await page.screenshot(path=path)
        logger.info(f"Viewport screenshot: {path}")
        return path

    async def element(self, page: Page, selector: str, prefix: str = "element") -> str:
        """Скриншот конкретного элемента."""
        path = self._filename(prefix, "png")
        element = page.locator(selector)
        await element.screenshot(path=path)
        logger.info(f"Element screenshot: {path}")
        return path

    async def pdf(self, page: Page, prefix: str = "page") -> str:
        """Экспорт страницы в PDF."""
        path = self._filename(prefix, "pdf")
        await page.pdf(path=path, format="A4", print_background=True)
        logger.info(f"PDF: {path}")
        return path

    async def compare(
        self,
        page: Page,
        baseline_path: str,
        threshold: float = 0.1,
    ) -> tuple[bool, float, str]:
        """Сравнить текущий вид с эталонным скриншотом.

        Returns:
            (match, diff_ratio, diff_path)
        """
        import io

        from PIL import Image

        # Сделать текущий скриншот
        current_bytes = await page.screenshot()

        # Загрузить оба изображения
        current_img = Image.open(io.BytesIO(current_bytes)).convert("RGB")
        baseline_img = Image.open(baseline_path).convert("RGB")

        # Привести к одному размеру
        if current_img.size != baseline_img.size:
            current_img = current_img.resize(baseline_img.size)

        # Pix-by-pix сравнение
        import itertools
        pixels_current = list(current_img.getdata())
        pixels_baseline = list(baseline_img.getdata())

        diff_pixels = sum(
            1 for p1, p2 in zip(pixels_current, pixels_baseline)
            if abs(p1[0] - p2[0]) + abs(p1[1] - p2[1]) + abs(p1[2] - p2[2]) > 30
        )
        total_pixels = len(pixels_current)
        diff_ratio = diff_pixels / total_pixels if total_pixels else 1.0

        match = diff_ratio <= threshold

        # Сохранить diff
        diff_path = self._filename("diff", "png")
        if not match:
            # Визуализация отличий
            diff_img = Image.new("RGB", baseline_img.size)
            for i, (p1, p2) in enumerate(zip(itertools.islice(pixels_current, total_pixels), pixels_baseline)):
                if abs(p1[0]-p2[0]) + abs(p1[1]-p2[1]) + abs(p1[2]-p2[2]) > 30:
                    diff_img.putpixel((i % baseline_img.size[0], i // baseline_img.size[0]), (255, 0, 0))
            diff_img.save(diff_path)

        logger.info(f"Compare: match={match}, diff={diff_ratio:.2%}")
        return match, diff_ratio, diff_path
