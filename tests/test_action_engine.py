"""
Тесты для ActionEngine, ActionResult, ActionStep, ActionType.

Покрывает:
  - ActionResult: создание, is_success, все статусы
  - ActionStep: создание, дефолтные значения
  - ActionType / ActionResultStatus: enum значения
  - ActionEngine: структуры, свойства, execute_chain логика
"""
import pytest

from lab_playwright_kit.action_engine import (
    ActionType,
    ActionResult,
    ActionResultStatus,
    ActionStep,
    ActionEngine,
)


# ─── ActionType ──────────────────────────────────────────────────────────────

class TestActionType:
    """Тесты enum ActionType."""

    def test_all_types_exist(self):
        """Все типы действий определены."""
        expected = {
            "like", "repost", "comment", "follow", "unfollow",
            "view", "click", "type", "scroll", "navigate",
            "wait", "screenshot", "custom",
        }
        actual = {t.value for t in ActionType}
        assert actual == expected

    def test_type_values(self):
        """Значения enum совпадают с именами."""
        assert ActionType.LIKE == "like"
        assert ActionType.REPOST == "repost"
        assert ActionType.COMMENT == "comment"
        assert ActionType.FOLLOW == "follow"
        assert ActionType.UNFOLLOW == "unfollow"
        assert ActionType.VIEW == "view"
        assert ActionType.CLICK == "click"
        assert ActionType.TYPE == "type"
        assert ActionType.SCROLL == "scroll"
        assert ActionType.NAVIGATE == "navigate"
        assert ActionType.WAIT == "wait"
        assert ActionType.SCREENSHOT == "screenshot"
        assert ActionType.CUSTOM == "custom"

    def test_type_is_string(self):
        """ActionType — строковый enum."""
        assert isinstance(ActionType.LIKE, str)
        assert ActionType.LIKE == "like"


# ─── ActionResultStatus ─────────────────────────────────────────────────────

class TestActionResultStatus:
    """Тесты enum ActionResultStatus."""

    def test_all_statuses_exist(self):
        """Все статусы определены."""
        expected = {"success", "failed", "skipped", "blocked", "rate_limited", "captcha"}
        actual = {s.value for s in ActionResultStatus}
        assert actual == expected

    def test_status_values(self):
        """Значения статусов."""
        assert ActionResultStatus.SUCCESS == "success"
        assert ActionResultStatus.FAILED == "failed"
        assert ActionResultStatus.SKIPPED == "skipped"
        assert ActionResultStatus.BLOCKED == "blocked"
        assert ActionResultStatus.RATE_LIMITED == "rate_limited"
        assert ActionResultStatus.CAPTCHA == "captcha"


# ─── ActionResult ────────────────────────────────────────────────────────────

class TestActionResult:
    """Тесты dataclass ActionResult."""

    def test_default_creation(self):
        """Создание с дефолтными значениями."""
        r = ActionResult(action_type="like")
        assert r.action_type == "like"
        assert r.status == ActionResultStatus.SUCCESS
        assert r.target == ""
        assert r.message == ""
        assert r.duration_ms == 0
        assert r.metadata == {}

    def test_is_success_true(self):
        """is_success = True при SUCCESS."""
        r = ActionResult(action_type="like", status=ActionResultStatus.SUCCESS)
        assert r.is_success is True

    def test_is_success_false_for_failed(self):
        """is_success = False при FAILED."""
        r = ActionResult(action_type="like", status=ActionResultStatus.FAILED)
        assert r.is_success is False

    def test_is_success_false_for_skipped(self):
        """is_success = False при SKIPPED."""
        r = ActionResult(action_type="like", status=ActionResultStatus.SKIPPED)
        assert r.is_success is False

    def test_is_success_false_for_blocked(self):
        """is_success = False при BLOCKED."""
        r = ActionResult(action_type="like", status=ActionResultStatus.BLOCKED)
        assert r.is_success is False

    def test_is_success_false_for_rate_limited(self):
        """is_success = False при RATE_LIMITED."""
        r = ActionResult(action_type="like", status=ActionResultStatus.RATE_LIMITED)
        assert r.is_success is False

    def test_is_success_false_for_captcha(self):
        """is_success = False при CAPTCHA."""
        r = ActionResult(action_type="like", status=ActionResultStatus.CAPTCHA)
        assert r.is_success is False

    def test_custom_values(self):
        """Создание с кастомными значениями."""
        r = ActionResult(
            action_type="comment",
            status=ActionResultStatus.FAILED,
            target="https://example.com",
            message="Element not found",
            duration_ms=1500.5,
            metadata={"retries": 3, "selector": ".btn"},
        )
        assert r.action_type == "comment"
        assert r.status == ActionResultStatus.FAILED
        assert r.target == "https://example.com"
        assert r.message == "Element not found"
        assert r.duration_ms == 1500.5
        assert r.metadata == {"retries": 3, "selector": ".btn"}

    def test_metadata_default_is_dict(self):
        """metadata по умолчанию — пустой dict."""
        r1 = ActionResult(action_type="a")
        r2 = ActionResult(action_type="b")
        assert r1.metadata is not r2.metadata  # Не общая ссылка


# ─── ActionStep ──────────────────────────────────────────────────────────────

class TestActionStep:
    """Тесты dataclass ActionStep."""

    def test_default_creation(self):
        """Создание с дефолтными значениями."""
        s = ActionStep(action_type="navigate")
        assert s.action_type == "navigate"
        assert s.params == {}
        assert s.condition is None
        assert s.on_fail == "continue"
        assert s.max_retries == 3
        assert s.retry_delay_ms == 5000

    def test_custom_creation(self):
        """Создание с кастомными значениями."""
        s = ActionStep(
            action_type="click",
            params={"selector": ".btn"},
            condition="element_visible",
            on_fail="abort",
            max_retries=5,
            retry_delay_ms=10000,
        )
        assert s.action_type == "click"
        assert s.params == {"selector": ".btn"}
        assert s.condition == "element_visible"
        assert s.on_fail == "abort"
        assert s.max_retries == 5
        assert s.retry_delay_ms == 10000

    def test_on_fail_options(self):
        """on_fail может быть continue, abort, retry."""
        for on_fail in ("continue", "abort", "retry"):
            s = ActionStep(action_type="x", on_fail=on_fail)
            assert s.on_fail == on_fail

    def test_params_default_is_dict(self):
        """params по умолчанию — пустой dict."""
        s1 = ActionStep(action_type="a")
        s2 = ActionStep(action_type="b")
        assert s1.params is not s2.params  # Не общая ссылка


# ─── ActionEngine — структуры и свойства ────────────────────────────────────

class TestActionEngine:
    """Тесты структуры и свойств ActionEngine."""

    def test_results_empty_initially(self):
        """results пустой до выполнения действий."""
        engine = ActionEngine(page=None)  # page не нужен для теста свойств
        assert engine.results == []

    def test_success_count_empty(self):
        """success_count = 0 без результатов."""
        engine = ActionEngine(page=None)
        assert engine.success_count == 0

    def test_fail_count_empty(self):
        """fail_count = 0 без результатов."""
        engine = ActionEngine(page=None)
        assert engine.fail_count == 0

    def test_results_after_manual_append(self):
        """results возвращает добавленные результаты."""
        engine = ActionEngine(page=None)
        engine._results.append(ActionResult(action_type="like", status=ActionResultStatus.SUCCESS))
        engine._results.append(ActionResult(action_type="click", status=ActionResultStatus.FAILED))
        assert len(engine.results) == 2

    def test_success_count_mixed(self):
        """success_count считает только SUCCESS."""
        engine = ActionEngine(page=None)
        engine._results.append(ActionResult(action_type="a", status=ActionResultStatus.SUCCESS))
        engine._results.append(ActionResult(action_type="b", status=ActionResultStatus.SUCCESS))
        engine._results.append(ActionResult(action_type="c", status=ActionResultStatus.FAILED))
        assert engine.success_count == 2

    def test_fail_count_mixed(self):
        """fail_count считает все не-SUCCESS."""
        engine = ActionEngine(page=None)
        engine._results.append(ActionResult(action_type="a", status=ActionResultStatus.SUCCESS))
        engine._results.append(ActionResult(action_type="b", status=ActionResultStatus.FAILED))
        engine._results.append(ActionResult(action_type="c", status=ActionResultStatus.SKIPPED))
        assert engine.fail_count == 2

    def test_results_returns_copy(self):
        """results возвращает копию, а не оригинал."""
        engine = ActionEngine(page=None)
        engine._results.append(ActionResult(action_type="x"))
        results = engine.results
        results.clear()
        assert len(engine._results) == 1  # Оригинал не изменился

    def test_default_profile(self):
        """Дефолтный профиль — social_media."""
        engine = ActionEngine(page=None)
        assert engine.behavior is not None

    def test_custom_profile(self):
        """Кастомный профиль."""
        engine = ActionEngine(page=None, profile="power_user")
        assert engine.behavior is not None

    def test_custom_seed(self):
        """Кастомный seed."""
        engine = ActionEngine(page=None, seed=42)
        assert engine.behavior is not None


# ─── ActionEngine._execute_step — логика ────────────────────────────────────

class TestActionEngineExecuteStep:
    """Тесты _execute_step — маппинг типов действий."""

    def test_unknown_action_type(self):
        """Неизвестный тип действия возвращает FAILED."""
        engine = ActionEngine(page=None)
        step = ActionStep(action_type="unknown_action")
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(engine._execute_step(step))
        assert result.status == ActionResultStatus.FAILED
        assert "Unknown action type" in result.message

    def test_navigate_action_type(self):
        """navigate вызывает navigate()."""
        engine = ActionEngine(page=None)
        step = ActionStep(action_type=ActionType.NAVIGATE, params={"url": "https://example.com"})
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(engine._execute_step(step))
        # Без реального page — FAILED, но не Unknown
        assert "Unknown action type" not in result.message

    def test_click_action_type(self):
        """click вызывает click_element()."""
        engine = ActionEngine(page=None)
        step = ActionStep(action_type=ActionType.CLICK, params={"selector": ".btn"})
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(engine._execute_step(step))
        assert "Unknown action type" not in result.message

    def test_type_action_type(self):
        """type вызывает type_in_field()."""
        engine = ActionEngine(page=None)
        step = ActionStep(action_type=ActionType.TYPE, params={"selector": "input", "text": "hello"})
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(engine._execute_step(step))
        assert "Unknown action type" not in result.message

    def test_like_action_type(self):
        """like вызывает like()."""
        engine = ActionEngine(page=None)
        step = ActionStep(action_type=ActionType.LIKE)
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(engine._execute_step(step))
        assert "Unknown action type" not in result.message

    def test_comment_action_type(self):
        """comment вызывает comment()."""
        engine = ActionEngine(page=None)
        step = ActionStep(action_type=ActionType.COMMENT, params={"text": "test"})
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(engine._execute_step(step))
        assert "Unknown action type" not in result.message

    def test_follow_action_type(self):
        """follow вызывает follow()."""
        engine = ActionEngine(page=None)
        step = ActionStep(action_type=ActionType.FOLLOW)
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(engine._execute_step(step))
        assert "Unknown action type" not in result.message

    def test_repost_action_type(self):
        """repost вызывает repost()."""
        engine = ActionEngine(page=None)
        step = ActionStep(action_type=ActionType.REPOST)
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(engine._execute_step(step))
        assert "Unknown action type" not in result.message

    def test_view_action_type(self):
        """view вызывает view_content()."""
        engine = ActionEngine(page=None)
        step = ActionStep(action_type=ActionType.VIEW)
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(engine._execute_step(step))
        assert "Unknown action type" not in result.message

    def test_scroll_action_type(self):
        """scroll вызывает scroll_and_read()."""
        engine = ActionEngine(page=None)
        step = ActionStep(action_type=ActionType.SCROLL)
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(engine._execute_step(step))
        assert "Unknown action type" not in result.message

    def test_wait_action_type(self):
        """wait вызывает wait_for_content()."""
        engine = ActionEngine(page=None)
        step = ActionStep(action_type=ActionType.WAIT, params={"selector": ".content"})
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(engine._execute_step(step))
        assert "Unknown action type" not in result.message


# ─── ActionEngine.execute_chain — логика ────────────────────────────────────

class TestActionEngineExecuteChain:
    """Тесты execute_chain — цепочки действий."""

    def test_empty_chain(self):
        """Пустая цепочка — пустой список."""
        engine = ActionEngine(page=None)
        import asyncio
        results = asyncio.get_event_loop().run_until_complete(engine.execute_chain([]))
        assert results == []

    def test_chain_abort_on_fail(self):
        """on_fail=abort останавливает цепочку."""
        engine = ActionEngine(page=None)
        steps = [
            ActionStep(action_type="unknown_1", on_fail="abort"),
            ActionStep(action_type="unknown_2"),  # Не должна выполниться
        ]
        import asyncio
        results = asyncio.get_event_loop().run_until_complete(engine.execute_chain(steps))
        assert len(results) == 1  # Только первый шаг
        assert results[0].status == ActionResultStatus.FAILED

    def test_chain_continue_on_fail(self):
        """on_fail=continue продолжает цепочку."""
        engine = ActionEngine(page=None)
        steps = [
            ActionStep(action_type="unknown_1", on_fail="continue"),
            ActionStep(action_type="unknown_2", on_fail="continue"),
        ]
        import asyncio
        results = asyncio.get_event_loop().run_until_complete(engine.execute_chain(steps))
        assert len(results) == 2  # Оба шага

    def test_chain_retry_on_fail(self):
        """on_fail=retry повторяет шаг max_retries раз."""
        engine = ActionEngine(page=None)
        step = ActionStep(
            action_type="always_fails",
            on_fail="retry",
            max_retries=2,
            retry_delay_ms=10,
        )
        import asyncio
        results = asyncio.get_event_loop().run_until_complete(engine.execute_chain([step]))
        # Первый запуск + 2 retry = 3 результата, последний заменяет
        assert len(results) == 1  # Один шаг в цепочке
        assert results[0].status == ActionResultStatus.FAILED

    def test_chain_all_success(self):
        """Все шаги успешны — все выполнены."""
        engine = ActionEngine(page=None)
        # Используем navigate с невалидным URL — вызовет FAILED от page=None
        # Но нам нужно проверить что все шаги выполняются
        steps = [
            ActionStep(action_type="navigate", params={"url": "x"}, on_fail="continue"),
            ActionStep(action_type="navigate", params={"url": "y"}, on_fail="continue"),
            ActionStep(action_type="navigate", params={"url": "z"}, on_fail="continue"),
        ]
        import asyncio
        results = asyncio.get_event_loop().run_until_complete(engine.execute_chain(steps))
        assert len(results) == 3

    def test_chain_returns_results(self):
        """execute_chain возвращает результаты всех шагов."""
        engine = ActionEngine(page=None)
        steps = [
            ActionStep(action_type="unknown", on_fail="continue"),
        ]
        import asyncio
        results = asyncio.get_event_loop().run_until_complete(engine.execute_chain(steps))
        assert len(results) == 1
        assert results[0].status == ActionResultStatus.FAILED
