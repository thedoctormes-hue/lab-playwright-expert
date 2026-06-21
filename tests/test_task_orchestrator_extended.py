"""
Расширенные тесты для TaskOrchestrator, Task, RateLimit, TaskPriority, TaskStatus.

Покрывает:
  - TaskPriority enum
  - TaskStatus enum
  - Task dataclass: все поля, значения по умолчанию, __lt__
  - RateLimit: can_execute, record_action, wait_time
  - DEFAULT_RATE_LIMITS
  - TaskOrchestrator: __init__, add_task, task queue
"""

from __future__ import annotations

from lab_playwright_kit.task_orchestrator import (
    DEFAULT_RATE_LIMITS,
    RateLimit,
    Task,
    TaskOrchestrator,
    TaskPriority,
    TaskStatus,
)


# ─── TaskPriority enum ───────────────────────────────────────────────────


class TestTaskPriority:
    def test_critical(self):
        assert TaskPriority.CRITICAL == 0

    def test_high(self):
        assert TaskPriority.HIGH == 1

    def test_normal(self):
        assert TaskPriority.NORMAL == 2

    def test_low(self):
        assert TaskPriority.LOW == 3

    def test_background(self):
        assert TaskPriority.BACKGROUND == 4

    def test_ordering(self):
        assert TaskPriority.CRITICAL < TaskPriority.HIGH
        assert TaskPriority.HIGH < TaskPriority.NORMAL
        assert TaskPriority.NORMAL < TaskPriority.LOW
        assert TaskPriority.LOW < TaskPriority.BACKGROUND


# ─── TaskStatus enum ─────────────────────────────────────────────────────


class TestTaskStatus:
    def test_pending(self):
        assert TaskStatus.PENDING.value == "pending"

    def test_running(self):
        assert TaskStatus.RUNNING.value == "running"

    def test_success(self):
        assert TaskStatus.SUCCESS.value == "success"

    def test_completed(self):
        assert TaskStatus.COMPLETED.value == "completed"

    def test_failed(self):
        assert TaskStatus.FAILED.value == "failed"

    def test_retry(self):
        assert TaskStatus.RETRY.value == "retry"

    def test_cancelled(self):
        assert TaskStatus.CANCELLED.value == "cancelled"

    def test_paused(self):
        assert TaskStatus.PAUSED.value == "paused"

    def test_retrying(self):
        assert TaskStatus.RETRYING.value == "retrying"

    def test_str_enum(self):
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.FAILED == "failed"


# ─── Task defaults ───────────────────────────────────────────────────────


class TestTaskDefaults:
    def test_default_id(self):
        t = Task()
        assert t.id == ""

    def test_default_platform(self):
        t = Task()
        assert t.platform == ""

    def test_default_action(self):
        t = Task()
        assert t.action == ""

    def test_default_target(self):
        t = Task()
        assert t.target == ""

    def test_default_params(self):
        t = Task()
        assert t.params == {}

    def test_default_priority(self):
        t = Task()
        assert t.priority == TaskPriority.NORMAL

    def test_default_status(self):
        t = Task()
        assert t.status == TaskStatus.PENDING

    def test_default_account_id(self):
        t = Task()
        assert t.account_id == 0

    def test_default_max_retries(self):
        t = Task()
        assert t.max_retries == 3

    def test_default_retry_count(self):
        t = Task()
        assert t.retry_count == 0

    def test_default_retry_delay(self):
        t = Task()
        assert t.retry_delay_seconds == 5.0

    def test_default_error(self):
        t = Task()
        assert t.error == ""

    def test_default_result(self):
        t = Task()
        assert t.result == {}

    def test_default_started_at(self):
        t = Task()
        assert t.started_at == 0

    def test_default_completed_at(self):
        t = Task()
        assert t.completed_at == 0

    def test_created_at_set(self):
        t = Task()
        assert t.created_at > 0


# ─── Task custom values ──────────────────────────────────────────────────


class TestTaskCustom:
    def test_custom_values(self):
        t = Task(
            id="task_001",
            platform="twitter",
            action="like",
            target="https://twitter.com/post/123",
            params={"user": "test"},
            priority=TaskPriority.HIGH,
            status=TaskStatus.RUNNING,
            account_id=1,
            max_retries=5,
        )
        assert t.id == "task_001"
        assert t.platform == "twitter"
        assert t.action == "like"
        assert t.target == "https://twitter.com/post/123"
        assert t.params == {"user": "test"}
        assert t.priority == TaskPriority.HIGH
        assert t.status == TaskStatus.RUNNING
        assert t.account_id == 1
        assert t.max_retries == 5


# ─── Task.__lt__ (heap ordering) ─────────────────────────────────────────


class TestTaskOrdering:
    def test_lower_priority_less_than(self):
        t_high = Task(priority=TaskPriority.HIGH)
        t_low = Task(priority=TaskPriority.LOW)
        assert t_high < t_low

    def test_same_priority_not_less(self):
        t1 = Task(priority=TaskPriority.NORMAL)
        t2 = Task(priority=TaskPriority.NORMAL)
        assert not (t1 < t2)

    def test_critical_less_than_all(self):
        t_crit = Task(priority=TaskPriority.CRITICAL)
        for p in [
            TaskPriority.HIGH,
            TaskPriority.NORMAL,
            TaskPriority.LOW,
            TaskPriority.BACKGROUND,
        ]:
            assert t_crit < Task(priority=p)


# ─── RateLimit defaults ──────────────────────────────────────────────────


class TestRateLimitDefaults:
    def test_default_platform(self):
        rl = RateLimit()
        assert rl.platform == ""

    def test_default_max_per_minute(self):
        rl = RateLimit()
        assert rl.max_per_minute == 30

    def test_default_max_per_hour(self):
        rl = RateLimit()
        assert rl.max_per_hour == 500

    def test_default_max_per_day(self):
        rl = RateLimit()
        assert rl.max_per_day == 5000

    def test_default_cooldown(self):
        rl = RateLimit()
        assert rl.cooldown_seconds == 2.0


# ─── RateLimit.can_execute ───────────────────────────────────────────────


class TestRateLimitCanExecute:
    def test_empty_can_execute(self):
        rl = RateLimit()
        assert rl.can_execute() is True

    def test_exceeds_minute_limit(self):
        rl = RateLimit(max_per_minute=2)
        rl.record_action()
        rl.record_action()
        assert rl.can_execute() is False

    def test_exceeds_hour_limit(self):
        rl = RateLimit(max_per_hour=1)
        rl.record_action()
        assert rl.can_execute() is False

    def test_exceeds_day_limit(self):
        rl = RateLimit(max_per_day=1)
        rl.record_action()
        assert rl.can_execute() is False

    def test_cooldown_blocks(self):
        rl = RateLimit(cooldown_seconds=10.0)
        rl.record_action()
        assert rl.can_execute() is False


# ─── RateLimit.record_action ─────────────────────────────────────────────


class TestRateLimitRecordAction:
    def test_records_action(self):
        rl = RateLimit()
        rl.record_action()
        assert len(rl._actions_minute) == 1
        assert len(rl._actions_hour) == 1
        assert len(rl._actions_day) == 1

    def test_updates_last_action(self):
        rl = RateLimit()
        rl.record_action()
        assert rl._last_action > 0

    def test_multiple_actions(self):
        rl = RateLimit()
        for _ in range(5):
            rl.record_action()
        assert len(rl._actions_minute) == 5


# ─── RateLimit.wait_time ─────────────────────────────────────────────────


class TestRateLimitWaitTime:
    def test_no_wait_when_empty(self):
        rl = RateLimit()
        assert rl.wait_time == 0

    def test_wait_when_minute_exceeded(self):
        rl = RateLimit(max_per_minute=1)
        rl.record_action()
        assert rl.wait_time > 0

    def test_wait_when_cooldown(self):
        rl = RateLimit(cooldown_seconds=10.0)
        rl.record_action()
        assert rl.wait_time > 0


# ─── DEFAULT_RATE_LIMITS ─────────────────────────────────────────────────


class TestDefaultRateLimits:
    def test_has_twitter(self):
        assert "twitter" in DEFAULT_RATE_LIMITS

    def test_has_instagram(self):
        assert "instagram" in DEFAULT_RATE_LIMITS

    def test_has_facebook(self):
        assert "facebook" in DEFAULT_RATE_LIMITS

    def test_has_telegram(self):
        assert "telegram" in DEFAULT_RATE_LIMITS

    def test_has_vk(self):
        assert "vk" in DEFAULT_RATE_LIMITS

    def test_has_reddit(self):
        assert "reddit" in DEFAULT_RATE_LIMITS

    def test_has_github(self):
        assert "github" in DEFAULT_RATE_LIMITS

    def test_has_habr(self):
        assert "habr" in DEFAULT_RATE_LIMITS

    def test_all_have_platform(self):
        for name, rl in DEFAULT_RATE_LIMITS.items():
            assert rl.platform == name

    def test_all_have_positive_limits(self):
        for name, rl in DEFAULT_RATE_LIMITS.items():
            assert rl.max_per_minute > 0
            assert rl.max_per_hour > 0
            assert rl.max_per_day > 0

    def test_telegram_highest_rate(self):
        tg = DEFAULT_RATE_LIMITS["telegram"]
        tw = DEFAULT_RATE_LIMITS["twitter"]
        assert tg.max_per_minute >= tw.max_per_minute

    def test_reddit_lowest_rate(self):
        rd = DEFAULT_RATE_LIMITS["reddit"]
        assert rd.max_per_minute <= 15


# ─── TaskOrchestrator init ───────────────────────────────────────────────


class TestTaskOrchestratorInit:
    def test_default_workers(self):
        to = TaskOrchestrator()
        assert to._workers == 3

    def test_custom_workers(self):
        to = TaskOrchestrator(workers=5)
        assert to._workers == 5

    def test_empty_queue(self):
        to = TaskOrchestrator()
        assert to._queue == []

    def test_empty_results(self):
        to = TaskOrchestrator()
        assert to._results == []

    def test_default_rate_limits_loaded(self):
        to = TaskOrchestrator()
        assert len(to._rate_limits) > 0
        assert "twitter" in to._rate_limits

    def test_custom_rate_limits(self):
        custom = {"custom_platform": RateLimit("custom_platform", max_per_minute=10)}
        to = TaskOrchestrator(rate_limits=custom)
        assert "custom_platform" in to._rate_limits
        assert "twitter" not in to._rate_limits

    def test_running_false(self):
        to = TaskOrchestrator()
        assert to._running is False

    def test_handlers_empty(self):
        to = TaskOrchestrator()
        assert to._handlers == {}


# ─── TaskOrchestrator.add_task ───────────────────────────────────────────


class TestAddTask:
    def test_add_task(self):
        to = TaskOrchestrator()
        to.add_task(Task(platform="twitter", action="like"))
        assert len(to._queue) == 1

    def test_add_multiple_tasks(self):
        to = TaskOrchestrator()
        to.add_task(Task(platform="twitter", action="like"))
        to.add_task(Task(platform="habr", action="comment"))
        to.add_task(Task(platform="reddit", action="post"))
        assert len(to._queue) == 3

    def test_priority_ordering(self):
        to = TaskOrchestrator()
        to.add_task(Task(priority=TaskPriority.LOW))
        to.add_task(Task(priority=TaskPriority.CRITICAL))
        to.add_task(Task(priority=TaskPriority.HIGH))
        # heapq: first popped should be CRITICAL (lowest value)
        import heapq

        first = heapq.heappop(to._queue)
        assert first.priority == TaskPriority.CRITICAL
