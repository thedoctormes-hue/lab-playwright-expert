"""
Clock Control модуль: манипуляция временем в браузере.

Использует встроенный механизм page.clock Playwright для:
  - Заморозки времени
  - Продвижения времени на заданный интервал
  - Установки фиксированного времени
  - Сброса к реальному времени

Полезно для тестирования:
  - Таймеров и обратного отсчёта
  - Сессий с истечением срока
  - Периодических задач (setInterval / setTimeout)
  - Зависимости от Date.now() / new Date()
"""
from __future__ import annotations

from loguru import logger
from playwright.async_api import Page


class ClockController:
    """Манипуляция временем в браузере через Playwright clock API.

    Использует встроенный механизм page.clock Playwright:
    - page.clock.freeze() — заморозить время
    - page.clock.run_for() — продвинуть время
    - page.clock.set_fixed_time() — установить фиксированное время
    - page.clock.resume() — сбросить к реальному времени

    Требует предварительной установки через page.clock.install().

    Example:
        >>> controller = ClockController()
        >>> await controller.freeze(page, 1700000000000)
        >>> await controller.advance(page, 5000)  # +5 секунд
        >>> await controller.reset(page)
    """

    def __init__(self, installed: bool = False):
        self._installed = installed

    async def _ensure_installed(self, page: Page) -> None:
        """Установить clock mock если ещё не установлен."""
        if not self._installed:
            await page.clock.install()
            self._installed = True
            logger.debug("Clock mock installed")

    async def freeze(self, page: Page, timestamp: int) -> None:
        """Заморозить время на указанном timestamp.

        После заморозки Date.now(), new Date(), performance.now()
        будут возвращать одно и то же значение.

        Args:
            page: Playwright Page объект
            timestamp: Unix timestamp в миллисекундах

        Example:
            >>> # Заморозить на 1 января 2024 00:00:00 UTC
            >>> await controller.freeze(page, 1704067200000)
        """
        await self._ensure_installed(page)
        await page.clock.freeze(timestamp)
        logger.info(f"Clock frozen at {timestamp}")

    async def advance(self, page: Page, ms: int) -> None:
        """Продвинуть время на указанное количество миллисекунд.

        Выполняет все запланированные таймеры (setTimeout, setInterval)
        в промежутке [текущее_время, текущее_время + ms].

        Args:
            page: Playwright Page объект
            ms: Количество миллисекунд для продвижения

        Example:
            >>> # Продвинуть на 5 секунд
            >>> await controller.advance(page, 5000)
            >>> # Продвинуть на 1 час
            >>> await controller.advance(page, 3600000)
        """
        await self._ensure_installed(page)
        await page.clock.run_for(ms)
        logger.info(f"Clock advanced by {ms}ms")

    async def set_fixed(self, page: Page, timestamp: int) -> None:
        """Установить фиксированное время.

        В отличие от freeze(), set_fixed_time() не останавливает часы,
        а подменяет возвращаемое значение Date.now() и new Date().
        Таймеры продолжают работать.

        Args:
            page: Playwright Page объект
            timestamp: Unix timestamp в миллисекундах

        Example:
            >>> # Установить фиксированное время
            >>> await controller.set_fixed(page, 1704067200000)
        """
        await self._ensure_installed(page)
        await page.clock.set_fixed_time(timestamp)
        logger.info(f"Clock set to fixed time {timestamp}")

    async def reset(self, page: Page) -> None:
        """Сбросить часы к реальному времени.

        Отключает все манипуляции с временем, возвращая
        нормальное поведение Date.now(), new Date(), таймеров.

        Args:
            page: Playwright Page объект

        Example:
            >>> await controller.reset(page)
        """
        await page.clock.resume()
        logger.info("Clock reset to real time")

    async def fast_forward(self, page: Page, ms: int) -> None:
        """Быстро продвинуть время, выполнив все таймеры.

        Аналог advance() — выполняет все запланированные таймеры
        в промежутке. Разница в семантике: fast_forward подчёркивает
        что таймеры будут выполнены.

        Args:
            page: Playwright Page объект
            ms: Количество миллисекунд для продвижения

        Example:
            >>> # Выполнить все таймеры в ближайшие 10 секунд
            >>> await controller.fast_forward(page, 10000)
        """
        await self._ensure_installed(page)
        await page.clock.fast_forward(ms)
        logger.info(f"Clock fast-forwarded by {ms}ms")

    async def run_for(self, page: Page, ms: int) -> None:
        """Выполнить таймеры на указанный интервал.

        Синоним advance() — выполняет все setTimeout/setInterval
        в промежутке [текущее_время, текущее_время + ms].

        Args:
            page: Playwright Page объект
            ms: Количество миллисекунд

        Example:
            >>> await controller.run_for(page, 3000)  # выполнить таймеры на 3 сек
        """
        await self._ensure_installed(page)
        await page.clock.run_for(ms)
        logger.info(f"Clock run_for {ms}ms")
