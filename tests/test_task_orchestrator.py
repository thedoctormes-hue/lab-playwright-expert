"""
Тесты для TaskOrchestrator, Task, TaskPriority, TaskStatus, RateLimit.

Покрывает:
  - TaskPriority / TaskStatus / RateLimit: enum значения и логика
  - Task: создание, сравнение для heapq
  - TaskOrchestrator: добавление, выполнение, ретраи, rate limiting
"""
import asyncio
import time

import pytest

from lab_playwright_kit.task_orchestrator import (
    DEFAULT_RATE_LIMITS,
    RateLimit,
    Task,
    TaskOrchestrator,
    TaskPriority,
    TaskStatus,
)


# ─── TaskPriority ────────────────────────────────────────────────────────────

class TestTaskPriority:
    """Тесты enum TaskPriority."""

    def test_ordering(self):
        assert TaskPriority.CRITICAL < TaskPriority.HIGH < TaskPriority.NORMAL < TaskPriority.LOW < TaskPriority.BACKGROUND

    def test_values(self):
        assert TaskPriority.CRITICAL == 0
        assert TaskPriority.HIGH == 1
        assert TaskPriority.NORMAL == 2
        assert TaskPriority.LOW == 3
        assert TaskPriority.BACKGROUND == 4


# ─── TaskStatus ──────────────────────────────────────────────────────────────

class TestTaskStatus:
    """Тесты enum TaskStatus."""

    def test_all_statuses(self):
        expected = {"pending", "running", "success", "completed", "failed", "retry", "cancelled", "paused", "retrying"}
        actual = {s.value for s in TaskStatus}
        assert actual == expected


# ─── RateLimit ───────────────────────────────────────────────────────────────

class TestRateLimit:
    """Тесты dataclass RateLimit."""

    def test_defaults(self):
        rl = RateLimit()
        assert rl.platform == ""
        assert rl.max_per_minute == 30
        assert rl.max_per_hour == 500
        assert rl.max_per_day == 5000
        assert rl.cooldown_seconds == 2.0

    def test_custom(self):
        rl = RateLimit(platform="twitter", max_per_minute=10, max_per_hour=100, max_per_day=1000)
        assert rl.platform == "twitter"
        assert rl.max_per_minute == 10

    def test_can_execute_empty(self):
        """Пустой rate limit — можно выполнять."""
        rl = RateLimit()
        assert rl.can_execute() is True

    def test_can_execute_after_record(self):
        """После записи — можно (если под лимитом и cooldown прошёл)."""
        rl = RateLimit(max_per_minute=10, cooldown_seconds=0)
        rl.record_action()
        assert rl.can_execute() is True

    def test_can_execute_minute_exceeded(self):
        """Превышен per_minute — False."""
        rl = RateLimit(max_per_minute=2, cooldown_seconds=0)
        rl.record_action()
        rl.record_action()
        assert rl.can_execute() is False

    def test_can_execute_cooldown(self):
        """Cooldown не прошёл — False."""
        rl = RateLimit(max_per_minute=10, cooldown_seconds=5.0)
        rl.record_action()
        assert rl.can_execute() is False

    def test_record_action(self):
        """record_action добавляет timestamp."""
        rl = RateLimit()
        assert len(rl._actions_minute) == 0
        rl.record_action()
        assert len(rl._actions_minute) == 1
        assert len(rl._actions_hour) == 1
        assert len(rl._actions_day) == 1
        assert rl._last_action > 0

    def test_wait_time_zero(self):
        """wait_time = 0 если лимит не превышен."""
        rl = RateLimit()
        assert rl.wait_time == 0

    def test_wait_time_positive_when_exceeded(self):
        """wait_time > 0 при превышении minute лимита."""
        rl = RateLimit(max_per_minute=1, cooldown_seconds=0)
        rl.record_action()
        # После record_action cooldown=0, но minute превышен
        assert rl.wait_time > 0

    def test_default_rate_limits_populated(self):
        """DEFAULT_RATE_LIMITS содержит основные платформы."""
        assert "twitter" in DEFAULT_RATE_LIMITS
        assert "instagram" in DEFAULT_RATE_LIMITS
        assert "telegram" in DEFAULT_RATE_LIMITS
        assert "habr" in DEFAULT_RATE_LIMITS
        assert "vcru" in DEFAULT_RATE_LIMITS

    def test_default_rate_limits_count(self):
        """Не менее 15 платформ в DEFAULT_RATE_LIMITS."""
        assert len(DEFAULT_RATE_LIMITS) >= 15


# ─── Task ────────────────────────────────────────────────────────────────────

class TestTask:
    """Тесты dataclass Task."""

    def test_default_creation(self):
        task = Task()
        assert task.id == ""
        assert task.platform == ""
        assert task.action == ""
        assert task.status == TaskStatus.PENDING
        assert task.priority == TaskPriority.NORMAL
        assert task.max_retries == 3
        assert task.retry_count == 0
        assert task.retry_delay_seconds == 5.0
        assert task.created_at > 0
        assert task.started_at == 0
        assert task.completed_at == 0
        assert task.error == ""
        assert task.result == {}

    def test_custom_creation(self):
        task = Task(
            id="t_001", platform="twitter", action="like",
            target="https://t.co/abc", priority=TaskPriority.HIGH,
            max_retries=5, account_id=42,
        )
        assert task.id == "t_001"
        assert task.platform == "twitter"
        assert task.action == "like"
        assert task.priority == TaskPriority.HIGH
        assert task.max_retries == 5
        assert task.account_id == 42

    def test_heapq_ordering(self):
        """Task сравнивается по priority для heapq."""
        t1 = Task(priority=TaskPriority.LOW)
        t2 = Task(priority=TaskPriority.HIGH)
        t3 = Task(priority=TaskPriority.CRITICAL)
        assert t3 < t2 < t1

    def test_heapq_same_priority(self):
        """Задачи с одинаковым priority — не падают."""
        t1 = Task(priority=TaskPriority.NORMAL)
        t2 = Task(priority=TaskPriority.NORMAL)
        tasks = [t1, t2]
        import heapq
        heapq.heapify(tasks)
        assert len(tasks) == 2

    def test_params_dict(self):
        task = Task(params={"key": "value", "num": 42})
        assert task.params == {"key": "value", "num": 42}

    def test_result_dict(self):
        task = Task(result={"status": "ok"})
        assert task.result == {"status": "ok"}


# ─── TaskOrchestrator ───────────────────────────────────────────────────────

@pytest.fixture
def orchestrator():
    """TaskOrchestrator с 2 воркерами."""
    return TaskOrchestrator(workers=2)


class TestTaskOrchestratorInit:
    """Тесты инициализации."""

    def test_default_init(self):
        orch = TaskOrchestrator()
        assert orch._workers == 3
        assert orch._queue == []
        assert orch._results == []
        assert orch._running is False

    def test_custom_workers(self):
        orch = TaskOrchestrator(workers=5)
        assert orch._workers == 5

    def test_default_rate_limits_loaded(self):
        orch = TaskOrchestrator()
        assert "twitter" in orch._rate_limits
        assert "instagram" in orch._rate_limits

    def test_custom_rate_limits(self):
        custom = {"my_platform": RateLimit("my_platform", max_per_minute=5)}
        orch = TaskOrchestrator(rate_limits=custom)
        assert "my_platform" in orch._rate_limits
        assert "twitter" not in orch._rate_limits

    def test_handlers_empty(self):
        orch = TaskOrchestrator()
        assert orch._handlers == {}


class TestTaskOrchestratorRateLimit:
    """Тесты rate limiting через orchestrator."""

    def test_set_rate_limit(self, orchestrator):
        rl = RateLimit(platform="custom", max_per_minute=5)
        orchestrator.set_rate_limit("custom", rl)
        assert "custom" in orchestrator._rate_limits
        assert orchestrator._rate_limits["custom"].max_per_minute == 5


class TestTaskOrchestratorAddTask:
    """Тесты добавления задач."""

    def test_add_task(self, orchestrator):
        task = Task(id="t_001", platform="twitter", action="like")
        orchestrator.add_task(task)
        assert len(orchestrator._queue) == 1

    def test_add_task_priority_ordering(self, orchestrator):
        """Задачи добавляются с учётом приоритета."""
        t1 = Task(id="low", priority=TaskPriority.LOW)
        t2 = Task(id="high", priority=TaskPriority.HIGH)
        t3 = Task(id="critical", priority=TaskPriority.CRITICAL)
        orchestrator.add_task(t1)
        orchestrator.add_task(t2)
        orchestrator.add_task(t3)
        import heapq
        first = heapq.heappop(orchestrator._queue)
        assert first.id == "critical"

    def test_add_tasks_bulk(self, orchestrator):
        tasks = [Task(id=f"bulk_{i}", platform="twitter", action="like") for i in range(10)]
        orchestrator.add_tasks(tasks)
        assert len(orchestrator._queue) == 10


class TestTaskOrchestratorRegisterHandler:
    """Тесты регистрации обработчиков."""

    def test_register_handler(self, orchestrator):
        async def handler(task):
            return {"ok": True}
        orchestrator.register_handler("like", handler)
        assert "like" in orchestrator._handlers

    def test_register_handlers(self, orchestrator):
        async def like_handler(task):
            return {}
        async def follow_handler(task):
            return {}
        orchestrator.register_handlers({"like": like_handler, "follow": follow_handler})
        assert len(orchestrator._handlers) == 2


class TestTaskOrchestratorProperties:
    """Тесты свойств."""

    def test_queue_size_empty(self, orchestrator):
        assert orchestrator.queue_size == 0

    def test_queue_size_with_tasks(self, orchestrator):
        orchestrator.add_task(Task(id="t_001"))
        assert orchestrator.queue_size == 1

    def test_results_empty(self, orchestrator):
        assert orchestrator.results == []

    def test_stats(self, orchestrator):
        stats = orchestrator.stats
        assert "queue_size" in stats
        assert "processed" in stats
        assert "success" in stats
        assert "failed" in stats
        assert "workers" in stats
        assert stats["workers"] == 2
        assert stats["running"] is False


class TestTaskOrchestratorRun:
    """Тесты выполнения задач."""

    @pytest.mark.asyncio
    async def test_run_empty(self, orchestrator):
        """Пустой оркестратор."""
        results = await orchestrator.run()
        assert results == []

    @pytest.mark.asyncio
    async def test_run_single_task(self, orchestrator):
        """Одна задача с обработчиком."""
        async def handler(task):
            return {"status": "ok"}
        orchestrator.register_handler("like", handler)
        orchestrator.add_task(Task(id="t_001", platform="twitter", action="like", target="https://t.co/abc"))
        results = await orchestrator.run()
        assert len(results) == 1
        assert results[0].status == TaskStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_run_multiple_tasks(self, orchestrator):
        """Несколько задач."""
        async def handler(task):
            return {"status": "ok"}
        orchestrator.register_handler("like", handler)
        for i in range(5):
            orchestrator.add_task(Task(id=f"t_{i:03d}", platform="twitter", action="like"))
        results = await orchestrator.run()
        assert len(results) == 5
        assert all(r.status == TaskStatus.SUCCESS for r in results)

    @pytest.mark.asyncio
    async def test_run_priority_order(self, orchestrator):
        """Критическая задача выполняется первой."""
        execution_order = []

        async def handler(task):
            execution_order.append(task.id)
            return {"status": "ok"}

        orchestrator.register_handler("like", handler)
        orchestrator.add_task(Task(id="low", platform="twitter", action="like", priority=TaskPriority.LOW))
        orchestrator.add_task(Task(id="critical", platform="twitter", action="like", priority=TaskPriority.CRITICAL))
        orchestrator.add_task(Task(id="high", platform="twitter", action="like", priority=TaskPriority.HIGH))
        await orchestrator.run()
        assert execution_order[0] == "critical"

    @pytest.mark.asyncio
    async def test_run_no_handler_fails(self, orchestrator):
        """Задача без обработчика — FAILED."""
        orchestrator.add_task(Task(id="no_handler", platform="twitter", action="unknown"))
        results = await orchestrator.run()
        assert results[0].status == TaskStatus.FAILED
        assert "No handler" in results[0].error

    @pytest.mark.asyncio
    async def test_run_with_failure(self, orchestrator):
        """Задача с ошибкой — FAILED."""
        async def handler(task):
            raise RuntimeError("test error")
        orchestrator.register_handler("like", handler)
        orchestrator.add_task(Task(id="fail_001", platform="twitter", action="like", max_retries=0))
        results = await orchestrator.run()
        assert results[0].status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_run_with_retry(self, orchestrator):
        """Retry при ошибке — успех со второй попытки."""
        call_count = 0

        async def handler(task):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("first attempt fails")
            return {"status": "ok"}

        orchestrator.register_handler("like", handler)
        orchestrator.add_task(Task(
            id="retry_001", platform="twitter", action="like",
            max_retries=2, retry_delay_seconds=0.01,
        ))
        results = await orchestrator.run()
        assert call_count == 2
        assert results[0].status == TaskStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_run_max_retries_exceeded(self, orchestrator):
        """Превышен лимит ретраев — FAILED."""
        async def handler(task):
            raise RuntimeError("always fails")
        orchestrator.register_handler("like", handler)
        orchestrator.add_task(Task(
            id="max_retry_001", platform="twitter", action="like",
            max_retries=2, retry_delay_seconds=0.01,
        ))
        results = await orchestrator.run()
        assert results[0].status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_run_single_task_method(self, orchestrator):
        """run_single выполняет одну задачу."""
        async def handler(task):
            return {"result": "done"}
        orchestrator.register_handler("like", handler)
        task = Task(id="single_001", platform="twitter", action="like")
        result = await orchestrator.run_single(task)
        assert result.status == TaskStatus.SUCCESS
        assert result.result == {"result": "done"}

    @pytest.mark.asyncio
    async def test_stats_after_run(self, orchestrator):
        """Статистика после выполнения."""
        async def handler(task):
            return {"status": "ok"}
        orchestrator.register_handler("like", handler)
        for i in range(3):
            orchestrator.add_task(Task(id=f"st_{i}", platform="twitter", action="like"))
        await orchestrator.run()
        stats = orchestrator.stats
        assert stats["processed"] == 3
        assert stats["success"] == 3
        assert stats["failed"] == 0
        assert stats["success_rate"] == 100.0
