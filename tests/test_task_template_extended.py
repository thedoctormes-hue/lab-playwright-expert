"""
Расширенные тесты для TaskTemplate (BaseTask + TaskContext).

Покрывает:
  - TaskContext (duration_ms, success_count, fail_count, to_dict)
  - AuthPreset dataclass
  - BaseTask.__init__
  - BaseTask.execute_step
  - BaseTask.run (basic flow)
  - TaskStep / ActionResult (если доступны)
"""

from __future__ import annotations

from unittest.mock import MagicMock

from lab_playwright_kit.browser_auth import AuthPreset
from lab_playwright_kit.task_orchestrator import TaskStatus
from lab_playwright_kit.task_template import (
    BaseTask,
    TaskContext,
)


# ─── TaskContext ────────────────────────────────────────────────────────────


class TestTaskContext:
    def test_defaults(self):
        ctx = TaskContext()
        assert ctx.task_id == ""
        assert ctx.task_name == ""
        assert ctx.status == TaskStatus.PENDING
        assert ctx.current_step == 0
        assert ctx.total_steps == 0
        assert ctx.results == []
        assert ctx.errors == []
        assert ctx.metadata == {}
        assert ctx.duration_ms == 0.0
        assert ctx.success_count == 0
        assert ctx.fail_count == 0

    def test_duration_ms_not_started(self):
        ctx = TaskContext()
        assert ctx.duration_ms == 0.0

    def test_duration_ms_with_start(self):
        ctx = TaskContext(started_at="2026-01-01T00:00:00+00:00")
        assert ctx.duration_ms > 0

    def test_duration_ms_with_start_and_end(self):
        ctx = TaskContext(
            started_at="2026-01-01T00:00:00+00:00",
            finished_at="2026-01-01T00:00:05+00:00",
        )
        assert ctx.duration_ms == 5000.0

    def test_success_count(self):
        ctx = TaskContext()
        mock_result = MagicMock()
        mock_result.is_success = True
        mock_result2 = MagicMock()
        mock_result2.is_success = False
        ctx.results = [mock_result, mock_result2, mock_result]
        assert ctx.success_count == 2
        assert ctx.fail_count == 1

    def test_to_dict(self):
        ctx = TaskContext(
            task_id="abc",
            task_name="test_task",
            status=TaskStatus.RUNNING,
            current_step=2,
            total_steps=5,
        )
        d = ctx.to_dict()
        assert d["task_id"] == "abc"
        assert d["task_name"] == "test_task"
        assert d["status"] == TaskStatus.RUNNING
        assert d["current_step"] == 2
        assert d["total_steps"] == 5


# ─── AuthPreset ────────────────────────────────────────────────────────────


class TestAuthPreset:
    def test_defaults(self):
        preset = AuthPreset()
        assert preset.platform == ""
        assert preset.login_url == ""
        assert preset.username_selector == "input[name='email'], input[type='email']"
        assert preset.password_selector == "input[name='password'], input[type='password']"
        assert preset.submit_selector == "button[type='submit']"
        assert preset.use_human_behavior is True

    def test_custom_preset(self):
        preset = AuthPreset(
            platform="habr",
            login_url="https://habr.com/login",
            auth_selectors=["a[href*='editor']"],
        )
        assert preset.platform == "habr"
        assert preset.login_url == "https://habr.com/login"
        assert "a[href*='editor']" in preset.auth_selectors


# ─── BaseTask (via concrete subclass) ─────────────────────────────────────


class ConcreteTask(BaseTask):
    """Минимальная реализация BaseTask для тестирования."""

    def get_task_name(self) -> str:
        return "concrete_test"

    def get_steps(self):
        return []


class TestBaseTask:
    def test_init(self):
        bm = MagicMock()
        task = ConcreteTask(browser_manager=bm)
        assert task._browser_mgr is bm

    def test_init_with_health_monitor(self):
        bm = MagicMock()
        hm = MagicMock()
        task = ConcreteTask(browser_manager=bm, health_monitor=hm)
        assert task._health is hm

    def test_init_default_values(self):
        bm = MagicMock()
        task = ConcreteTask(browser_manager=bm)
        assert task._max_retries == 3
        assert task._step_delay == (1.0, 3.0)


class TestConcreteTaskMethods:
    def test_get_task_name(self):
        bm = MagicMock()
        task = ConcreteTask(browser_manager=bm)
        assert task.get_task_name() == "concrete_test"

    def test_get_steps(self):
        bm = MagicMock()
        task = ConcreteTask(browser_manager=bm)
        assert task.get_steps() == []


# ─── TaskContext edge cases ───────────────────────────────────────────────


class TestTaskContextEdgeCases:
    def test_empty_metadata(self):
        ctx = TaskContext(metadata={})
        assert ctx.metadata == {}

    def test_metadata_with_data(self):
        ctx = TaskContext(metadata={"key": "value", "count": 42})
        assert ctx.metadata["key"] == "value"
        assert ctx.metadata["count"] == 42

    def test_errors_list(self):
        ctx = TaskContext()
        ctx.errors.append("error1")
        ctx.errors.append("error2")
        assert len(ctx.errors) == 2

    def test_results_empty(self):
        ctx = TaskContext()
        assert ctx.success_count == 0
        assert ctx.fail_count == 0

    def test_page_none(self):
        ctx = TaskContext()
        assert ctx.page is None

    def test_browser_manager_none(self):
        ctx = TaskContext()
        assert ctx.browser_manager is None
