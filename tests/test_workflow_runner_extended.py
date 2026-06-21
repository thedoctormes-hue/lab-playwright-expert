"""
Расширенные тесты для WorkflowRunner.

Покрывает:
  - WorkItem dataclass
  - WorkflowResult (summary property)
  - WorkflowRunner.__init__
  - WorkflowRunner.register_task_type
  - WorkflowRunner.add_work (valid/invalid)
  - WorkflowRunner.run (empty, with mocked tasks)
  - WorkflowRunner.stats
  - WorkflowRunner._make_handler
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lab_playwright_kit.task_orchestrator import TaskPriority
from lab_playwright_kit.workflow_runner import (
    WorkflowResult,
    WorkflowRunner,
    WorkItem,
)


# ─── WorkItem ──────────────────────────────────────────────────────────────


class TestWorkItem:
    def test_defaults(self):
        item = WorkItem(task_type="crosspost")
        assert item.task_type == "crosspost"
        assert item.params == {}
        assert item.priority == TaskPriority.NORMAL
        assert item.platform == ""

    def test_all_fields(self):
        item = WorkItem(
            task_type="social",
            params={"action": "like", "target": "https://t.me/test"},
            priority=TaskPriority.HIGH,
            platform="telegram",
        )
        assert item.task_type == "social"
        assert item.params["action"] == "like"
        assert item.priority == TaskPriority.HIGH
        assert item.platform == "telegram"


# ─── WorkflowResult ────────────────────────────────────────────────────────


class TestWorkflowResult:
    def test_defaults(self):
        result = WorkflowResult(work_item=WorkItem(task_type="test"))
        assert result.success is False
        assert result.error == ""
        assert result.elapsed_seconds == 0.0
        assert result.task_contexts == []

    def test_summary_success(self):
        item = WorkItem(task_type="crosspost")
        result = WorkflowResult(work_item=item, success=True, elapsed_seconds=3.5)
        assert result.summary == "✓ crosspost (3.50s)"

    def test_summary_failure(self):
        item = WorkItem(task_type="crosspost")
        result = WorkflowResult(work_item=item, success=False, error="Timeout")
        assert result.summary == "✗ crosspost: Timeout"

    def test_summary_zero_time(self):
        item = WorkItem(task_type="test")
        result = WorkflowResult(work_item=item, success=True, elapsed_seconds=0)
        assert result.summary == "✓ test (0.00s)"


# ─── WorkflowRunner init ───────────────────────────────────────────────────


class TestWorkflowRunnerInit:
    def test_default_init(self):
        bm = MagicMock()
        runner = WorkflowRunner(bm)
        assert runner._browser_mgr is bm
        assert runner._task_types == {}
        assert runner._pending_work == []
        assert runner._results == []

    def test_custom_workers(self):
        bm = MagicMock()
        runner = WorkflowRunner(bm, workers=5)
        assert runner._orchestrator._workers == 5


# ─── register_task_type ────────────────────────────────────────────────────


class TestRegisterTaskType:
    def test_register(self):
        bm = MagicMock()
        runner = WorkflowRunner(bm)

        class FakeTask:
            pass

        runner.register_task_type("crosspost", FakeTask)
        assert "crosspost" in runner._task_types
        assert runner._task_types["crosspost"] is FakeTask

    def test_register_multiple(self):
        bm = MagicMock()
        runner = WorkflowRunner(bm)

        class TaskA:
            pass

        class TaskB:
            pass

        runner.register_task_type("a", TaskA)
        runner.register_task_type("b", TaskB)
        assert len(runner._task_types) == 2

    def test_register_overwrite(self):
        bm = MagicMock()
        runner = WorkflowRunner(bm)

        class TaskV1:
            pass

        class TaskV2:
            pass

        runner.register_task_type("x", TaskV1)
        runner.register_task_type("x", TaskV2)
        assert runner._task_types["x"] is TaskV2


# ─── add_work ──────────────────────────────────────────────────────────────


class TestAddWork:
    def test_add_valid_work(self):
        bm = MagicMock()
        runner = WorkflowRunner(bm)

        class FakeTask:
            pass

        runner.register_task_type("crosspost", FakeTask)
        runner.add_work("crosspost", title="Hello", content="World")
        assert len(runner._pending_work) == 1
        assert runner._pending_work[0].task_type == "crosspost"
        assert runner._pending_work[0].params["title"] == "Hello"

    def test_add_work_unknown_type(self):
        bm = MagicMock()
        runner = WorkflowRunner(bm)
        with pytest.raises(ValueError, match="Unknown task type"):
            runner.add_work("unknown", title="Hi")

    def test_add_work_with_priority(self):
        bm = MagicMock()
        runner = WorkflowRunner(bm)

        class FakeTask:
            pass

        runner.register_task_type("social", FakeTask)
        runner.add_work("social", priority=TaskPriority.HIGH, action="like")
        assert runner._pending_work[0].priority == TaskPriority.HIGH

    def test_add_work_with_platform(self):
        bm = MagicMock()
        runner = WorkflowRunner(bm)

        class FakeTask:
            pass

        runner.register_task_type("social", FakeTask)
        runner.add_work("social", platform="telegram", action="post")
        assert runner._pending_work[0].platform == "telegram"

    def test_add_multiple_work(self):
        bm = MagicMock()
        runner = WorkflowRunner(bm)

        class FakeTask:
            pass

        runner.register_task_type("crosspost", FakeTask)
        runner.add_work("crosspost", title="A")
        runner.add_work("crosspost", title="B")
        runner.add_work("crosspost", title="C")
        assert len(runner._pending_work) == 3


# ─── stats ─────────────────────────────────────────────────────────────────


class TestStats:
    def test_empty_stats(self):
        bm = MagicMock()
        runner = WorkflowRunner(bm)
        stats = runner.stats
        assert stats["pending"] == 0
        assert stats["completed"] == 0
        assert stats["success"] == 0
        assert stats["failed"] == 0
        assert stats["registered_types"] == []

    def test_stats_after_register(self):
        bm = MagicMock()
        runner = WorkflowRunner(bm)

        class FakeTask:
            pass

        runner.register_task_type("crosspost", FakeTask)
        runner.add_work("crosspost", title="Hi")
        stats = runner.stats
        assert stats["pending"] == 1
        assert "crosspost" in stats["registered_types"]


# ─── run (empty) ───────────────────────────────────────────────────────────


class TestRun:
    @pytest.mark.asyncio
    async def test_run_empty(self):
        bm = MagicMock()
        runner = WorkflowRunner(bm)
        results = await runner.run()
        assert results == []


# ─── _make_handler ────────────────────────────────────────────────────────


class TestMakeHandler:
    def test_make_handler_returns_coroutine(self):
        bm = MagicMock()
        runner = WorkflowRunner(bm)

        class FakeTask:
            pass

        work = WorkItem(task_type="test", params={"key": "value"})
        handler = runner._make_handler(FakeTask, work)
        assert callable(handler)
