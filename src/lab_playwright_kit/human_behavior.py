"""
Human Behavior Engine — имитация человеческого поведения в браузере.

Генерирует реалистичные:
  - Движения мыши (кривые Безье с джиттером)
  - Скроллинг (переменная скорость, паузы, микро-движения)
  - Клики (рандомные задержки до и после)
  - Набор текста (переменная скорость, ошибки, паузы)
  - Паттерны чтения (скролл → пауза → скролл → пауза)

Ключевой принцип: ВСЁ рандомизировано, но в рамках реалистичных диапазонов.
Никаких фиксированных задержек — бота выдетектят мгновенно.

Использование:
    >>> behavior = HumanBehaviorEngine(page, profile="casual_reader")
    >>> await behavior.move_mouse_to(500, 300)
    >>> await behavior.click()
    >>> await behavior.scroll_down(pages=2)
    >>> await behavior.type_text("Привет мир!")
    >>> await behavior.read_page()
"""
from __future__ import annotations

import asyncio
import math
import random
import time
from dataclasses import dataclass

from loguru import logger
from playwright.async_api import Locator, Page


@dataclass
class BehaviorProfile:
    """Профиль поведения — набор параметров для рандомизации.

    Каждый профиль описывает "тип пользователя":
    - casual_reader: читает статьи, медленно скроллит
    - power_user: быстро навигирует, быстро печатает
    - researcher: долго читает, копирует текст, делает скриншоты
    - social_media: лайки, комменты, быстрый скролл ленты
    """

    name: str = "casual_reader"

    # Мышь
    mouse_move_min_ms: int = 200
    mouse_move_max_ms: int = 800
    mouse_jitter_px: float = 2.0  # джиттер в пикселях
    mouse_bezier_points: int = 3  # количество контрольных точек

    # Клик
    click_delay_before_ms: tuple[int, int] = (50, 200)
    click_delay_after_ms: tuple[int, int] = (100, 500)
    double_click_chance: float = 0.05

    # Скролл
    scroll_speed_px: tuple[int, int] = (100, 400)  # пикселей за "тик"
    scroll_interval_ms: tuple[int, int] = (50, 150)  # интервал между тиками
    scroll_pause_chance: float = 0.15  # шанс паузы при скролле
    scroll_pause_ms: tuple[int, int] = (500, 3000)
    scroll_reverse_chance: float = 0.05  # шанс прокрутить назад (как реальный юзер)

    # Чтение
    reading_speed_wpm: tuple[int, int] = (200, 400)  # слов в минуту
    reading_pause_chance: float = 0.3
    reading_pause_ms: tuple[int, int] = (1000, 5000)

    # Набор текста
    typing_speed_wpm: tuple[int, int] = (150, 350)
    typing_error_chance: float = 0.02  # шанс ошибки (и исправления)
    typing_pause_chance: float = 0.1  # шанс паузы при наборе
    typing_pause_ms: tuple[int, int] = (200, 1500)

    # Общее
    action_delay_ms: tuple[int, int] = (500, 2000)  # задержка между действиями
    idle_chance: float = 0.1  # шанс "зависнуть" (как реальный юзер)
    idle_ms: tuple[int, int] = (2000, 8000)


# ─── Пресеты профилей ────────────────────────────────────────────────────────

BEHAVIOR_PROFILES: dict[str, BehaviorProfile] = {
    "casual_reader": BehaviorProfile(
        name="casual_reader",
        mouse_move_min_ms=300,
        mouse_move_max_ms=1000,
        scroll_speed_px=(80, 300),
        scroll_interval_ms=(80, 200),
        scroll_pause_chance=0.2,
        scroll_pause_ms=(1000, 4000),
        reading_speed_wpm=(180, 300),
        typing_speed_wpm=(120, 250),
        action_delay_ms=(800, 3000),
    ),
    "power_user": BehaviorProfile(
        name="power_user",
        mouse_move_min_ms=100,
        mouse_move_max_ms=400,
        scroll_speed_px=(200, 600),
        scroll_interval_ms=(30, 80),
        scroll_pause_chance=0.05,
        scroll_pause_ms=(200, 1000),
        reading_speed_wpm=(350, 600),
        typing_speed_wpm=(300, 500),
        action_delay_ms=(200, 800),
    ),
    "researcher": BehaviorProfile(
        name="researcher",
        mouse_move_min_ms=200,
        mouse_move_max_ms=700,
        scroll_speed_px=(50, 200),
        scroll_interval_ms=(100, 300),
        scroll_pause_chance=0.35,
        scroll_pause_ms=(2000, 8000),
        reading_speed_wpm=(150, 250),
        typing_speed_wpm=(100, 200),
        action_delay_ms=(1000, 5000),
    ),
    "social_media": BehaviorProfile(
        name="social_media",
        mouse_move_min_ms=150,
        mouse_move_max_ms=500,
        scroll_speed_px=(150, 500),
        scroll_interval_ms=(40, 120),
        scroll_pause_chance=0.25,
        scroll_pause_ms=(500, 2500),
        reading_speed_wpm=(250, 450),
        typing_speed_wpm=(180, 350),
        action_delay_ms=(300, 1500),
    ),
}


class HumanBehaviorEngine:
    """Движок человеческого поведения для Playwright.

    Имитирует реалистичное поведение пользователя:
    движения мыши по кривым Безье, переменный скроллинг,
    реалистичный набор текста с ошибками.

    Использование:
        >>> behavior = HumanBehaviorEngine(page, profile="casual_reader")
        >>> await behavior.move_mouse_to(500, 300)
        >>> await behavior.click()
        >>> await behavior.scroll_down(pages=2)
        >>> await behavior.read_page()
    """

    def __init__(
        self,
        page: Page,
        profile: str | BehaviorProfile = "casual_reader",
        seed: int | None = None,
    ):
        self.page = page
        if isinstance(profile, str):
            self.profile = BEHAVIOR_PROFILES.get(profile, BehaviorProfile())
        else:
            self.profile = profile

        self._rng = random.Random(seed)
        self._current_x: float = 0
        self._current_y: float = 0

    # ─── Мышь ──────────────────────────────────────────────────────────────

    async def move_mouse_to(
        self,
        x: int,
        y: int,
        steps: int | None = None,
    ) -> None:
        """Переместить мышь к координатам с реалистичной траекторией.

        Использует кривые Безье для естественного движения.
        Добавляет микро-джиттер имитацию тремора руки.

        Args:
            x: Целевая X координата
            y: Целевая Y координата
            steps: Количество шагов (авто если None)
        """
        if steps is None:
            distance = math.sqrt((x - self._current_x) ** 2 + (y - self._current_y) ** 2)
            steps = max(5, int(distance / 50))

        # Генерируем контрольные точки Безье
        points = self._generate_bezier_points(
            self._current_x, self._current_y, x, y, steps
        )

        # Двигаем мышь по точкам с переменной скоростью
        for px, py in points:
            # Добавляем джиттер
            jitter_x = self._rng.gauss(0, self.profile.mouse_jitter_px)
            jitter_y = self._rng.gauss(0, self.profile.mouse_jitter_px)

            await self.page.mouse.move(px + jitter_x, py + jitter_y)

            # Переменная задержка между микро-движениями
            delay = self._rng.uniform(0.005, 0.02)
            await asyncio.sleep(delay)

        self._current_x = x
        self._current_y = y

    async def move_mouse_to_element(
        self,
        locator: Locator | str,
        offset_x: int | None = None,
        offset_y: int | None = None,
    ) -> None:
        """Переместить мышь к элементу с рандомным смещением внутри.

        Args:
            locator: Playwright Locator или строка-селектор
            offset_x: Смещение X от центра (авто если None)
            offset_y: Смещение Y от центра (авто если None)
        """
        if isinstance(locator, str):
            locator = self.page.locator(locator)
        box = await locator.bounding_box()
        if not box:
            logger.warning("Element not visible, cannot move mouse to it")
            return

        # Рандомная точка внутри элемента (не всегда центр!)
        if offset_x is None:
            offset_x = self._rng.uniform(box["width"] * 0.2, box["width"] * 0.8)
        if offset_y is None:
            offset_y = self._rng.uniform(box["height"] * 0.2, box["height"] * 0.8)

        target_x = box["x"] + offset_x
        target_y = box["y"] + offset_y

        await self.move_mouse_to(target_x, target_y)

    async def click(
        self,
        x: int | None = None,
        y: int | None = None,
        locator: Locator | None = None,
        button: str = "left",
    ) -> None:
        """Клик с реалистичными задержками.

        Args:
            x: X координата (если не указан locator)
            y: Y координата
            locator: Playwright Locator (приоритетнее координат)
            button: Кнопка мыши — left, right, middle
        """
        # Задержка перед кликом
        delay_before = self._rng.uniform(*self.profile.click_delay_before_ms) / 1000
        await asyncio.sleep(delay_before)

        if locator:
            await self.move_mouse_to_element(locator)
            await locator.click(button=button)
        elif x is not None and y is not None:
            await self.move_mouse_to(x, y)
            await self.page.mouse.click(x, y, button=button)
        else:
            # Клик в текущую позицию
            await self.page.mouse.click(self._current_x, self._current_y, button=button)

        # Задержка после клика
        delay_after = self._rng.uniform(*self.profile.click_delay_after_ms) / 1000
        await asyncio.sleep(delay_after)

    async def double_click(
        self,
        x: int | None = None,
        y: int | None = None,
        locator: Locator | None = None,
    ) -> None:
        """Двойной клик."""
        if locator:
            await locator.dblclick()
        elif x is not None and y is not None:
            await self.page.mouse.dblclick(x, y)

    # ─── Скроллинг ─────────────────────────────────────────────────────────

    async def scroll_down(
        self,
        pages: float = 1.0,
        smooth: bool = True,
    ) -> None:
        """Прокрутить вниз на указанное количество "страниц".

        Имитирует реальное поведение: переменная скорость,
        случайные паузы, иногда прокрутка назад.

        Args:
            pages: Количество страниц (0.5 = половина экрана)
            smooth: Плавный скролл (True) или мгновенный (False)
        """
        viewport_height = 800  # примерная высота viewport
        direction = 1 if pages >= 0 else -1
        total_px = int(viewport_height * abs(pages))
        scrolled = 0

        while scrolled < total_px:
            # Случайная дистанция за тик
            tick_px = self._rng.randint(*self.profile.scroll_speed_px)
            tick_px = min(tick_px, total_px - scrolled)
            delta = tick_px * direction

            if smooth:
                await self.page.mouse.wheel(0, delta)
            else:
                await self.page.evaluate(f"window.scrollBy(0, {delta})")

            scrolled += tick_px

            # Случайная пауза (как будто читает контент)
            if self._rng.random() < self.profile.scroll_pause_chance:
                pause = self._rng.uniform(*self.profile.scroll_pause_ms) / 1000
                await asyncio.sleep(pause)

            # Микро-пауза между тиками
            interval = self._rng.uniform(*self.profile.scroll_interval_ms) / 1000
            await asyncio.sleep(interval)

            # Иногда прокручиваем немного назад (реальное поведение!)
            if self._rng.random() < self.profile.scroll_reverse_chance:
                reverse_px = self._rng.randint(30, 100)
                await self.page.mouse.wheel(0, -reverse_px * direction)
                await asyncio.sleep(self._rng.uniform(0.3, 1.0))

    async def scroll_up(self, pages: float = 1.0, smooth: bool = True) -> None:
        """Прокрутить вверх."""
        await self.scroll_down(pages=-pages, smooth=smooth)

    async def scroll_to_element(self, locator: Locator) -> None:
        """Прокрутить к элементу с реалистичным поведением."""
        await locator.scroll_into_view_if_needed()
        # Небольшая пауза после скролла к элементу
        await asyncio.sleep(self._rng.uniform(0.3, 0.8))

    async def scroll_to_top(self) -> None:
        """Прокрутить наверх."""
        await self.page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(self._rng.uniform(0.5, 1.5))

    async def scroll_to_bottom(self) -> None:
        """Прокрутить в самый низ."""
        await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(self._rng.uniform(0.5, 1.5))

    # ─── Набор текста ──────────────────────────────────────────────────────

    async def type_text(
        self,
        text: str,
        locator: Locator | None = None,
        clear_first: bool = True,
        error_rate: float | None = None,
    ) -> None:
        """Набрать текст с реалистичной скоростью и ошибками.

        Имитирует реальный набор: переменная скорость между символами,
        случайные ошибки с исправлением, паузы на сложных символах.

        Args:
            text: Текст для набора
            locator: Элемент ввода (если None — ввод в фокусированный элемент)
            clear_first: Очистить поле перед вводом
            error_rate: Шанс ошибки (по умолчанию из профиля)
        """
        if error_rate is None:
            error_rate = self.profile.typing_error_chance

        if locator:
            await self.move_mouse_to_element(locator)
            await self.click(locator=locator)
            if clear_first:
                await locator.fill("")

        wpm = self._rng.uniform(*self.profile.typing_speed_wpm)
        base_delay = 60.0 / (wpm * 5)  # 5 символов = 1 слово в среднем

        for i, char in enumerate(text):
            # Случайная ошибка
            if self._rng.random() < error_rate and char.isalpha():
                # Печатаем не ту букву
            # Печатаем не ту букву
                wrong_char = self._rng.choice("йцукенгшщзхъфывапролджэячсмитьбю")
                if locator:
                    await locator.press(wrong_char)
                else:
                    await self.page.keyboard.press(wrong_char)
                await asyncio.sleep(base_delay * 0.5)
                # Исправляем
                if locator:
                    await locator.press("Backspace")
                else:
                    await self.page.keyboard.press("Backspace")
                await asyncio.sleep(base_delay * 0.3)

            # Печатаем правильный символ
            if locator:
                await locator.press(char)
            else:
                await self.page.keyboard.press(char)

            # Переменная задержка между символами
            delay = base_delay * self._rng.uniform(0.5, 1.5)

            # Дольше на спецсимволах и пробелах
            if char in " .,!?;:\n":
                delay *= self._rng.uniform(1.5, 3.0)

            # Случайная пауза (как будто думает)
            if self._rng.random() < self.profile.typing_pause_chance:
                delay += self._rng.uniform(*self.profile.typing_pause_ms) / 1000

            await asyncio.sleep(delay)

    async def type_like_human(
        self,
        text: str,
        locator: Locator | None = None,
    ) -> None:
        """Набрать текст с максимально человечным паттерном.

        Использует type с задержкой вместо press для более реалистичного ввода.
        """
        if locator:
            await self.move_mouse_to_element(locator)
            await self.click(locator=locator)
            await locator.fill("")

        # Разбиваем на "слова" и печатаем группами
        words = text.split(" ")
        for i, word in enumerate(words):
            # Печатаем слово
            delay_per_char = self._rng.uniform(0.03, 0.12)
            if locator:
                await locator.type(word, delay=delay_per_char * 1000)
            else:
                await self.page.keyboard.type(word, delay=delay_per_char * 1000)

            # Пробел между словами (кроме последнего)
            if i < len(words) - 1:
                space_delay = self._rng.uniform(0.05, 0.2)
                await asyncio.sleep(space_delay)

            # Пауза после "сложных" слов
            if len(word) > 8:
                await asyncio.sleep(self._rng.uniform(0.2, 0.5))

    # ─── Чтение ────────────────────────────────────────────────────────────

    async def read_page(self, text_length: int | None = None) -> None:
        """Имитировать чтение страницы.

        Скроллит медленно, делает паузы, иногда двигает мышь
        (как будто следит за текстом).

        Args:
            text_length: Длина текста в символах (авто если None)
        """
        if text_length is None:
            # Пытаемся оценить длину текста
            try:
                text_length = await self.page.evaluate(
                    "() => document.body.innerText.length"
                )
            except Exception:
                text_length = 2000

        # Время чтения на основе скорости
        wpm = self._rng.uniform(*self.profile.reading_speed_wpm)
        words = text_length / 5  # ~5 символов на слово
        read_time_seconds = (words / wpm) * 60

        # Ограничиваем разумными пределами
        read_time_seconds = max(3, min(read_time_seconds, 120))

        logger.debug(f"Reading page: ~{text_length} chars, est. {read_time_seconds:.0f}s")

        start = time.monotonic()
        while time.monotonic() - start < read_time_seconds:
            # Скроллим понемногu
            if self._rng.random() < 0.4:
                await self.scroll_down(pages=self._rng.uniform(0.1, 0.3))

            # Иногда двигаем мышь (следим за текстом)
            if self._rng.random() < 0.2:
                x = self._rng.uniform(100, 800)
                y = self._rng.uniform(200, 600)
                await self.move_mouse_to(x, y)

            # Пауза
            pause = self._rng.uniform(1, 4)
            await asyncio.sleep(pause)

    async def read_article(self) -> None:
        """Имитировать чтение статьи — медленно и внимательно."""
        original_profile = self.profile
        self.profile = BehaviorProfile(
            name="article_reader",
            scroll_speed_px=(30, 100),
            scroll_interval_ms=(150, 400),
            scroll_pause_chance=0.4,
            scroll_pause_ms=(2000, 6000),
        )
        await self.read_page()
        self.profile = original_profile

    # ─── Утилиты ───────────────────────────────────────────────────────────

    async def random_idle(self) -> None:
        """Случайная пауза — как будто пользователь отвлёкся."""
        if self._rng.random() < self.profile.idle_chance:
            idle_time = self._rng.uniform(*self.profile.idle_ms) / 1000
            logger.debug(f"Idling for {idle_time:.1f}s")
            await asyncio.sleep(idle_time)

    async def wait_between_actions(self) -> None:
        """Задержка между действиями."""
        delay = self._rng.uniform(*self.profile.action_delay_ms) / 1000
        await asyncio.sleep(delay)

    async def hover(self, locator: Locator, duration_ms: int | None = None) -> None:
        """Навести на элемент с задержкой."""
        await self.move_mouse_to_element(locator)
        if duration_ms is None:
            duration_ms = self._rng.randint(300, 1500)
        await asyncio.sleep(duration_ms / 1000)

    # ─── Внутренние методы ─────────────────────────────────────────────────

    def _generate_bezier_points(
        self,
        x0: float, y0: float,
        x3: float, y3: float,
        num_points: int,
    ) -> list[tuple[float, float]]:
        """Генерировать точки на кривой Безье.

        Создаёт естественную траекторию движения мыши
        с рандомными контрольными точками.
        """
        # Контрольные точки — рандомные, но близкие к линии
        dx = x3 - x0
        dy = y3 - y0

        # Перпендикулярное смещение для естественности
        perp_x = -dy * self._rng.uniform(-0.3, 0.3)
        perp_y = dx * self._rng.uniform(-0.3, 0.3)

        x1 = x0 + dx * 0.25 + perp_x
        y1 = y0 + dy * 0.25 + perp_y
        x2 = x0 + dx * 0.75 - perp_x
        y2 = y0 + dy * 0.75 - perp_y

        points = []
        for i in range(num_points + 1):
            t = i / num_points
            # Кубическая кривая Безье
            mt = 1 - t
            x = mt**3 * x0 + 3 * mt**2 * t * x1 + 3 * mt * t**2 * x2 + t**3 * x3
            y = mt**3 * y0 + 3 * mt**2 * t * y1 + 3 * mt * t**2 * y2 + t**3 * y3
            points.append((x, y))

        return points
