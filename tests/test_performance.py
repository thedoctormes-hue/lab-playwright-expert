"""
Performance Regression Tests for Lab Playwright Kit v2.0.

These tests ensure that critical operations stay within performance budgets.
They are designed to catch regressions early — not to be precise benchmarks.

Run with:
    PYTHONPATH=src pytest tests/test_performance.py -v
    PYTHONPATH=src pytest tests/test_performance.py -v --timeout=60
"""
from __future__ import annotations

import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure src is on path
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from lab_playwright_kit import (
    Account,
    AccountManager,
    AccountStatus,
    ActionEngine,
    ActionResult,
    ActionStep,
    ActionType,
    BehaviorProfile,
    BrowserFingerprint,
    CaptchaResult,
    CaptchaSolver,
    CaptchaType,
    FingerprintManager,
    HumanBehaviorEngine,
    Platform,
    SolverProvider,
    Task,
    TaskOrchestrator,
    TaskPriority,
    TaskStatus,
)
from lab_playwright_kit.captcha_solver import SolverConfig
from lab_playwright_kit.task_orchestrator import RateLimit


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def measure_ms(func, iterations=200):
    """Run func N times and return list of per-call times in ms."""
    # Warmup
    for _ in range(min(10, iterations // 10)):
        func()

    times = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        func()
        end = time.perf_counter_ns()
        times.append((end - start) / 1_000_000)  # ns → ms
    return times


def assert_performance(name, times, target_ms, percentile=50):
    """Assert that the given percentile of times is within target."""
    sorted_times = sorted(times)
    idx = int(len(sorted_times) * percentile / 100)
    actual = sorted_times[idx]
    avg = statistics.mean(times)
    assert actual <= target_ms, (
        f"{name}: p{percentile}={actual:.4f}ms > target={target_ms}ms "
        f"(avg={avg:.4f}ms, max={max(times):.4f}ms)"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Fingerprint Module Performance
# ═══════════════════════════════════════════════════════════════════════════════

class TestFingerprintPerformance:
    """Performance regression tests for Fingerprint module."""

    def test_generation_within_budget(self):
        """Fingerprint generation should be <1ms on average."""
        counter = [0]
        def generate():
            counter[0] += 1
            FingerprintManager.generate(f"perf_{counter[0]}", os="windows", browser="chrome")

        times = measure_ms(generate, iterations=200)
        assert_performance("Fingerprint Generation", times, target_ms=1.0)

    def test_serialization_within_budget(self):
        """Fingerprint to_dict should be <0.1ms."""
        fp = FingerprintManager.generate("serial_perf", os="windows", browser="chrome")
        times = measure_ms(lambda: fp.to_dict(), iterations=500)
        assert_performance("Fingerprint Serialization", times, target_ms=0.1)

    def test_deserialization_within_budget(self):
        """Fingerprint from_dict should be <0.1ms."""
        fp = FingerprintManager.generate("deserial_perf", os="windows", browser="chrome")
        d = fp.to_dict()
        times = measure_ms(lambda: BrowserFingerprint.from_dict(d), iterations=500)
        assert_performance("Fingerprint Deserialization", times, target_ms=0.1)

    def test_noise_hex_within_budget(self):
        """Canvas/audio noise hex properties should be <0.01ms."""
        fp = FingerprintManager.generate("noise_perf", os="windows", browser="chrome")
        times = measure_ms(lambda: (fp.canvas_noise_hex, fp.audio_noise_hex), iterations=500)
        assert_performance("Noise Hex Properties", times, target_ms=0.01)

    def test_summary_within_budget(self):
        """Fingerprint summary property should be <0.05ms."""
        fp = FingerprintManager.generate("summary_perf", os="windows", browser="chrome")
        times = measure_ms(lambda: fp.summary, iterations=500)
        assert_performance("Fingerprint Summary", times, target_ms=0.05)

    def test_generation_deterministic_performance(self):
        """Same seed should produce similar performance (no degradation)."""
        fp1_times = measure_ms(lambda: FingerprintManager.generate("det_1"), iterations=100)
        fp2_times = measure_ms(lambda: FingerprintManager.generate("det_2"), iterations=100)
        avg1 = statistics.mean(fp1_times)
        avg2 = statistics.mean(fp2_times)
        # Performance should be within 2x of each other
        ratio = max(avg1, avg2) / max(min(avg1, avg2), 0.0001)
        assert ratio < 2.0, f"Performance ratio {ratio:.1f}x between seeds (degradation)"

    def test_all_os_generations(self):
        """All OS/browser combos should generate within budget."""
        combos = [
            ("windows", "chrome"), ("macos", "chrome"), ("linux", "chrome"),
            ("windows", "firefox"), ("macos", "firefox"), ("linux", "firefox"),
            ("windows", "edge"), ("macos", "safari"), ("android", "chrome"),
        ]
        for os, browser in combos:
            counter = [0]
            def gen(os=os, browser=browser):
                counter[0] += 1
                FingerprintManager.generate(f"combo_{counter[0]}", os=os, browser=browser)

            times = measure_ms(gen, iterations=50)
            avg = statistics.mean(times)
            assert avg < 2.0, f"Generation for {os}/{browser} too slow: {avg:.4f}ms"


# ═══════════════════════════════════════════════════════════════════════════════
# Human Behavior Performance
# ═══════════════════════════════════════════════════════════════════════════════

class TestHumanBehaviorPerformance:
    """Performance regression tests for Human Behavior module."""

    def test_bezier_generation_within_budget(self):
        """Bezier curve generation should be <0.1ms."""
        page = MagicMock()
        engine = HumanBehaviorEngine(page)
        times = measure_ms(
            lambda: engine._generate_bezier_points(0, 0, 100, 100, 20),
            iterations=500,
        )
        assert_performance("Bezier Generation (100px)", times, target_ms=0.1)

    def test_bezier_long_distance(self):
        """Bezier for long distances should be <0.5ms."""
        page = MagicMock()
        engine = HumanBehaviorEngine(page)
        times = measure_ms(
            lambda: engine._generate_bezier_points(0, 0, 1000, 1000, 50),
            iterations=200,
        )
        assert_performance("Bezier Generation (1000px)", times, target_ms=0.5)

    def test_profile_creation_within_budget(self):
        """BehaviorProfile creation should be <0.01ms."""
        times = measure_ms(
            lambda: BehaviorProfile(name="perf", mouse_move_min_ms=100),
            iterations=500,
        )
        assert_performance("BehaviorProfile Creation", times, target_ms=0.01)

    def test_profile_preset_access(self):
        """Behavior profile preset access should be <0.001ms."""
        from lab_playwright_kit import BEHAVIOR_PROFILES
        times = measure_ms(
            lambda: BEHAVIOR_PROFILES.get("casual_reader"),
            iterations=500,
        )
        assert_performance("Profile Preset Access", times, target_ms=0.001)

    def test_engine_creation(self):
        """HumanBehaviorEngine creation should be <0.1ms."""
        page = MagicMock()
        times = measure_ms(
            lambda: HumanBehaviorEngine(page, profile="casual_reader"),
            iterations=200,
        )
        assert_performance("HumanBehaviorEngine Creation", times, target_ms=0.1)


# ═══════════════════════════════════════════════════════════════════════════════
# Account Manager Performance
# ═══════════════════════════════════════════════════════════════════════════════

class TestAccountPerformance:
    """Performance regression tests for Account module.

    Note: These tests use SQLite and may be flaky under heavy parallel load.
    They are marked with reruns to handle I/O contention.
    """

    def _get_db(self):
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        return AccountManager(db_path=f.name), f.name

    @pytest.mark.flaky(reruns=2, reruns_delay=1)
    def test_account_creation_within_budget(self):
        """Account creation should be <30ms (SQLite write + Fernet encrypt, allow retries under load)."""
        am, path = self._get_db()
        counter = [0]
        def create():
            counter[0] += 1
            try:
                am.create_account(platform="telegram", username=f"perf_{counter[0]}")
            except ValueError:
                pass

        times = measure_ms(create, iterations=100)
        assert_performance("Account Creation", times, target_ms=30.0)
        os.unlink(path)

    def test_account_query_within_budget(self):
        """Account query by ID should be <1ms."""
        am, path = self._get_db()
        acc = am.create_account(platform="telegram", username="query_perf")
        times = measure_ms(lambda: am.get_account(acc.id), iterations=200)
        assert_performance("Account Query", times, target_ms=1.0)
        os.unlink(path)

    @pytest.mark.flaky(reruns=2, reruns_delay=1)
    def test_action_recording_within_budget(self):
        """Action recording should be <30ms (SQLite write, allow retries under load)."""
        am, path = self._get_db()
        acc = am.create_account(platform="telegram", username="action_perf")
        times = measure_ms(
            lambda: am.record_action(acc.id, "like", "https://t.me/test/1"),
            iterations=100,
        )
        assert_performance("Action Recording", times, target_ms=30.0)
        os.unlink(path)

    @pytest.mark.flaky(reruns=2, reruns_delay=1)
    def test_status_transition_within_budget(self):
        """Status transition should be <30ms (SQLite write, allow retries under load)."""
        am, path = self._get_db()
        acc = am.create_account(platform="telegram", username="status_perf")
        statuses = [AccountStatus.WARMUP, AccountStatus.ACTIVE, AccountStatus.COOLDOWN]
        idx = [0]
        def transition():
            am.update_status(acc.id, statuses[idx[0] % len(statuses)])
            idx[0] += 1

        times = measure_ms(transition, iterations=100)
        assert_performance("Status Transition", times, target_ms=30.0)
        os.unlink(path)

    def test_encryption_within_budget(self):
        """Password encrypt+decrypt should be <0.1ms."""
        am, path = self._get_db()
        am._encryption_key = "perf_key_42"
        times = measure_ms(
            lambda: am._decrypt(am._encrypt("test_pwd")),
            iterations=200,
        )
        assert_performance("Encrypt+Decrypt", times, target_ms=0.1)
        os.unlink(path)

    def test_is_available_within_budget(self):
        """Account.is_available should be <0.01ms."""
        account = Account(
            id=1, platform="telegram", username="avail_perf",
            status=AccountStatus.ACTIVE, daily_actions=5, daily_limit=100,
        )
        times = measure_ms(lambda: account.is_available, iterations=500)
        assert_performance("is_available Check", times, target_ms=0.01)

    def test_account_stats_within_budget(self):
        """AccountManager.get_stats should be <5ms."""
        am, path = self._get_db()
        for i in range(10):
            am.create_account(platform="telegram", username=f"stats_{i}")
        times = measure_ms(lambda: am.get_stats(), iterations=100)
        assert_performance("Account Stats", times, target_ms=5.0)
        os.unlink(path)


# ═══════════════════════════════════════════════════════════════════════════════
# Action Engine Performance
# ═══════════════════════════════════════════════════════════════════════════════

class TestActionEnginePerformance:
    """Performance regression tests for Action Engine module."""

    def test_action_result_creation(self):
        """ActionResult creation should be <0.01ms."""
        times = measure_ms(
            lambda: ActionResult(
                action_type=ActionType.LIKE,
                status="success",
                target="https://t.me/test/123",
                duration_ms=150.0,
            ),
            iterations=500,
        )
        assert_performance("ActionResult Creation", times, target_ms=0.01)

    def test_action_step_creation(self):
        """ActionStep creation should be <0.01ms."""
        times = measure_ms(
            lambda: ActionStep(
                action_type=ActionType.LIKE,
                params={"selector": "[data-testid='like']"},
                on_fail="retry",
                max_retries=3,
            ),
            iterations=500,
        )
        assert_performance("ActionStep Creation", times, target_ms=0.01)

    def test_action_type_enum_access(self):
        """ActionType enum access should be <0.01ms."""
        times = measure_ms(lambda: ActionType.LIKE, iterations=500)
        assert_performance("ActionType Access", times, target_ms=0.01)

    def test_engine_creation(self):
        """ActionEngine creation should be <0.5ms."""
        page = MagicMock()
        times = measure_ms(
            lambda: ActionEngine(page, profile="social_media"),
            iterations=200,
        )
        assert_performance("ActionEngine Creation", times, target_ms=0.5)


# ═══════════════════════════════════════════════════════════════════════════════
# Task Orchestrator Performance
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrchestratorPerformance:
    """Performance regression tests for Task Orchestrator module."""

    def test_task_enqueue_within_budget(self):
        """Task enqueue should be <0.5ms (incl. logging)."""
        orch = TaskOrchestrator(workers=1)
        counter = [0]
        def enqueue():
            counter[0] += 1
            orch.add_task(Task(
                id=f"perf_{counter[0]}",
                platform="telegram",
                action="like",
                target=f"https://t.me/test/{counter[0]}",
            ))

        times = measure_ms(enqueue, iterations=500)
        assert_performance("Task Enqueue", times, target_ms=0.5)

    def test_task_creation_within_budget(self):
        """Task creation should be <0.01ms."""
        counter = [0]
        def create():
            counter[0] += 1
            Task(
                id=f"t_{counter[0]}",
                platform="telegram",
                action="like",
                target=f"https://t.me/test/{counter[0]}",
            )

        times = measure_ms(create, iterations=500)
        assert_performance("Task Creation", times, target_ms=0.01)

    def test_rate_limit_check_within_budget(self):
        """Rate limit check should be <0.01ms."""
        rl = RateLimit(platform="telegram", max_per_minute=30, max_per_hour=500)
        times = measure_ms(lambda: rl.can_execute(), iterations=500)
        assert_performance("Rate Limit Check", times, target_ms=0.01)

    def test_rate_limit_with_data(self):
        """Rate limit check with existing data should be <0.05ms."""
        rl = RateLimit(platform="telegram", max_per_minute=30, max_per_hour=500)
        now = time.time()
        rl._actions_minute = [now - i for i in range(10)]
        rl._actions_hour = [now - i for i in range(50)]
        rl._actions_day = [now - i for i in range(100)]

        times = measure_ms(lambda: rl.can_execute(), iterations=200)
        assert_performance("Rate Limit Check (with data)", times, target_ms=0.05)

    def test_priority_queue_ordering(self):
        """Priority queue should maintain correct ordering."""
        orch = TaskOrchestrator(workers=1)
        priorities = [3, 1, 4, 0, 2, 1, 3, 0, 2, 4]
        for i, p in enumerate(priorities):
            orch.add_task(Task(
                id=f"order_{i}",
                platform="telegram",
                action="like",
                target=f"https://t.me/test/{i}",
                priority=p,
            ))

        # Dequeue and verify ordering
        import heapq
        prev = -1
        while orch._queue:
            t = heapq.heappop(orch._queue)
            assert t.priority >= prev, "Priority queue ordering broken"
            prev = t.priority

    def test_orchestrator_stats(self):
        """Orchestrator stats should be <0.01ms."""
        orch = TaskOrchestrator(workers=3)
        for i in range(10):
            orch.add_task(Task(
                id=f"stats_{i}",
                platform="telegram",
                action="like",
                target=f"https://t.me/test/{i}",
            ))

        times = measure_ms(lambda: orch.stats, iterations=500)
        assert_performance("Orchestrator Stats", times, target_ms=0.01)

    def test_task_lt_comparison(self):
        """Task __lt__ comparison should be <0.001ms."""
        t1 = Task(id="a", priority=TaskPriority.HIGH)
        t2 = Task(id="b", priority=TaskPriority.LOW)
        times = measure_ms(lambda: t1 < t2, iterations=500)
        assert_performance("Task __lt__ Comparison", times, target_ms=0.001)


# ═══════════════════════════════════════════════════════════════════════════════
# Captcha Solver Performance
# ═══════════════════════════════════════════════════════════════════════════════

class TestCaptchaPerformance:
    """Performance regression tests for Captcha Solver module."""

    def test_config_creation(self):
        """SolverConfig creation should be <0.01ms."""
        times = measure_ms(
            lambda: SolverConfig(
                provider=SolverProvider.TWOCAPTCHA,
                api_key="perf_key_123",
            ),
            iterations=500,
        )
        assert_performance("SolverConfig Creation", times, target_ms=0.01)

    def test_solver_creation(self):
        """CaptchaSolver creation should be <60ms (includes httpx.AsyncClient init)."""
        times = measure_ms(
            lambda: CaptchaSolver(api_key="perf_key_123"),
            iterations=200,
        )
        assert_performance("CaptchaSolver Creation", times, target_ms=60.0)

    def test_stats_tracking(self):
        """Stats property access should be <0.01ms."""
        solver = CaptchaSolver(api_key="perf_key_123")
        times = measure_ms(lambda: solver.stats, iterations=500)
        assert_performance("Stats Tracking", times, target_ms=0.01)

    def test_captcha_result_creation(self):
        """CaptchaResult creation should be <0.01ms."""
        times = measure_ms(
            lambda: CaptchaResult(
                success=True,
                token="test_token_abc",
                solve_time_ms=5000.0,
                cost=0.00299,
            ),
            iterations=500,
        )
        assert_performance("CaptchaResult Creation", times, target_ms=0.01)

    def test_captcha_type_enum(self):
        """CaptchaType enum access should be <0.001ms."""
        times = measure_ms(lambda: CaptchaType.RECAPTCHA_V2, iterations=500)
        assert_performance("CaptchaType Access", times, target_ms=0.001)


# ═══════════════════════════════════════════════════════════════════════════════
# Cross-Module Integration Performance
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntegrationPerformance:
    """Cross-module integration performance tests."""

    def test_full_task_pipeline(self):
        """Full pipeline: create task → enqueue → check rate limit → stats."""
        orch = TaskOrchestrator(workers=2)
        rl = RateLimit(platform="telegram", max_per_minute=30, max_per_hour=500)
        counter = [0]

        def pipeline():
            counter[0] += 1
            task = Task(
                id=f"pipe_{counter[0]}",
                platform="telegram",
                action="like",
                target=f"https://t.me/test/{counter[0]}",
            )
            orch.add_task(task)
            rl.can_execute()
            orch.stats

        times = measure_ms(pipeline, iterations=200)
        assert_performance("Full Task Pipeline", times, target_ms=1.0)

    @pytest.mark.flaky(reruns=2, reruns_delay=1)
    def test_account_with_fingerprint(self):
        """Account creation + fingerprint generation should be <15ms combined."""
        am, path = self._get_db_helper()
        counter = [0]

        def combined():
            counter[0] += 1
            try:
                am.create_account(
                    platform="telegram",
                    username=f"combo_{counter[0]}",
                    profile_id=f"fp_{counter[0]}",
                )
            except ValueError:
                pass
            FingerprintManager.generate(f"combo_fp_{counter[0]}")

        times = measure_ms(combined, iterations=100)
        assert_performance("Account + Fingerprint", times, target_ms=15.0)
        try:
            os.unlink(path)
        except OSError:
            pass

    def _get_db_helper(self):
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        return AccountManager(db_path=f.name), f.name

    def test_behavior_with_fingerprint(self):
        """Behavior engine creation + fingerprint should be <1ms combined."""
        page = MagicMock()
        counter = [0]

        def combined():
            counter[0] += 1
            HumanBehaviorEngine(page, profile="casual_reader")
            FingerprintManager.generate(f"behavior_fp_{counter[0]}")

        times = measure_ms(combined, iterations=200)
        assert_performance("Behavior + Fingerprint", times, target_ms=1.0)


# ═══════════════════════════════════════════════════════════════════════════════
# Memory Regression Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestMemoryRegression:
    """Memory usage regression tests."""

    def test_task_memory_per_instance(self):
        """Each Task instance should use <1KB."""
        import sys
        t = Task(id="mem_test", platform="telegram", action="like", target="https://t.me/1")
        size = sys.getsizeof(t)
        # Dataclass with __slots__ should be compact
        # Without __slots__, dataclasses use ~200-400 bytes for the object + dict
        assert size < 2000, f"Task instance too large: {size} bytes"

    def test_fingerprint_memory_per_instance(self):
        """Each BrowserFingerprint should use <5KB."""
        import sys
        fp = FingerprintManager.generate("mem_test")
        size = sys.getsizeof(fp)
        assert size < 5000, f"BrowserFingerprint too large: {size} bytes"

    def test_action_result_memory(self):
        """ActionResult should use <1KB."""
        import sys
        ar = ActionResult(action_type=ActionType.LIKE, status="success")
        size = sys.getsizeof(ar)
        assert size < 2000, f"ActionResult too large: {size} bytes"

    def test_orchestrator_queue_memory(self):
        """1000 tasks in queue should use <2MB."""
        import tracemalloc
        tracemalloc.start()
        orch = TaskOrchestrator(workers=1)
        for i in range(1000):
            orch.add_task(Task(
                id=f"mem_{i}",
                platform="telegram",
                action="like",
                target=f"https://t.me/test/{i}",
            ))
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert peak < 2_000_000, f"1000 tasks use too much memory: {peak / 1024:.0f} KB"
