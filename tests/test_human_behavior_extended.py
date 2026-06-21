"""
Расширенные тесты для HumanBehaviorEngine и BehaviorProfile.

Покрывает:
  - BehaviorProfile dataclass: все поля, значения по умолчанию
  - BEHAVIOR_PROFILES пресеты: casual_reader, power_user, researcher, social_media
  - HumanBehaviorEngine.__init__ — профиль по умолчанию, кастомный профиль, seed
"""

from __future__ import annotations

from lab_playwright_kit.human_behavior import (
    BEHAVIOR_PROFILES,
    BehaviorProfile,
    HumanBehaviorEngine,
)


# ─── BehaviorProfile defaults ────────────────────────────────────────────


class TestBehaviorProfileDefaults:
    def test_default_name(self):
        bp = BehaviorProfile()
        assert bp.name == "casual_reader"

    def test_default_mouse_move(self):
        bp = BehaviorProfile()
        assert bp.mouse_move_min_ms == 200
        assert bp.mouse_move_max_ms == 800

    def test_default_mouse_jitter(self):
        bp = BehaviorProfile()
        assert bp.mouse_jitter_px == 2.0

    def test_default_mouse_bezier_points(self):
        bp = BehaviorProfile()
        assert bp.mouse_bezier_points == 3

    def test_default_click_delay_before(self):
        bp = BehaviorProfile()
        assert bp.click_delay_before_ms == (50, 200)

    def test_default_click_delay_after(self):
        bp = BehaviorProfile()
        assert bp.click_delay_after_ms == (100, 500)

    def test_default_double_click_chance(self):
        bp = BehaviorProfile()
        assert bp.double_click_chance == 0.05

    def test_default_scroll_speed(self):
        bp = BehaviorProfile()
        assert bp.scroll_speed_px == (100, 400)

    def test_default_scroll_interval(self):
        bp = BehaviorProfile()
        assert bp.scroll_interval_ms == (50, 150)

    def test_default_scroll_pause_chance(self):
        bp = BehaviorProfile()
        assert bp.scroll_pause_chance == 0.15

    def test_default_scroll_pause_ms(self):
        bp = BehaviorProfile()
        assert bp.scroll_pause_ms == (500, 3000)

    def test_default_scroll_reverse_chance(self):
        bp = BehaviorProfile()
        assert bp.scroll_reverse_chance == 0.05

    def test_default_reading_speed(self):
        bp = BehaviorProfile()
        assert bp.reading_speed_wpm == (200, 400)

    def test_default_reading_pause_chance(self):
        bp = BehaviorProfile()
        assert bp.reading_pause_chance == 0.3

    def test_default_reading_pause_ms(self):
        bp = BehaviorProfile()
        assert bp.reading_pause_ms == (1000, 5000)

    def test_default_typing_speed(self):
        bp = BehaviorProfile()
        assert bp.typing_speed_wpm == (150, 350)

    def test_default_typing_error_chance(self):
        bp = BehaviorProfile()
        assert bp.typing_error_chance == 0.02

    def test_default_typing_pause_chance(self):
        bp = BehaviorProfile()
        assert bp.typing_pause_chance == 0.1

    def test_default_typing_pause_ms(self):
        bp = BehaviorProfile()
        assert bp.typing_pause_ms == (200, 1500)

    def test_default_action_delay(self):
        bp = BehaviorProfile()
        assert bp.action_delay_ms == (500, 2000)

    def test_default_idle_chance(self):
        bp = BehaviorProfile()
        assert bp.idle_chance == 0.1

    def test_default_idle_ms(self):
        bp = BehaviorProfile()
        assert bp.idle_ms == (2000, 8000)


# ─── BehaviorProfile custom ──────────────────────────────────────────────


class TestBehaviorProfileCustom:
    def test_custom_name(self):
        bp = BehaviorProfile(name="custom_bot")
        assert bp.name == "custom_bot"

    def test_custom_mouse_params(self):
        bp = BehaviorProfile(
            mouse_move_min_ms=50,
            mouse_move_max_ms=200,
            mouse_jitter_px=5.0,
        )
        assert bp.mouse_move_min_ms == 50
        assert bp.mouse_move_max_ms == 200
        assert bp.mouse_jitter_px == 5.0


# ─── BEHAVIOR_PROFILES presets ──────────────────────────────────────────


class TestBehaviorProfilePresets:
    def test_has_casual_reader(self):
        assert "casual_reader" in BEHAVIOR_PROFILES

    def test_has_power_user(self):
        assert "power_user" in BEHAVIOR_PROFILES

    def test_has_researcher(self):
        assert "researcher" in BEHAVIOR_PROFILES

    def test_has_social_media(self):
        assert "social_media" in BEHAVIOR_PROFILES

    def test_casual_reader_is_slower_than_power_user(self):
        casual = BEHAVIOR_PROFILES["casual_reader"]
        power = BEHAVIOR_PROFILES["power_user"]
        assert casual.mouse_move_min_ms > power.mouse_move_min_ms
        assert casual.mouse_move_max_ms > power.mouse_move_max_ms

    def test_power_user_faster_scroll(self):
        power = BEHAVIOR_PROFILES["power_user"]
        casual = BEHAVIOR_PROFILES["casual_reader"]
        assert power.scroll_speed_px[0] > casual.scroll_speed_px[0]

    def test_researcher_slower_reading(self):
        researcher = BEHAVIOR_PROFILES["researcher"]
        casual = BEHAVIOR_PROFILES["casual_reader"]
        assert researcher.reading_speed_wpm[1] < casual.reading_speed_wpm[1]

    def test_all_presets_have_name(self):
        for name, profile in BEHAVIOR_PROFILES.items():
            assert profile.name == name

    def test_all_presets_have_positive_values(self):
        for name, bp in BEHAVIOR_PROFILES.items():
            assert bp.mouse_move_min_ms > 0
            assert bp.mouse_move_max_ms > bp.mouse_move_min_ms
            assert bp.scroll_speed_px[0] > 0
            assert bp.scroll_speed_px[1] > bp.scroll_speed_px[0]
            assert 0 <= bp.scroll_pause_chance <= 1
            assert 0 <= bp.idle_chance <= 1
            assert 0 <= bp.typing_error_chance <= 1


# ─── HumanBehaviorEngine init ───────────────────────────────────────────


class TestHumanBehaviorEngineInit:
    def test_default_profile(self):
        mock_page = object()
        engine = HumanBehaviorEngine(mock_page)
        assert engine.profile.name == "casual_reader"

    def test_string_profile(self):
        mock_page = object()
        engine = HumanBehaviorEngine(mock_page, profile="power_user")
        assert engine.profile.name == "power_user"

    def test_object_profile(self):
        mock_page = object()
        custom_bp = BehaviorProfile(name="custom", mouse_jitter_px=10.0)
        engine = HumanBehaviorEngine(mock_page, profile=custom_bp)
        assert engine.profile.name == "custom"
        assert engine.profile.mouse_jitter_px == 10.0

    def test_invalid_profile_falls_back_to_default(self):
        mock_page = object()
        engine = HumanBehaviorEngine(mock_page, profile="nonexistent")
        assert engine.profile.name == "casual_reader"

    def test_seed_creates_rng(self):
        mock_page = object()
        engine = HumanBehaviorEngine(mock_page, seed=42)
        assert engine._rng is not None

    def test_no_seed_rng_none(self):
        """HumanBehaviorEngine always creates RNG (no None even without seed)."""
        mock_page = object()
        engine = HumanBehaviorEngine(mock_page)
        # Engine creates RNG regardless of seed parameter
        assert engine._rng is not None

    def test_initial_position(self):
        mock_page = object()
        engine = HumanBehaviorEngine(mock_page)
        assert engine._current_x == 0
        assert engine._current_y == 0

    def test_page_stored(self):
        mock_page = object()
        engine = HumanBehaviorEngine(mock_page)
        assert engine.page is mock_page
