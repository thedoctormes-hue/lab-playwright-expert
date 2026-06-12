"""
Тесты для TaskTemplate — системы шаблонов типовых сценариев.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from lab_playwright_kit.task_template import (
    AuthTask,
    BaseTask,
    ContentPublishTask,
    CrossPostTask,
    DataCollectionTask,
    MonitoringTask,
    SocialMediaTask,
    TaskContext,
    TaskStatus,
    TaskStep,
)


# ─── TaskContext ─────────────────────────────────────────────────────────────

class TestTaskContext:
    def test_creation(self):
        ctx = TaskContext(task_id="abc123", task_name="test")
        assert ctx.task_id == "abc123"
        assert ctx.task_name == "test"
        assert ctx.status == TaskStatus.PENDING
        assert ctx.results == []
        assert ctx.errors == []

    def test_success_count_empty(self):
        ctx = TaskContext()
        assert ctx.success_count == 0
        assert ctx.fail_count == 0

    def test_to_dict(self):
        ctx = TaskContext(task_id="t1", task_name="test", status=TaskStatus.COMPLETED)
        d = ctx.to_dict()
        assert d["task_id"] == "t1"
        assert d["task_name"] == "test"
        assert d["status"] == "completed"
        assert "duration_ms" in d

    def test_duration_zero_without_start(self):
        ctx = TaskContext()
        assert ctx.duration_ms == 0.0


# ─── TaskStep ────────────────────────────────────────────────────────────────

class TestTaskStep:
    def test_creation_defaults(self):
        step = TaskStep(name="navigate", action="navigate", params={"url": "https://example.com"})
        assert step.name == "navigate"
        assert step.action == "navigate"
        assert step.max_retries == 3
        assert step.on_fail == "continue"
        assert step.timeout == 30.0

    def test_creation_custom(self):
        step = TaskStep(
            name="like",
            action="click",
            params={"selector": ".like-btn"},
            on_fail="abort",
            max_retries=5,
            pre_delay=1.0,
            post_delay=2.0,
        )
        assert step.on_fail == "abort"
        assert step.max_retries == 5
        assert step.pre_delay == 1.0
        assert step.post_delay == 2.0


# ─── TaskStatus ──────────────────────────────────────────────────────────────

class TestTaskStatus:
    def test_values(self):
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"
        assert TaskStatus.PAUSED.value == "paused"
        assert TaskStatus.RETRYING.value == "retrying"


# ─── SocialMediaTask ─────────────────────────────────────────────────────────

class TestSocialMediaTask:
    def test_creation(self):
        bm = MagicMock()
        task = SocialMediaTask(bm, platform="twitter")
        assert task._platform == "twitter"
        assert task.get_task_name() == "social_twitter"

    def test_creation_instagram(self):
        bm = MagicMock()
        task = SocialMediaTask(bm, platform="instagram")
        assert task._platform == "instagram"
        assert "like" in task._selectors

    def test_creation_unknown_platform(self):
        bm = MagicMock()
        task = SocialMediaTask(bm, platform="unknown")
        assert task._selectors == {}

    def test_get_steps_base(self):
        bm = MagicMock()
        task = SocialMediaTask(bm)
        assert task.get_steps() == []


# ─── ContentPublishTask ──────────────────────────────────────────────────────

class TestContentPublishTask:
    def test_creation(self):
        bm = MagicMock()
        task = ContentPublishTask(bm, platform="habr")
        assert task._platform == "habr"
        assert task.get_task_name() == "publish_habr"

    def test_creation_with_credentials(self):
        bm = MagicMock()
        creds = {"username": "test", "password": "pass"}
        task = ContentPublishTask(bm, credentials=creds)
        assert task._credentials == creds

    def test_get_steps(self):
        bm = MagicMock()
        task = ContentPublishTask(bm)
        assert task.get_steps() == []


# ─── DataCollectionTask ──────────────────────────────────────────────────────

class TestDataCollectionTask:
    def test_creation(self):
        bm = MagicMock()
        task = DataCollectionTask(bm, niche="ecommerce")
        assert task._niche == "ecommerce"
        assert task.get_task_name() == "collect_ecommerce"

    def test_get_steps(self):
        bm = MagicMock()
        task = DataCollectionTask(bm)
        assert task.get_steps() == []


# ─── AuthTask ────────────────────────────────────────────────────────────────

class TestAuthTask:
    def test_creation(self):
        bm = MagicMock()
        task = AuthTask(bm)
        assert task._credentials == {}
        assert task._cookies == []

    def test_creation_with_credentials(self):
        bm = MagicMock()
        creds = {"username": "user", "password": "pass"}
        task = AuthTask(bm, credentials=creds)
        assert task._credentials == creds

    def test_get_task_name(self):
        bm = MagicMock()
        task = AuthTask(bm)
        assert task.get_task_name() == "auth"

    def test_get_cookies_empty(self):
        bm = MagicMock()
        task = AuthTask(bm)
        assert task.get_cookies() == []

    def test_get_steps(self):
        bm = MagicMock()
        task = AuthTask(bm)
        assert task.get_steps() == []


# ─── MonitoringTask ──────────────────────────────────────────────────────────

class TestMonitoringTask:
    def test_creation(self):
        bm = MagicMock()
        task = MonitoringTask(bm)
        assert task._interval == 300.0
        assert task._snapshots == {}

    def test_creation_custom_interval(self):
        bm = MagicMock()
        task = MonitoringTask(bm, check_interval=60.0)
        assert task._interval == 60.0

    def test_get_task_name(self):
        bm = MagicMock()
        task = MonitoringTask(bm)
        assert task.get_task_name() == "monitor"

    def test_get_steps(self):
        bm = MagicMock()
        task = MonitoringTask(bm)
        assert task.get_steps() == []


# ─── CrossPostTask ───────────────────────────────────────────────────────────

class TestCrossPostTask:
    def test_creation(self):
        bm = MagicMock()
        task = CrossPostTask(bm)
        assert task._credentials == {}
        assert task.get_task_name() == "crosspost"

    def test_creation_with_credentials(self):
        bm = MagicMock()
        creds = {"habr": {"login": "user", "password": "pass"}}
        task = CrossPostTask(bm, credentials=creds)
        assert task._credentials == creds

    def test_platform_urls(self):
        assert "habr" in CrossPostTask.PLATFORM_URLS
        assert "vc_ru" in CrossPostTask.PLATFORM_URLS
        assert "telegraph" in CrossPostTask.PLATFORM_URLS

    def test_get_steps(self):
        bm = MagicMock()
        task = CrossPostTask(bm)
        assert task.get_steps() == []


# ─── BaseTask (abstract) ─────────────────────────────────────────────────────

class TestBaseTask:
    def test_cannot_instantiate_abstract(self):
        bm = MagicMock()
        with pytest.raises(TypeError):
            BaseTask(bm)

    def test_concrete_subclass(self):
        bm = MagicMock()

        class ConcreteTask(BaseTask):
            def get_steps(self):
                return [TaskStep(name="step1", action="navigate", params={})]

            def get_task_name(self):
                return "concrete"

        task = ConcreteTask(bm)
        assert task.get_task_name() == "concrete"
        assert len(task.get_steps()) == 1

    def test_eval_condition_true(self):
        bm = MagicMock()

        class ConcreteTask(BaseTask):
            def get_steps(self):
                return []

            def get_task_name(self):
                return "test"

        task = ConcreteTask(bm)
        ctx = TaskContext()
        assert task._eval_condition("len(errors) == 0", ctx) is True

    def test_eval_condition_false(self):
        bm = MagicMock()

        class ConcreteTask(BaseTask):
            def get_steps(self):
                return []

            def get_task_name(self):
                return "test"

        task = ConcreteTask(bm)
        ctx = TaskContext()
        ctx.errors = ["some error"]
        assert task._eval_condition("len(errors) == 0", ctx) is False

    def test_eval_condition_error_returns_true(self):
        bm = MagicMock()

        class ConcreteTask(BaseTask):
            def get_steps(self):
                return []

            def get_task_name(self):
                return "test"

        task = ConcreteTask(bm)
        ctx = TaskContext()
        # Некорректное выражение — должно вернуть True (fail-open)
        assert task._eval_condition("undefined_var", ctx) is True


# ─── Integration-style tests ─────────────────────────────────────────────────

class TestTaskContextIntegration:
    def test_full_lifecycle(self):
        ctx = TaskContext(task_id="t1", task_name="test")
        assert ctx.status == TaskStatus.PENDING

        ctx.status = TaskStatus.RUNNING
        ctx.total_steps = 3
        ctx.current_step = 1
        assert ctx.status == TaskStatus.RUNNING

        ctx.status = TaskStatus.COMPLETED
        assert ctx.status == TaskStatus.COMPLETED

    def test_results_tracking(self):
        ctx = TaskContext()
        from lab_playwright_kit.action_engine import ActionResult

        ctx.results.append(ActionResult(action_type="click", status="success"))
        ctx.results.append(ActionResult(action_type="type", status="success"))
        ctx.results.append(ActionResult(action_type="navigate", status="failed"))

        assert ctx.success_count == 2
        assert ctx.fail_count == 1


# ─── AuthTask Enhanced ───────────────────────────────────────────────────────

class TestAuthTaskEnhanced:
    def test_platform_presets_exist(self):
        assert "habr" in AuthTask.PLATFORM_PRESETS
        assert "vc_ru" in AuthTask.PLATFORM_PRESETS
        assert "tenchat" in AuthTask.PLATFORM_PRESETS

    def test_habr_preset_structure(self):
        preset = AuthTask.PLATFORM_PRESETS["habr"]
        assert "login_url" in preset
        assert "auth_url" in preset
        assert "auth_selectors" in preset
        assert "username_selector" in preset
        assert "password_selector" in preset
        assert "submit_selector" in preset

    def test_vc_ru_preset_structure(self):
        preset = AuthTask.PLATFORM_PRESETS["vc_ru"]
        assert "login_url" in preset
        assert "auth_url" in preset
        assert "auth_selectors" in preset

    def test_tenchat_preset_structure(self):
        preset = AuthTask.PLATFORM_PRESETS["tenchat"]
        assert "login_url" in preset
        assert "auth_url" in preset

    def test_unknown_preset(self):
        assert "unknown_platform" not in AuthTask.PLATFORM_PRESETS

    def test_presets_have_auth_selectors(self):
        for platform, preset in AuthTask.PLATFORM_PRESETS.items():
            assert len(preset["auth_selectors"]) > 0, f"{platform}: no auth_selectors"
