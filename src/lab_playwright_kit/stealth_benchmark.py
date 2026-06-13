"""
Stealth Benchmark модуль: автоматическая оценка уровня маскировки.

Запускает headless Chromium через Playwright, навигирует на
bot.sannysoft.com и собирает результаты тестов антибот-системы.

Использование:
    >>> from lab_playwright_kit.stealth_benchmark import StealthBenchmark, StealthConfig
    >>> config = StealthConfig.advanced()
    >>> benchmark = StealthBenchmark(config)
    >>> result = await benchmark.run()
    >>> print(f"Score: {result.score}/100")
    >>> print(result.summary)

Метрики:
  - score: Общий stealth score (0-100)
  - passed: Количество пройденных тестов
  - failed: Количество проваленных тестов
  - total: Общее количество тестов
  - details: Детальная информация по каждому тесту

Целевой сайт: bot.sannysoft.com
  - Проверяет: webdriver, plugins, languages, chrome, permissions,
    webgl, hardware, codecs, iframe, WebRTC и другие сигнатуры
  - Зелёный маркер = тест пройден
  - Красный маркер = тест провален
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from loguru import logger
from playwright.async_api import Page

from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.stealth import StealthConfig, apply_stealth


@dataclass
class BenchmarkTestResult:
    """Результат одного теста антибот-системы.

    Attributes:
        name: Название теста.
        passed: Тест пройден (зелёный маркер).
        value: Значение, которое увидела антибот-система.
        expected: Ожидаемое значение.
    """
    __test__ = False
    name: str
    passed: bool
    value: str = ""
    expected: str = ""


@dataclass
class BenchmarkResult:
    __test__ = False
    """Результат полного бенчмарка stealth.

    Attributes:
        score: Общий stealth score (0-100).
        passed: Количество пройденных тестов.
        failed: Количество проваленных тестов.
        total: Общее количество тестов.
        details: Детали по каждому тесту.
        duration_ms: Время выполнения бенчмарка.
        url: URL тестовой страницы.
        error: Ошибка, если бенчмарк не удалось выполнить.
    """
    score: int = 0
    passed: int = 0
    failed: int = 0
    total: int = 0
    details: list[BenchmarkTestResult] = field(default_factory=list)
    duration_ms: float = 0.0
    url: str = ""
    error: str | None = None

    @property
    def summary(self) -> str:
        """Краткое описание результата."""
        if self.error:
            return f"Benchmark FAILED: {self.error}"
        return (
            f"Stealth Score: {self.score}/100 "
            f"({self.passed}/{self.total} passed, {self.failed} failed) "
            f"in {self.duration_ms:.0f}ms"
        )

    @property
    def passed_names(self) -> list[str]:
        """Названия пройденных тестов."""
        return [d.name for d in self.details if d.passed]

    @property
    def failed_names(self) -> list[str]:
        """Названия проваленных тестов."""
        return [d.name for d in self.details if not d.passed]


class StealthBenchmark:
    """Автоматический бенчмарк stealth-маскировки.

    Запускает headless Chromium, применяет stealth-конфигурацию,
    навигирует на bot.sannysoft.com и собирает результаты.

    Example:
        >>> config = StealthConfig.advanced()
        >>> benchmark = StealthBenchmark(config)
        >>> result = await benchmark.run()
        >>> assert result.score > 50, f"Stealth too low: {result.score}"
    """

    # URL тестовой страницы
    DEFAULT_URL = "https://bot.sannysoft.com"

    def __init__(
        self,
        config: StealthConfig | None = None,
        url: str = DEFAULT_URL,
        timeout_ms: int = 30000,
        wait_after_load_ms: int = 5000,
    ):
        """Инициализация бенчмарка.

        Args:
            config: Stealth-конфигурация для тестирования.
            url: URL тестовой страницы.
            timeout_ms: Таймаут загрузки страницы.
            wait_after_load_ms: Время ожидания после загрузки (для рендеринга).
        """
        self._config = config or StealthConfig.advanced()
        self._url = url
        self._timeout_ms = timeout_ms
        self._wait_after_load_ms = wait_after_load_ms

    async def run(self) -> BenchmarkResult:
        """Запустить бенчмарк.

        Запускает браузер, применяет stealth, навигирует на тестовую
        страницу и собирает результаты.

        Returns:
            BenchmarkResult с результатами.
        """
        start_time = time.monotonic()
        result = BenchmarkResult(url=self._url)

        try:
            async with BrowserManager(headless=True) as browser:
                page = await browser.new_page()

                # Применяем stealth
                ua = self._config.get_user_agent()
                if ua:
                    await page.context.add_init_script(
                        f"Object.defineProperty(navigator, 'userAgent', {{get: () => '{ua}'}});"
                    )
                await apply_stealth(page, self._config)

                # Навигируем на тестовую страницу
                logger.info(f"Navigating to {self._url}")
                await page.goto(self._url, timeout=self._timeout_ms, wait_until="domcontentloaded")

                # Ждём рендеринга результатов
                await page.wait_for_timeout(self._wait_after_load_ms)

                # Собираем результаты
                result = await self._collect_results(page, result)

        except Exception as e:
            logger.error(f"Benchmark failed: {e}")
            result.error = str(e)

        result.duration_ms = (time.monotonic() - start_time) * 1000
        logger.info(result.summary)
        return result

    async def _collect_results(
        self,
        page: Page,
        result: BenchmarkResult,
    ) -> BenchmarkResult:
        """Собрать результаты тестов со страницы.

        Парсит таблицу результатов на bot.sannysoft.com.
        Каждая строка содержит название теста и результат
        (зелёный = pass, красный = fail).

        Args:
            page: Playwright Page объект.
            result: BenchmarkResult для заполнения.

        Returns:
            Заполненный BenchmarkResult.
        """
        try:
            # Получаем все строки таблицы результатов
            rows = await page.query_selector_all("table tr")

            for row in rows:
                cells = await row.query_selector_all("td")
                if len(cells) < 2:
                    continue

                # Первая ячейка — название теста
                name = await cells[0].inner_text()
                name = name.strip()
                if not name:
                    continue

                # Вторая ячейка — результат (содержит цветной маркер)
                value_cell = cells[1]
                value = await value_cell.inner_text()
                value = value.strip()

                # Определяем результат по цвету или тексту
                cell_html = await value_cell.inner_html()
                passed = self._is_passed(cell_html, value)

                result.details.append(BenchmarkTestResult(
                    name=name,
                    passed=passed,
                    value=value,
                ))

            # Подсчитываем статистику
            result.total = len(result.details)
            result.passed = sum(1 for d in result.details if d.passed)
            result.failed = sum(1 for d in result.details if not d.passed)

            # Вычисляем score
            if result.total > 0:
                result.score = round((result.passed / result.total) * 100)
            else:
                result.score = 0

        except Exception as e:
            logger.warning(f"Failed to collect all results: {e}")
            result.error = f"Partial results: {e}"

        return result

    @staticmethod
    def _is_passed(html: str, text: str) -> bool:
        """Определить, пройден ли тест по HTML и тексту.

        Зелёный маркер = pass, красный = fail.
        Также проверяем текст на наличие "ok", "pass", "true".

        Args:
            html: HTML содержимое ячейки.
            text: Текст ячейки.

        Returns:
            True если тест пройден.
        """
        text_lower = text.lower()

        # Проверяем текст
        if any(word in text_lower for word in ("ok", "pass", "true", "success")):
            return True
        if any(word in text_lower for word in ("fail", "false", "error", "blocked")):
            return False

        # Проверяем цвета в HTML
        html_lower = html.lower()
        if "green" in html_lower or "#0f0" in html_lower or "#00ff00" in html_lower:
            return True
        if "red" in html_lower or "#f00" in html_lower or "#ff0000" in html_lower:
            return False

        # Проверяем эмодзи-маркеры
        if "\u2705" in text or "\u2611" in text:  # ✅, ☑
            return True
        if "\u274c" in text or "\u2612" in text:  # ❌, ☒
            return False

        # По умолчанию — считаем пройденным (если не явно указано fail)
        return True


async def run_benchmark(
    config: StealthConfig | None = None,
    url: str = StealthBenchmark.DEFAULT_URL,
) -> BenchmarkResult:
    """Запустить stealth бенчмарк с заданной конфигурацией.

    Удобная обёртка для быстрого запуска.

    Args:
        config: Stealth-конфигурация. По умолчанию — advanced().
        url: URL тестовой страницы.

    Returns:
        BenchmarkResult с результатами.

    Example:
        >>> from lab_playwright_kit.stealth_benchmark import run_benchmark
        >>> result = await run_benchmark()
        >>> print(result.summary)
    """
    benchmark = StealthBenchmark(config=config, url=url)
    return await benchmark.run()


# Backward compatibility aliases
TestResult = BenchmarkTestResult
