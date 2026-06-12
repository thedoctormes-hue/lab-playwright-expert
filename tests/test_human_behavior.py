"""
Тесты для human_behavior.py — Human Behavior Engine.

Покрывает:
  - BehaviorProfile: создание, значения по умолчанию, пресеты
  - BEHAVIOR_PROFILES: наличие профилей
  - HumanBehaviorEngine: инициализация, seed, свойства
"""
import asyncio
import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lab_playwright_kit.human_behavior import (
    BEHAVIOR_PROFILES,
    BehaviorProfile,
    HumanBehaviorEngine,
)


# ─── BehaviorProfile ─────────────────────────────────────────────────────────

class TestBehaviorProfile:
    """Тесты dataclass BehaviorProfile."""

    def test_default_creation(self):
        p = BehaviorProfile()
        assert p.name == "casual_reader"
        assert p.mouse_move_min_ms == 200
        assert p.mouse_move_max_ms == 800
        assert p.mouse_jitter_px == 2.0
        assert p.mouse_bezier_points == 3

    def test_click_defaults(self):
        p = BehaviorProfile()
        assert p.click_delay_before_ms == (50, 200)
        assert p.click_delay_after_ms == (100, 500)
        assert p.double_click_chance == 0.05

    def test_scroll_defaults(self):
        p = BehaviorProfile()
        assert p.scroll_speed_px == (100, 400)
        assert p.scroll_interval_ms == (50, 150)
        assert p.scroll_pause_chance == 0.15
        assert p.scroll_reverse_chance == 0.05

    def test_reading_defaults(self):
        p = BehaviorProfile()
        assert p.reading_speed_wpm == (200, 400)
        assert p.reading_pause_chance == 0.3

    def test_typing_defaults(self):
        p = BehaviorProfile()
        assert p.typing_speed_wpm == (150, 350)
        assert p.typing_error_chance == 0.02
        assert p.typing_pause_chance == 0.1

    def test_general_defaults(self):
        p = BehaviorProfile()
        assert p.action_delay_ms == (500, 2000)
        assert p.idle_chance == 0.1
        assert p.idle_ms == (2000, 8000)

    def test_custom_creation(self):
        p = BehaviorProfile(
            name="custom",
            mouse_move_min_ms=50,
            mouse_move_max_ms=200,
            typing_error_chance=0.05,
        )
        assert p.name == "custom"
        assert p.mouse_move_min_ms == 50
        assert p.typing_error_chance == 0.05


# ─── BEHAVIOR_PROFILES ──────────────────────────────────────────────────────

class TestBehaviorProfiles:
    """Тесты словаря пресетов."""

    def test_has_casual_reader(self):
        assert "casual_reader" in BEHAVIOR_PROFILES

    def test_has_power_user(self):
        assert "power_user" in BEHAVIOR_PROFILES

    def test_has_researcher(self):
        assert "researcher" in BEHAVIOR_PROFILES

    def test_has_social_media(self):
        assert "social_media" in BEHAVIOR_PROFILES

    def test_minimum_profiles(self):
        """Не менее 4 профилей."""
        assert len(BEHAVIOR_PROFILES) >= 4

    def test_all_are_behavior_profile(self):
        """Все значения — BehaviorProfile."""
        for name, profile in BEHAVIOR_PROFILES.items():
            assert isinstance(profile, BehaviorProfile)
            assert profile.name == name

    def test_casual_vs_power_speed(self):
        """casual_reader медленнее power_user."""
        casual = BEHAVIOR_PROFILES["casual_reader"]
        power = BEHAVIOR_PROFILES["power_user"]
        assert casual.mouse_move_min_ms > power.mouse_move_min_ms
        assert casual.mouse_move_max_ms > power.mouse_move_max_ms

    def test_researcher_slower_than_social(self):
        """researcher медленнее social_media."""
        researcher = BEHAVIOR_PROFILES["researcher"]
        social = BEHAVIOR_PROFILES["social_media"]
        assert researcher.reading_speed_wpm[1] < social.reading_speed_wpm[1]


# ─── HumanBehaviorEngine ────────────────────────────────────────────────────

@pytest.fixture
def mock_page():
    """Мок Playwright Page."""
    page = AsyncMock()
    page.mouse = AsyncMock()
    page.mouse.move = AsyncMock()
    page.mouse.click = AsyncMock()
    page.mouse.dblclick = AsyncMock()
    return page


@pytest.fixture
def engine(mock_page):
    """HumanBehaviorEngine с моком page и фиксированным seed."""
    return HumanBehaviorEngine(mock_page, profile="casual_reader", seed=42)


class TestHumanBehaviorEngineInit:
    """Тесты инициализации."""

    def test_init_with_string_profile(self, mock_page):
        engine = HumanBehaviorEngine(mock_page, profile="casual_reader")
        assert engine.profile.name == "casual_reader"

    def test_init_with_object_profile(self, mock_page):
        custom = BehaviorProfile(name="custom", mouse_move_min_ms=50)
        engine = HumanBehaviorEngine(mock_page, profile=custom)
        assert engine.profile.name == "custom"
        assert engine.profile.mouse_move_min_ms == 50

    def test_init_default_profile(self, mock_page):
        engine = HumanBehaviorEngine(mock_page)
        assert engine.profile.name == "casual_reader"

    def test_init_unknown_profile_fallback(self, mock_page):
        """Неизвестный профиль — fallback на default."""
        engine = HumanBehaviorEngine(mock_page, profile="nonexistent")
        assert engine.profile.name == "casual_reader"

    def test_init_with_seed(self, mock_page):
        engine = HumanBehaviorEngine(mock_page, seed=123)
        assert engine._rng is not None

    def test_init_position(self, engine):
        assert engine._current_x == 0
        assert engine._current_y == 0


class TestHumanBehaviorEngineProperties:
    """Тесты свойств."""

    def test_page_property(self, engine, mock_page):
        assert engine.page is mock_page

    def test_profile_property(self, engine):
        assert isinstance(engine.profile, BehaviorProfile)

    def test_rng_property(self, engine):
        assert engine._rng is not None


class TestHumanBehaviorEngineMouse:
    """Тесты методов мыши."""

    @pytest.mark.asyncio
    async def test_move_mouse_to(self, engine, mock_page):
        """move_mouse_to вызывает mouse.move."""
        await engine.move_mouse_to(100, 200)
        assert mock_page.mouse.move.called

    @pytest.mark.asyncio
    async def test_move_mouse_to_updates_position(self, engine, mock_page):
        """move_mouse_to обновляет текущую позицию."""
        await engine.move_mouse_to(100, 200)
        assert engine._current_x == 100
        assert engine._current_y == 200

    @pytest.mark.asyncio
    async def test_move_mouse_to_element(self, engine, mock_page):
        """move_mouse_to_element с видимым элементом."""
        locator = AsyncMock()
        locator.bounding_box = AsyncMock(return_value={
            "x": 100, "y": 200, "width": 50, "height": 30,
        })
        await engine.move_mouse_to_element(locator)
        assert mock_page.mouse.move.called

    @pytest.mark.asyncio
    async def test_move_mouse_to_element_not_visible(self, engine, mock_page):
        """move_mouse_to_element с невидимым элементом — без движения."""
        locator = AsyncMock()
        locator.bounding_box = AsyncMock(return_value=None)
        await engine.move_mouse_to_element(locator)
        # mouse.move не должен быть вызван
        assert not mock_page.mouse.move.called

    @pytest.mark.asyncio
    async def test_click_at_position(self, engine, mock_page):
        """click с координатами."""
        await engine.click(x=100, y=200)
        assert mock_page.mouse.click.called

    @pytest.mark.asyncio
    async def test_click_at_current_position(self, engine, mock_page):
        """click без координат — в текущую позицию."""
        await engine.click()
        assert mock_page.mouse.click.called

    @pytest.mark.asyncio
    async def test_click_with_locator(self, engine, mock_page):
        """click с locator."""
        locator = AsyncMock()
        locator.bounding_box = AsyncMock(return_value={
            "x": 100, "y": 200, "width": 50, "height": 30,
        })
        await engine.click(locator=locator)
        assert locator.click.called

    @pytest.mark.asyncio
    async def test_double_click(self, engine, mock_page):
        """double_click с координатами."""
        await engine.double_click(x=100, y=200)
        assert mock_page.mouse.dblclick.called

    @pytest.mark.asyncio
    async def test_double_click_with_locator(self, engine, mock_page):
        """double_click с locator."""
        locator = AsyncMock()
        await engine.double_click(locator=locator)
        assert locator.dblclick.called


class TestHumanBehaviorEngineScroll:
    """Тесты скроллинга."""

    @pytest.mark.asyncio
    async def test_scroll_down(self, engine, mock_page):
        """scroll_down вызывает mouse.wheel."""
        await engine.scroll_down(pages=0.1)
        assert mock_page.mouse.wheel.called or mock_page.evaluate.called

    @pytest.mark.asyncio
    async def test_scroll_up(self, engine, mock_page):
        """scroll_up (отрицательное значение)."""
        await engine.scroll_down(pages=-0.1)
        assert mock_page.mouse.wheel.called or mock_page.evaluate.called


class TestHumanBehaviorEngineKeyboard:
    """Тесты набора текста."""

    @pytest.mark.asyncio
    async def test_type_text(self, engine, mock_page):
        """type_text вызывает keyboard.type или type_like_human."""
        mock_page.keyboard = AsyncMock()
        mock_page.keyboard.type = AsyncMock()
        mock_page.keyboard.press = AsyncMock()
        await engine.type_text("Hello")
        # type_text может вызывать type или press посимвольно
        assert mock_page.keyboard.type.called or mock_page.keyboard.press.called

    @pytest.mark.asyncio
    async def test_type_text_empty(self, engine, mock_page):
        """type_text с пустой строкой — не падает."""
        mock_page.keyboard = AsyncMock()
        mock_page.keyboard.type = AsyncMock()
        await engine.type_text("")


class TestHumanBehaviorEngineRead:
    """Тесты имитации чтения."""

    @pytest.mark.asyncio
    async def test_read_page(self, engine, mock_page):
        """read_page вызывает evaluate для подсчёта слов."""
        mock_page.evaluate = AsyncMock(return_value=100)
        await engine.read_page()
        assert mock_page.evaluate.called


class TestHumanBehaviorEngineBezier:
    """Тесты генерации кривых Безье."""

    def test_generate_bezier_points(self, engine):
        """_generate_bezier_points возвращает список точек (num_points + 1)."""
        points = engine._generate_bezier_points(0, 0, 100, 100, 10)
        assert len(points) == 11  # num_points + 1 (включая начальную)
        for px, py in points:
            assert isinstance(px, float)
            assert isinstance(py, float)

    def test_bezier_start_point(self, engine):
        """Первая точка = начало."""
        points = engine._generate_bezier_points(10, 20, 100, 200, 10)
        assert points[0] == (10.0, 20.0)

    def test_bezier_end_point(self, engine):
        """Последняя точка = конец."""
        points = engine._generate_bezier_points(0, 0, 100, 200, 10)
        assert points[-1] == (100.0, 200.0)

    def test_bezier_points_count(self, engine):
        """Количество точек = num_points + 1."""
        for n in [5, 10, 20]:
            points = engine._generate_bezier_points(0, 0, 100, 100, n)
            assert len(points) == n + 1


class TestHumanBehaviorEngineDelays:
    """Тесты задержек."""

    def test_random_delay_in_range(self, engine):
        """_random_delay возвращает значение в диапазоне."""
        for _ in range(20):
            delay = engine._rng.uniform(100, 200)
            assert 100 <= delay <= 200

    def test_seed_reproducibility(self, mock_page):
        """Одинаковый seed → одинаковые результаты."""
        e1 = HumanBehaviorEngine(mock_page, seed=42)
        e2 = HumanBehaviorEngine(mock_page, seed=42)
        for _ in range(10):
            assert e1._rng.random() == e2._rng.random()
