"""
Tests for v2.0 modules: FingerprintManager, HumanBehaviorEngine,
CaptchaSolver, AccountManager, ActionEngine, TaskOrchestrator.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from lab_playwright_kit import (
    AccountManager,
    AccountStatus,
    ActionEngine,
    ActionType,
    BehaviorProfile,
    BrowserFingerprint,
    CaptchaSolver,
    CaptchaType,
    FingerprintManager,
    HumanBehaviorEngine,
    Platform,
    Task,
    TaskOrchestrator,
    TaskPriority,
)


# ─────────────────────────────────────────────
# FingerprintManager
# ─────────────────────────────────────────────

class TestFingerprintManager:
    """Tests for FingerprintManager and BrowserFingerprint."""

    def test_generate_chrome_windows(self):
        fp = FingerprintManager.generate("test_chrome_win", os="windows", browser="chrome")
        assert fp.profile_id == "test_chrome_win"
        assert fp.os == "windows"
        assert "Windows" in fp.user_agent

    def test_generate_firefox_linux(self):
        fp = FingerprintManager.generate("test_ff_linux", os="linux", browser="firefox")
        assert fp.os == "linux"
        assert "Firefox" in fp.user_agent

    def test_generate_safari_mac(self):
        fp = FingerprintManager.generate("test_safari_mac", os="macos", browser="safari")
        assert fp.os == "macos"
        assert fp.user_agent is not None

    def test_deterministic_same_seed(self):
        fp1 = FingerprintManager.generate("same_seed", os="windows", browser="chrome")
        fp2 = FingerprintManager.generate("same_seed", os="windows", browser="chrome")
        assert fp1.user_agent == fp2.user_agent
        assert fp1.screen_width == fp2.screen_width
        assert fp1.webgl_renderer == fp2.webgl_renderer

    def test_different_seeds_differ(self):
        fp1 = FingerprintManager.generate("seed_aaa", os="windows", browser="chrome")
        fp2 = FingerprintManager.generate("seed_bbb", os="windows", browser="chrome")
        assert fp1.user_agent != fp2.user_agent

    def test_to_dict(self):
        fp = FingerprintManager.generate("dict_test", os="windows", browser="chrome")
        d = fp.to_dict()
        assert "profile_id" in d
        assert "os" in d
        assert "user_agent" in d
        assert "screen_width" in d
        assert "webgl_renderer" in d

    def test_to_dict_has_all_fields(self):
        fp = FingerprintManager.generate("full_test", os="windows", browser="chrome")
        d = fp.to_dict()
        expected_keys = {
            "profile_id", "user_agent", "brand_version", "webgl_vendor",
            "webgl_renderer", "webgl_version", "webgl_shading_language",
            "webgl_extensions", "canvas_noise_seed", "audio_noise_seed",
            "screen_width", "screen_height", "screen_avail_width",
            "screen_avail_height", "screen_color_depth", "screen_pixel_ratio",
            "hardware_cores", "hardware_memory", "hardware_platform",
            "fonts", "os", "timezone", "locale", "languages",
        }
        assert expected_keys.issubset(d.keys())

    def test_from_dict_roundtrip(self):
        fp1 = FingerprintManager.generate("roundtrip", os="windows", browser="chrome")
        d = fp1.to_dict()
        fp2 = BrowserFingerprint.from_dict(d)
        assert fp1.user_agent == fp2.user_agent
        assert fp1.os == fp2.os

    def test_summary(self):
        fp = FingerprintManager.generate("summary_test", os="windows", browser="chrome")
        s = fp.summary
        assert "summary_test" in s
        assert "windows" in s

    def test_screen_dimensions(self):
        fp = FingerprintManager.generate("screen_test", os="windows", browser="chrome")
        assert fp.screen_width > 0
        assert fp.screen_height > 0

    def test_hardware_cores(self):
        fp = FingerprintManager.generate("hw_test", os="windows", browser="chrome")
        assert fp.hardware_cores in [2, 4, 8, 16]

    def test_hardware_memory(self):
        fp = FingerprintManager.generate("mem_test", os="windows", browser="chrome")
        assert fp.hardware_memory in [2, 4, 8, 16, 32, 64]

    def test_webgl_fields(self):
        fp = FingerprintManager.generate("webgl_test", os="windows", browser="chrome")
        assert fp.webgl_vendor is not None
        assert fp.webgl_renderer is not None
        assert fp.webgl_version is not None

    def test_canvas_noise_seed(self):
        fp = FingerprintManager.generate("canvas_test", os="windows", browser="chrome")
        assert isinstance(fp.canvas_noise_seed, int)

    def test_audio_noise_seed(self):
        fp = FingerprintManager.generate("audio_test", os="windows", browser="chrome")
        assert isinstance(fp.audio_noise_seed, int)

    def test_fonts_list(self):
        fp = FingerprintManager.generate("fonts_test", os="windows", browser="chrome")
        assert isinstance(fp.fonts, list)
        assert len(fp.fonts) > 0

    def test_timezone(self):
        fp = FingerprintManager.generate("tz_test", os="windows", browser="chrome")
        assert fp.timezone is not None

    def test_locale(self):
        fp = FingerprintManager.generate("locale_test", os="windows", browser="chrome")
        assert fp.locale is not None

    def test_languages(self):
        fp = FingerprintManager.generate("lang_test", os="windows", browser="chrome")
        assert isinstance(fp.languages, list)
        assert len(fp.languages) > 0


# ─────────────────────────────────────────────
# HumanBehaviorEngine
# ─────────────────────────────────────────────

class TestHumanBehaviorEngine:
    """Tests for HumanBehaviorEngine and BehaviorProfile."""

    def test_behavior_profile_defaults(self):
        profile = BehaviorProfile()
        assert profile.name == "casual_reader"
        assert profile.mouse_move_min_ms == 200
        assert profile.mouse_move_max_ms == 800

    def test_behavior_profile_custom(self):
        profile = BehaviorProfile(
            name="custom",
            mouse_move_min_ms=100,
            mouse_move_max_ms=500,
        )
        assert profile.name == "custom"
        assert profile.mouse_move_min_ms == 100

    def test_engine_creation(self):
        page = MagicMock()
        engine = HumanBehaviorEngine(page, profile="casual_reader")
        assert engine.profile.name == "casual_reader"

    def test_engine_invalid_profile_fallback(self):
        page = MagicMock()
        engine = HumanBehaviorEngine(page, profile="nonexistent")
        assert engine.profile.name == "casual_reader"

    def test_bezier_points_generation(self):
        page = MagicMock()
        engine = HumanBehaviorEngine(page)
        points = engine._generate_bezier_points(0, 0, 100, 100, 10)
        assert len(points) >= 10
        assert abs(points[0][0]) < 10
        assert abs(points[0][1]) < 10
        assert abs(points[-1][0] - 100) < 10
        assert abs(points[-1][1] - 100) < 10

    def test_public_methods_exist(self):
        page = MagicMock()
        engine = HumanBehaviorEngine(page)
        assert hasattr(engine, 'move_mouse_to')
        assert hasattr(engine, 'move_mouse_to_element')
        assert hasattr(engine, 'click')
        assert hasattr(engine, 'double_click')
        assert hasattr(engine, 'hover')
        assert hasattr(engine, 'scroll_down')
        assert hasattr(engine, 'scroll_up')
        assert hasattr(engine, 'scroll_to_top')
        assert hasattr(engine, 'scroll_to_bottom')
        assert hasattr(engine, 'scroll_to_element')
        assert hasattr(engine, 'type_text')
        assert hasattr(engine, 'type_like_human')
        assert hasattr(engine, 'read_page')
        assert hasattr(engine, 'read_article')
        assert hasattr(engine, 'wait_between_actions')
        assert hasattr(engine, 'random_idle')


# ─────────────────────────────────────────────
# CaptchaSolver
# ─────────────────────────────────────────────

class TestCaptchaSolver:
    """Tests for CaptchaSolver."""

    def test_init_default(self):
        solver = CaptchaSolver(api_key="test_key_123")
        assert solver.config.api_key == "test_key_123"
        assert solver.config.provider.value == "2captcha"

    def test_init_2captcha(self):
        solver = CaptchaSolver(api_key="test_key_123", provider="2captcha")
        assert solver.config.provider.value == "2captcha"

    def test_init_capsolver(self):
        solver = CaptchaSolver(api_key="test_key_456", provider="capsolver")
        assert solver.config.provider.value == "capsolver"

    def test_init_invalid_provider(self):
        with pytest.raises(ValueError):
            CaptchaSolver(api_key="test", provider="invalid_provider")

    def test_captcha_type_enum(self):
        assert CaptchaType.RECAPTCHA_V2.value == "recaptcha_v2"
        assert CaptchaType.RECAPTCHA_V3.value == "recaptcha_v3"
        assert CaptchaType.HCAPTCHA.value == "hcaptcha"
        assert CaptchaType.CLOUDFLARE_TURNSTILE.value == "cloudflare_turnstile"

    def test_solve_methods_exist(self):
        solver = CaptchaSolver(api_key="test")
        assert hasattr(solver, 'solve_recaptcha_v2')
        assert hasattr(solver, 'solve_recaptcha_v3')
        assert hasattr(solver, 'solve_hcaptcha')
        assert hasattr(solver, 'solve_cloudflare_turnstile')
        assert hasattr(solver, 'auto_solve')
        assert hasattr(solver, 'inject_recaptcha_token')
        assert hasattr(solver, 'inject_hcaptcha_token')
        assert hasattr(solver, 'inject_turnstile_token')

    def test_stats(self):
        solver = CaptchaSolver(api_key="test")
        stats = solver.stats
        assert isinstance(stats, dict)


# ─────────────────────────────────────────────
# AccountManager
# ─────────────────────────────────────────────

class TestAccountManager:
    """Tests for AccountManager."""

    def _make_am(self):
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        return AccountManager(db_path=f.name), f.name

    def test_init_creates_db(self):
        am, path = self._make_am()
        try:
            assert os.path.exists(path)
            conn = sqlite3.connect(path)
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            assert "accounts" in tables
            conn.close()
        finally:
            os.unlink(path)

    def test_create_account(self):
        am, path = self._make_am()
        try:
            account = am.create_account(
                username="test_user",
                platform=Platform.TELEGRAM,
                password="secret_pass",
            )
            assert account.username == "test_user"
            assert account.platform == Platform.TELEGRAM
            assert account.status == AccountStatus.CREATED
            assert account.id is not None
        finally:
            os.unlink(path)

    def test_get_account(self):
        am, path = self._make_am()
        try:
            created = am.create_account(username="get_test", platform=Platform.TELEGRAM)
            fetched = am.get_account(created.id)
            assert fetched is not None
            assert fetched.username == "get_test"
        finally:
            os.unlink(path)

    def test_get_nonexistent_account(self):
        am, path = self._make_am()
        try:
            assert am.get_account(99999) is None
        finally:
            os.unlink(path)

    def test_update_status(self):
        am, path = self._make_am()
        try:
            account = am.create_account(username="status_test", platform=Platform.TELEGRAM)
            am.update_status(account.id, AccountStatus.ACTIVE)
            updated = am.get_account(account.id)
            assert updated.status == AccountStatus.ACTIVE
        finally:
            os.unlink(path)

    def test_get_accounts(self):
        am, path = self._make_am()
        try:
            am.create_account(username="user1", platform=Platform.TELEGRAM)
            am.create_account(username="user2", platform=Platform.INSTAGRAM)
            am.create_account(username="user3", platform=Platform.TELEGRAM)

            all_accounts = am.get_accounts()
            assert len(all_accounts) == 3

            tg_accounts = am.get_accounts(platform=Platform.TELEGRAM)
            assert len(tg_accounts) == 2
        finally:
            os.unlink(path)

    def test_get_accounts_by_status(self):
        am, path = self._make_am()
        try:
            acc = am.create_account(username="active1", platform=Platform.TELEGRAM)
            am.update_status(acc.id, AccountStatus.ACTIVE)

            active = am.get_accounts(status=AccountStatus.ACTIVE.value)
            assert len(active) >= 1
        finally:
            os.unlink(path)

    def test_account_status_enum(self):
        assert AccountStatus.CREATED.value == "created"
        assert AccountStatus.WARMUP.value == "warmup"
        assert AccountStatus.ACTIVE.value == "active"
        assert AccountStatus.COOLDOWN.value == "cooldown"
        assert AccountStatus.BANNED.value == "banned"
        assert AccountStatus.DEAD.value == "dead"

    def test_platform_enum(self):
        assert Platform.TELEGRAM.value == "telegram"
        assert Platform.INSTAGRAM.value == "instagram"
        assert Platform.TWITTER.value == "twitter"
        assert Platform.FACEBOOK.value == "facebook"
        assert Platform.YOUTUBE.value == "youtube"

    def test_encryption_roundtrip(self):
        am, path = self._make_am()
        try:
            am._encryption_key = "test_key_42"
            original = "my_secret_password_123"
            encrypted = am._encrypt(original)
            decrypted = am._decrypt(encrypted)
            assert decrypted == original
            assert encrypted != original
        finally:
            os.unlink(path)

    def test_delete_account(self):
        am, path = self._make_am()
        try:
            account = am.create_account(username="delete_me", platform=Platform.TELEGRAM)
            assert am.delete_account(account.id) is True
            assert am.get_account(account.id) is None
        finally:
            os.unlink(path)

    def test_get_password(self):
        """get_password takes an Account object."""
        am, path = self._make_am()
        try:
            account = am.create_account(
                username="pwd_test",
                platform=Platform.TELEGRAM,
                password="my_pwd_123",
            )
            pwd = am.get_password(account)
            assert pwd == "my_pwd_123"
        finally:
            os.unlink(path)

    def test_get_account_by_username(self):
        """get_account_by_username(platform, username)."""
        am, path = self._make_am()
        try:
            am.create_account(username="lookup_user", platform=Platform.TELEGRAM)
            found = am.get_account_by_username(Platform.TELEGRAM, "lookup_user")
            assert found is not None
            assert found.username == "lookup_user"
        finally:
            os.unlink(path)

    def test_get_available_accounts(self):
        am, path = self._make_am()
        try:
            acc = am.create_account(username="avail1", platform=Platform.TELEGRAM)
            am.update_status(acc.id, AccountStatus.ACTIVE)
            available = am.get_available_accounts(Platform.TELEGRAM)
            assert len(available) >= 1
        finally:
            os.unlink(path)

    def test_record_action(self):
        am, path = self._make_am()
        try:
            account = am.create_account(username="action_test", platform=Platform.TELEGRAM)
            am.record_action(account.id, "like", "https://t.me/test/123")
            history = am.get_action_history(account.id)
            assert len(history) == 1
        finally:
            os.unlink(path)

    def test_set_cooldown(self):
        """set_cooldown takes (account_id, hours=...)."""
        am, path = self._make_am()
        try:
            account = am.create_account(username="cooldown_test", platform=Platform.TELEGRAM)
            am.set_cooldown(account.id, hours=0.5)  # 30 minutes
            updated = am.get_account(account.id)
            assert updated.status == AccountStatus.COOLDOWN
        finally:
            os.unlink(path)

    def test_get_stats(self):
        am, path = self._make_am()
        try:
            am.create_account(username="stat1", platform=Platform.TELEGRAM)
            am.create_account(username="stat2", platform=Platform.INSTAGRAM)
            stats = am.get_stats()
            assert "total" in stats
            assert stats["total"] == 2
            assert "by_status" in stats
        finally:
            os.unlink(path)


# ─────────────────────────────────────────────
# ActionEngine
# ─────────────────────────────────────────────

class TestActionEngine:
    """Tests for ActionEngine."""

    def test_action_type_enum(self):
        assert ActionType.LIKE.value == "like"
        assert ActionType.COMMENT.value == "comment"
        assert ActionType.FOLLOW.value == "follow"
        assert ActionType.UNFOLLOW.value == "unfollow"
        assert ActionType.REPOST.value == "repost"
        assert ActionType.VIEW.value == "view"
        assert ActionType.SCROLL.value == "scroll"

    def test_engine_creation(self):
        page = MagicMock()
        engine = ActionEngine(page)
        assert engine.page == page

    def test_engine_with_profile(self):
        page = MagicMock()
        engine = ActionEngine(page, profile="social_media")
        assert engine.behavior is not None

    def test_engine_default_profile(self):
        page = MagicMock()
        engine = ActionEngine(page)
        assert engine.behavior is not None

    def test_action_result(self):
        from lab_playwright_kit.action_engine import ActionResult
        result = ActionResult(
            action_type=ActionType.LIKE,
            status="success",
            target="https://t.me/test/123",
        )
        assert result.status == "success"
        assert result.action_type == ActionType.LIKE
        assert result.message == ""

    def test_action_result_with_error(self):
        from lab_playwright_kit.action_engine import ActionResult
        result = ActionResult(
            action_type=ActionType.COMMENT,
            status="failed",
            target="https://t.me/test/456",
            message="Element not found",
        )
        assert result.status == "failed"
        assert result.message == "Element not found"

    def test_engine_counters(self):
        page = MagicMock()
        engine = ActionEngine(page)
        assert engine.success_count == 0
        assert engine.fail_count == 0

    def test_engine_results_list(self):
        page = MagicMock()
        engine = ActionEngine(page)
        assert isinstance(engine.results, list)
        assert len(engine.results) == 0

    def test_engine_has_action_methods(self):
        page = MagicMock()
        engine = ActionEngine(page)
        assert hasattr(engine, 'like')
        assert hasattr(engine, 'comment')
        assert hasattr(engine, 'follow')
        assert hasattr(engine, 'repost')
        assert hasattr(engine, 'view_content')
        assert hasattr(engine, 'scroll_and_read')
        assert hasattr(engine, 'navigate')
        assert hasattr(engine, 'click_element')
        assert hasattr(engine, 'type_in_field')
        assert hasattr(engine, 'execute_chain')


# ─────────────────────────────────────────────
# TaskOrchestrator
# ─────────────────────────────────────────────

class TestTaskOrchestrator:
    """Tests for TaskOrchestrator and Task model."""

    def _make_task(self, **kwargs):
        defaults = dict(
            id="task_001",
            platform="telegram",
            action=ActionType.LIKE,
            target="https://t.me/test/123",
            params={},
        )
        defaults.update(kwargs)
        return Task(**defaults)

    def test_task_creation(self):
        task = self._make_task(priority=TaskPriority.HIGH)
        assert task.id == "task_001"
        assert task.action == ActionType.LIKE
        assert task.priority == TaskPriority.HIGH
        assert task.status == "pending"

    def test_task_priority_enum(self):
        assert TaskPriority.CRITICAL.value == 0
        assert TaskPriority.HIGH.value == 1
        assert TaskPriority.NORMAL.value == 2
        assert TaskPriority.LOW.value == 3
        assert TaskPriority.BACKGROUND.value == 4

    def test_orchestrator_creation(self):
        orch = TaskOrchestrator(workers=5)
        assert orch._workers == 5

    def test_add_task(self):
        orch = TaskOrchestrator()
        orch.add_task(self._make_task(id="add_test"))
        assert orch.queue_size == 1

    def test_add_tasks_batch(self):
        orch = TaskOrchestrator()
        tasks = [
            self._make_task(id=f"batch_{i}", target=f"https://t.me/test/{i}")
            for i in range(10)
        ]
        orch.add_tasks(tasks)
        assert orch.queue_size == 10

    def test_stats(self):
        orch = TaskOrchestrator(workers=3)
        orch.add_task(self._make_task(id="s1"))
        stats = orch.stats
        assert isinstance(stats, dict)
        assert stats["queue_size"] == 1
        assert stats["workers"] == 3

    def test_register_handler(self):
        orch = TaskOrchestrator()
        handler = AsyncMock()
        orch.register_handler(ActionType.LIKE, handler)
        assert ActionType.LIKE in orch._handlers

    def test_register_handlers(self):
        orch = TaskOrchestrator()
        handlers = {
            ActionType.LIKE: AsyncMock(),
            ActionType.COMMENT: AsyncMock(),
        }
        orch.register_handlers(handlers)
        assert len(orch._handlers) == 2

    def test_task_has_timestamps(self):
        task = self._make_task(id="time_test")
        assert task.created_at is not None
        # started_at and completed_at default to 0 (not None)
        assert task.started_at == 0
        assert task.completed_at == 0

    def test_task_retry_fields(self):
        task = self._make_task(id="retry_test", max_retries=5)
        assert task.max_retries == 5
        assert task.retry_count == 0

    def test_rate_limit_dataclass(self):
        from lab_playwright_kit.task_orchestrator import RateLimit
        rl = RateLimit(
            platform="telegram",
            max_per_minute=30,
            max_per_hour=500,
        )
        assert rl.platform == "telegram"
        assert rl.max_per_minute == 30

    def test_set_rate_limit(self):
        orch = TaskOrchestrator()
        from lab_playwright_kit.task_orchestrator import RateLimit
        rl = RateLimit(platform="telegram", max_per_minute=30, max_per_hour=500)
        orch.set_rate_limit("telegram", rl)
        assert "telegram" in orch._rate_limits
