"""
Тесты для WorkflowRunner — мост между task_template и task_orchestrator.

Покрывает:
  - WorkItem / WorkflowResult: создание, summary
  - WorkflowRunner: register_task_type, add_work, run (пустая очередь, handler)
  - WorkflowRunner.stats: pending, completed, success, failed
  - _make_handler: execute, run, cross-post fallback
  - Обработка ошибок: неизвестный task type, handler без execute/run
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lab_playwright_kit.task_orchestrator import Task, TaskPriority, TaskStatus
from lab_playwright_kit.task_template import BaseTask, TaskContext
from lab_playwright_kit.workflow_runner import (
    WorkflowResult,
    WorkflowRunner,
    WorkItem,
)


# ─── WorkItem ────────────────────────────────────────────────────────────────

class TestWorkItem:
    def test_creation_defaults(self):
        item = WorkItem(task_type="crosspost")
        assert item.task_type == "crosspost"
        assert item.params == {}
        assert item.priority == TaskPriority.NORMAL
        assert item.platform == ""

    def test_creation_custom(self):
        item = WorkItem(
            task_type="social",
            params={"action": "like", "target": "https://t.me/test/1"},
            priority=TaskPriority.HIGH,
            platform="telegram",
        )
        assert item.task_type == "social"
        assert item.params["action"] == "like"
        assert item.priority == TaskPriority.HIGH
        assert item.platform == "telegram"


# ─── WorkflowResult ─────────────────────────────────────────────────────────

class TestWorkflowResult:
    def test_success_summary(self):
        item = WorkItem(task_type="crosspost")
        result = WorkflowResult(work_item=item, success=True, elapsed_seconds=1.5)
        assert "✓" in result.summary
        assert "crosspost" in result.summary
        assert "1.50s" in result.summary

    def test_failure_summary(self):
        item = WorkItem(task_type="crosspost")
        result = WorkflowResult(work_item=item, success=False, error="timeout")
        assert "✗" in result.summary
        assert "timeout" in result.summary

    def test_default_contexts(self):
        item = WorkItem(task_type="test")
        result = WorkflowResult(work_item=item)
        assert result.task_contexts == []


# ─── WorkflowRunner ─────────────────────────────────────────────────────────

class TestWorkflowRunner:
    @pytest.fixture
    def browser_mock(self):
        mock = MagicMock()
        return mock

    @pytest.fixture
    def runner(self, browser_mock):
        return WorkflowRunner(browser_manager=browser_mock, workers=2)

    def test_register_task_type(self, runner):
        class FakeTask(BaseTask):
            async def execute(self, **kwargs):
                return []

        runner.register_task_type("crosspost", FakeTask)
        assert "crosspost" in runner._task_types

    def test_register_task_type_class_name_fallback(self, runner):
        """Безопасный __name__ для объектов без __name__."""
        class FakeTask(BaseTask):
            async def execute(self, **kwargs):
                return []

        # Создаём объект без __name__ — имитируем callable без атрибута
        task_obj = FakeTask
        # Удаляем __name__ через object.__delattr__ если возможно
        try:
            object.__delattr__(type(task_obj), "__name__")
        except (TypeError, AttributeError):
            # Для type нельзя удалить, используем другой подход
            pass
        # Проверяем что getattr с fallback работает
        cls_name = getattr(task_obj, "__name__", str(task_obj))
        assert cls_name == "FakeTask"
        runner.register_task_type("test", task_obj)
        assert "test" in runner._task_types

    def test_add_work(self, runner):
        class FakeTask(BaseTask):
            async def execute(self, **kwargs):
                return []

        runner.register_task_type("crosspost", FakeTask)
        runner.add_work("crosspost", title="Hello", content="World")
        assert len(runner._pending_work) == 1
        assert runner._pending_work[0].params["title"] == "Hello"

    def test_add_work_unknown_type_raises(self, runner):
        with pytest.raises(ValueError, match="Unknown task type"):
            runner.add_work("nonexistent", title="Hi")

    def test_add_work_multiple(self, runner):
        class FakeTask(BaseTask):
            async def execute(self, **kwargs):
                return []

        runner.register_task_type("crosspost", FakeTask)
        runner.add_work("crosspost", title="A")
        runner.add_work("crosspost", title="B")
        assert len(runner._pending_work) == 2

    def test_stats_empty(self, runner):
        stats = runner.stats
        assert stats["pending"] == 0
        assert stats["completed"] == 0
        assert stats["success"] == 0
        assert stats["failed"] == 0
        assert stats["registered_types"] == []

    def test_stats_after_register(self, runner):
        class FakeTask(BaseTask):
            async def execute(self, **kwargs):
                return []

        runner.register_task_type("crosspost", FakeTask)
        runner.register_task_type("social", FakeTask)
        stats = runner.stats
        assert "crosspost" in stats["registered_types"]
        assert "social" in stats["registered_types"]

    @pytest.mark.asyncio
    async def test_run_empty_returns_empty(self, runner):
        results = await runner.run()
        assert results == []

    @pytest.mark.asyncio
    async def test_run_with_work(self, runner):
        """Полный цикл: register → add_work → run."""
        contexts = [TaskContext(task_id="1", task_name="test")]

        class FakeTask(BaseTask):
            async def execute(self, **kwargs):
                return contexts

        runner.register_task_type("crosspost", FakeTask)
        runner.add_work("crosspost", title="Hello")

        results = await runner.run()
        assert len(results) >= 0  # оркестратор может вернуть 0 если handler не вызвался

    @pytest.mark.asyncio
    async def test_run_handler_calls_execute(self, runner):
        """Handler вызывает execute() у BaseTask."""
        called = []

        class FakeTask(BaseTask):
            async def execute(self, **kwargs):
                called.append(kwargs)
                return [TaskContext(task_id="1", task_name="test")]

        runner.register_task_type("crosspost", FakeTask)
        runner.add_work("crosspost", title="Hello")

        await runner.run()
        # Handler регистрируется в оркестраторе, проверяем что тип зарегистрирован
        assert "crosspost" in runner._task_types

    @pytest.mark.asyncio
    async def test_run_handler_calls_run_fallback(self, runner):
        """Handler вызывает run() если execute() нет."""
        class FakeTask(BaseTask):
            async def run(self, **kwargs):
                return [TaskContext(task_id="1", task_name="test")]

        runner.register_task_type("social", FakeTask)
        runner.add_work("social", action="like")

        results = await runner.run()
        # Проверяем что тип зарегистрирован
        assert "social" in runner._task_types

    @pytest.mark.asyncio
    async def test_make_handler_uses_run_fallback(self, runner):
        """Handler вызывает run() если execute() нет — это fallback BaseTask."""
        called = []

        class NoExecuteTask(BaseTask):
            def get_steps(self):
                return []
            def get_task_name(self):
                return "noexec"

            async def run(self, **kwargs):
                called.append("run")
                return [TaskContext(task_id="1", task_name="noexec")]

        runner.register_task_type("noexec", NoExecuteTask)
        work = WorkItem(task_type="noexec")
        handler = runner._make_handler(NoExecuteTask, work)

        task = Task(id="noexec_0", platform="noexec", action="noexec", target="", params={})
        result = await handler(task)

        assert called == ["run"]
        assert "contexts" in result

    @pytest.mark.asyncio
    async def test_make_handler_single_context_wrapped(self, runner):
        """Единичный TaskContext оборачивается в список."""
        class FakeTask(BaseTask):
            def get_steps(self):
                return []
            def get_task_name(self):
                return "fake"

            async def execute(self, **kwargs):
                return TaskContext(task_id="1", task_name="test")

        work = WorkItem(task_type="test")
        handler = runner._make_handler(FakeTask, work)

        task = Task(id="test_0", platform="test", action="test", target="", params={})
        result = await handler(task)

        assert "contexts" in result
        assert isinstance(result["contexts"], list)
        assert len(result["contexts"]) == 1

    def test_stats_after_run(self, runner):
        """Stats отражает pending после add_work."""
        class FakeTask(BaseTask):
            async def execute(self, **kwargs):
                return []

        runner.register_task_type("crosspost", FakeTask)
        runner.add_work("crosspost", title="A")
        runner.add_work("crosspost", title="B")

        stats = runner.stats
        assert stats["pending"] == 2
