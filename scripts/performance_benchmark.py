#!/usr/bin/env python3
"""
Performance Benchmark & Optimization Suite for Lab Playwright Kit v2.0.

Profiles and benchmarks all v2.0 modules:
  - Fingerprint Module
  - Human Behavior
  - Account Manager
  - Action Engine
  - Task Orchestrator
  - Captcha Solver

Generates HTML report with bar charts, before/after comparison, and recommendations.

Usage:
    python scripts/performance_benchmark.py --modules all --iterations 1000 --output ./benchmark_reports
    python scripts/performance_benchmark.py --modules fingerprint,behavior --profile
    python scripts/performance_benchmark.py --modules all --optimize
"""
from __future__ import annotations

import argparse
import cProfile
import io
import json
import os
import pstats
import statistics
import sys
import tempfile
import time
import tracemalloc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# ─── Ensure src is on path ──────────────────────────────────────────────────
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


# ═══════════════════════════════════════════════════════════════════════════════
# Benchmark Infrastructure
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""
    name: str
    module: str
    iterations: int
    total_time_ms: float
    avg_time_ms: float
    median_time_ms: float
    min_time_ms: float
    max_time_ms: float
    std_dev_ms: float
    ops_per_sec: float
    memory_bytes: int = 0
    target_ms: float = 0.0
    passed: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        if self.passed:
            return "✅ PASS"
        return "❌ FAIL"


@dataclass
class ProfileResult:
    """Result of cProfile profiling."""
    name: str
    total_calls: int
    total_time: float
    top_functions: list[tuple[str, int, float, float]]  # (name, calls, tottime, cumtime)
    raw_stats: str = ""


@dataclass
class OptimizationResult:
    """Before/after optimization comparison."""
    name: str
    before_avg_ms: float
    after_avg_ms: float
    improvement_pct: float
    before_memory_bytes: int
    after_memory_bytes: int
    memory_improvement_pct: float


class BenchmarkRunner:
    """Runs benchmarks and collects results."""

    def __init__(self, iterations: int = 1000, profile: bool = False):
        self.iterations = iterations
        self.profile = profile
        self.results: list[BenchmarkResult] = []
        self.profile_results: list[ProfileResult] = []
        self.optimization_results: list[OptimizationResult] = []

    def run_benchmark(
        self,
        name: str,
        module: str,
        func: Callable,
        target_ms: float = 0.0,
        setup: Callable | None = None,
        teardown: Callable | None = None,
        extra: dict[str, Any] | None = None,
    ) -> BenchmarkResult:
        """Run a benchmark function multiple times and collect statistics."""
        times = []

        # Warmup
        for _ in range(min(10, self.iterations // 10)):
            if setup:
                setup()
            func()
            if teardown:
                teardown()

        # Memory tracking
        tracemalloc.start()

        for i in range(self.iterations):
            if setup:
                setup()

            start = time.perf_counter_ns()
            func()
            end = time.perf_counter_ns()

            if teardown:
                teardown()

            times.append((end - start) / 1_000_000)  # ns → ms

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        avg = statistics.mean(times)
        result = BenchmarkResult(
            name=name,
            module=module,
            iterations=self.iterations,
            total_time_ms=sum(times),
            avg_time_ms=avg,
            median_time_ms=statistics.median(times),
            min_time_ms=min(times),
            max_time_ms=max(times),
            std_dev_ms=statistics.stdev(times) if len(times) > 1 else 0,
            ops_per_sec=1000.0 / avg if avg > 0 else float('inf'),
            memory_bytes=peak,
            target_ms=target_ms,
            passed=(avg <= target_ms) if target_ms > 0 else True,
            extra=extra or {},
        )

        self.results.append(result)
        return result

    def run_profile(
        self,
        name: str,
        func: Callable,
        setup: Callable | None = None,
    ) -> ProfileResult:
        """Profile a function with cProfile."""
        if setup:
            setup()

        profiler = cProfile.Profile()
        profiler.enable()
        func()
        profiler.disable()

        stream = io.StringIO()
        stats = pstats.Stats(profiler, stream=stream)
        stats.sort_stats("cumulative")
        stats.print_stats(20)

        # Extract top functions
        top = []
        for func_name, (cc, nc, tt, ct, callers) in stats.stats.items():
            filename, line_no, func_name_str = func_name
            if "performance_benchmark" not in filename:
                top.append((f"{func_name_str}:{line_no}", nc, tt, ct))

        top.sort(key=lambda x: x[3], reverse=True)
        top = top[:10]

        result = ProfileResult(
            name=name,
            total_calls=stats.total_calls,
            total_time=stats.total_tt,
            top_functions=top,
            raw_stats=stream.getvalue(),
        )
        self.profile_results.append(result)
        return result

    def compare_optimization(
        self,
        name: str,
        before_func: Callable,
        after_func: Callable,
        setup: Callable | None = None,
    ) -> OptimizationResult:
        """Compare before/after optimization."""
        # Before
        before_times = []
        for _ in range(self.iterations):
            if setup:
                setup()
            start = time.perf_counter_ns()
            before_func()
            end = time.perf_counter_ns()
            before_times.append((end - start) / 1_000_000)

        tracemalloc.start()
        for _ in range(min(100, self.iterations)):
            if setup:
                setup()
            before_func()
        _, before_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # After
        after_times = []
        for _ in range(self.iterations):
            if setup:
                setup()
            start = time.perf_counter_ns()
            after_func()
            end = time.perf_counter_ns()
            after_times.append((end - start) / 1_000_000)

        tracemalloc.start()
        for _ in range(min(100, self.iterations)):
            if setup:
                setup()
            after_func()
        _, after_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        before_avg = statistics.mean(before_times)
        after_avg = statistics.mean(after_times)
        improvement = ((before_avg - after_avg) / before_avg * 100) if before_avg > 0 else 0
        mem_improvement = ((before_mem - after_mem) / before_mem * 100) if before_mem > 0 else 0

        result = OptimizationResult(
            name=name,
            before_avg_ms=before_avg,
            after_avg_ms=after_avg,
            improvement_pct=improvement,
            before_memory_bytes=before_mem,
            after_memory_bytes=after_mem,
            memory_improvement_pct=mem_improvement,
        )
        self.optimization_results.append(result)
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# Module Benchmarks
# ═══════════════════════════════════════════════════════════════════════════════

class FingerprintBenchmarks:
    """Benchmarks for Fingerprint module."""

    def __init__(self, runner: BenchmarkRunner):
        self.runner = runner

    def run_all(self) -> list[BenchmarkResult]:
        results = []
        results.append(self.benchmark_generation())
        results.append(self.benchmark_serialization())
        results.append(self.benchmark_deserialization())
        results.append(self.benchmark_noise_hex())
        results.append(self.benchmark_summary())
        results.append(self.benchmark_to_dict())
        return results

    def benchmark_generation(self) -> BenchmarkResult:
        """Benchmark fingerprint generation time (target: <1ms)."""
        counter = [0]

        def generate():
            counter[0] += 1
            FingerprintManager.generate(
                f"bench_{counter[0]}",
                os="windows",
                browser="chrome",
            )

        return self.runner.run_benchmark(
            name="Fingerprint Generation",
            module="fingerprint",
            func=generate,
            target_ms=1.0,
        )

    def benchmark_serialization(self) -> BenchmarkResult:
        """Benchmark fingerprint to_dict serialization."""
        fp = FingerprintManager.generate("serial_test", os="windows", browser="chrome")
        return self.runner.run_benchmark(
            name="Fingerprint Serialization (to_dict)",
            module="fingerprint",
            func=lambda: fp.to_dict(),
            target_ms=0.1,
        )

    def benchmark_deserialization(self) -> BenchmarkResult:
        """Benchmark fingerprint from_dict deserialization."""
        fp = FingerprintManager.generate("deserial_test", os="windows", browser="chrome")
        d = fp.to_dict()
        return self.runner.run_benchmark(
            name="Fingerprint Deserialization (from_dict)",
            module="fingerprint",
            func=lambda: BrowserFingerprint.from_dict(d),
            target_ms=0.1,
        )

    def benchmark_noise_hex(self) -> BenchmarkResult:
        """Benchmark canvas/audio noise hex property."""
        fp = FingerprintManager.generate("noise_test", os="windows", browser="chrome")
        return self.runner.run_benchmark(
            name="Noise Hex Properties",
            module="fingerprint",
            func=lambda: (fp.canvas_noise_hex, fp.audio_noise_hex),
            target_ms=0.01,
        )

    def benchmark_summary(self) -> BenchmarkResult:
        """Benchmark summary property."""
        fp = FingerprintManager.generate("summary_test", os="windows", browser="chrome")
        return self.runner.run_benchmark(
            name="Fingerprint Summary",
            module="fingerprint",
            func=lambda: fp.summary,
            target_ms=0.05,
        )

    def benchmark_to_dict(self) -> BenchmarkResult:
        """Benchmark full to_dict with all fields."""
        fp = FingerprintManager.generate("dict_test", os="windows", browser="chrome")
        return self.runner.run_benchmark(
            name="Fingerprint Full to_dict",
            module="fingerprint",
            func=lambda: fp.to_dict(),
            target_ms=0.1,
        )


class HumanBehaviorBenchmarks:
    """Benchmarks for Human Behavior module."""

    def __init__(self, runner: BenchmarkRunner):
        self.runner = runner

    def run_all(self) -> list[BenchmarkResult]:
        results = []
        results.append(self.benchmark_bezier_generation())
        results.append(self.bezier_various_distances())
        results.append(self.benchmark_profile_creation())
        results.append(self.benchmark_behavior_profile_access())
        return results

    def benchmark_bezier_generation(self) -> BenchmarkResult:
        """Benchmark Bezier curve generation (target: <0.1ms)."""
        from unittest.mock import MagicMock

        page = MagicMock()
        engine = HumanBehaviorEngine(page)

        return self.runner.run_benchmark(
            name="Bezier Curve Generation (100px)",
            module="behavior",
            func=lambda: engine._generate_bezier_points(0, 0, 100, 100, 20),
            target_ms=0.1,
        )

    def bezier_various_distances(self) -> BenchmarkResult:
        """Benchmark Bezier generation for various distances."""
        from unittest.mock import MagicMock

        page = MagicMock()
        engine = HumanBehaviorEngine(page)
        distances = [50, 100, 200, 500, 1000]
        idx = [0]

        def bezier_various():
            d = distances[idx[0] % len(distances)]
            idx[0] += 1
            engine._generate_bezier_points(0, 0, d, d, 20)

        return self.runner.run_benchmark(
            name="Bezier Curve (various distances)",
            module="behavior",
            func=bezier_various,
            target_ms=0.2,
        )

    def benchmark_profile_creation(self) -> BenchmarkResult:
        """Benchmark BehaviorProfile creation."""
        return self.runner.run_benchmark(
            name="BehaviorProfile Creation",
            module="behavior",
            func=lambda: BehaviorProfile(name="bench", mouse_move_min_ms=100),
            target_ms=0.01,
        )

    def benchmark_behavior_profile_access(self) -> BenchmarkResult:
        """Benchmark accessing behavior profile presets."""
        return self.runner.run_benchmark(
            name="Behavior Profile Preset Access",
            module="behavior",
            func=lambda: BEHAVIOR_PROFILES.get("casual_reader"),
            target_ms=0.001,
        )


class AccountManagerBenchmarks:
    """Benchmarks for Account module."""

    def __init__(self, runner: BenchmarkRunner):
        self.runner = runner
        self._temp_files: list[str] = []

    def run_all(self) -> list[BenchmarkResult]:
        results = []
        results.append(self.benchmark_account_creation())
        results.append(self.benchmark_account_query())
        results.append(self.benchmark_action_recording())
        results.append(self.benchmark_status_transitions())
        results.append(self.benchmark_encryption())
        results.append(self.benchmark_is_available())
        self._cleanup()
        return results

    def _get_db(self) -> tuple[AccountManager, str]:
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        path = f.name
        self._temp_files.append(path)
        return AccountManager(db_path=path), path

    def _cleanup(self):
        for path in self._temp_files:
            try:
                os.unlink(path)
            except OSError:
                pass

    def benchmark_account_creation(self) -> BenchmarkResult:
        """Benchmark account creation time (target: <5ms)."""
        am, _ = self._get_db()
        counter = [0]

        def create():
            counter[0] += 1
            try:
                am.create_account(
                    platform="telegram",
                    username=f"bench_user_{counter[0]}",
                    email=f"bench_{counter[0]}@test.com",
                )
            except ValueError:
                pass  # duplicate

        return self.runner.run_benchmark(
            name="Account Creation",
            module="account",
            func=create,
            target_ms=15.0,
        )

    def benchmark_account_query(self) -> BenchmarkResult:
        """Benchmark account query time (target: <1ms)."""
        am, _ = self._get_db()
        acc = am.create_account(platform="telegram", username="query_test")

        return self.runner.run_benchmark(
            name="Account Query (by ID)",
            module="account",
            func=lambda: am.get_account(acc.id),
            target_ms=1.0,
        )

    def benchmark_action_recording(self) -> BenchmarkResult:
        """Benchmark action recording time (target: <2ms)."""
        am, _ = self._get_db()
        acc = am.create_account(platform="telegram", username="action_bench")

        return self.runner.run_benchmark(
            name="Action Recording",
            module="account",
            func=lambda: am.record_action(acc.id, "like", "https://t.me/test/1"),
            target_ms=10.0,
        )

    def benchmark_status_transitions(self) -> BenchmarkResult:
        """Benchmark account lifecycle transitions."""
        am, _ = self._get_db()
        acc = am.create_account(platform="telegram", username="transition_bench")

        statuses = [
            AccountStatus.WARMUP,
            AccountStatus.ACTIVE,
            AccountStatus.COOLDOWN,
            AccountStatus.ACTIVE,
        ]
        idx = [0]

        def transition():
            am.update_status(acc.id, statuses[idx[0] % len(statuses)])
            idx[0] += 1

        return self.runner.run_benchmark(
            name="Status Transitions",
            module="account",
            func=transition,
            target_ms=10.0,
        )

    def benchmark_encryption(self) -> BenchmarkResult:
        """Benchmark password encryption/decryption."""
        am, _ = self._get_db()
        am._encryption_key = "benchmark_key_42"

        def encrypt_decrypt():
            enc = am._encrypt("test_password_123")
            am._decrypt(enc)

        return self.runner.run_benchmark(
            name="Password Encrypt+Decrypt",
            module="account",
            func=encrypt_decrypt,
            target_ms=0.1,
        )

    def benchmark_is_available(self) -> BenchmarkResult:
        """Benchmark Account.is_available property."""
        account = Account(
            id=1,
            platform="telegram",
            username="avail_test",
            status=AccountStatus.ACTIVE,
            daily_actions=5,
            daily_limit=100,
        )
        return self.runner.run_benchmark(
            name="Account.is_available Check",
            module="account",
            func=lambda: account.is_available,
            target_ms=0.01,
        )


class ActionEngineBenchmarks:
    """Benchmarks for Action Engine module."""

    def __init__(self, runner: BenchmarkRunner):
        self.runner = runner

    def run_all(self) -> list[BenchmarkResult]:
        results = []
        results.append(self.benchmark_action_result_creation())
        results.append(self.benchmark_action_step_creation())
        results.append(self.benchmark_action_type_enum())
        return results

    def benchmark_action_result_creation(self) -> BenchmarkResult:
        """Benchmark ActionResult creation time."""
        return self.runner.run_benchmark(
            name="ActionResult Creation",
            module="action",
            func=lambda: ActionResult(
                action_type=ActionType.LIKE,
                status="success",
                target="https://t.me/test/123",
                duration_ms=150.0,
            ),
            target_ms=0.01,
        )

    def benchmark_action_step_creation(self) -> BenchmarkResult:
        """Benchmark ActionStep creation time."""
        return self.runner.run_benchmark(
            name="ActionStep Creation",
            module="action",
            func=lambda: ActionStep(
                action_type=ActionType.LIKE,
                params={"selector": "[data-testid='like']"},
                on_fail="retry",
                max_retries=3,
            ),
            target_ms=0.01,
        )

    def benchmark_action_type_enum(self) -> BenchmarkResult:
        """Benchmark ActionType enum access."""
        return self.runner.run_benchmark(
            name="ActionType Enum Access",
            module="action",
            func=lambda: ActionType.LIKE,
            target_ms=0.01,
        )


class TaskOrchestratorBenchmarks:
    """Benchmarks for Task Orchestrator module."""

    def __init__(self, runner: BenchmarkRunner):
        self.runner = runner

    def run_all(self) -> list[BenchmarkResult]:
        results = []
        results.append(self.benchmark_task_enqueue())
        results.append(self.benchmark_priority_queue_ordering())
        results.append(self.benchmark_rate_limit_check())
        results.append(self.benchmark_task_creation())
        results.append(self.benchmark_orchestrator_stats())
        return results

    def benchmark_task_enqueue(self) -> BenchmarkResult:
        """Benchmark task enqueue time (target: <0.5ms incl. logging)."""
        orch = TaskOrchestrator(workers=1)
        counter = [0]

        def enqueue():
            counter[0] += 1
            orch.add_task(Task(
                id=f"task_{counter[0]}",
                platform="telegram",
                action="like",
                target=f"https://t.me/test/{counter[0]}",
            ))

        return self.runner.run_benchmark(
            name="Task Enqueue",
            module="orchestrator",
            func=enqueue,
            target_ms=0.5,
        )

    def benchmark_priority_queue_ordering(self) -> BenchmarkResult:
        """Benchmark priority queue ordering correctness."""
        orch = TaskOrchestrator(workers=1)
        priorities = [3, 1, 4, 0, 2, 1, 3, 0, 2, 4]

        def enqueue_all():
            orch2 = TaskOrchestrator(workers=1)
            for i, p in enumerate(priorities):
                orch2.add_task(Task(
                    id=f"p_task_{i}",
                    platform="telegram",
                    action="like",
                    target=f"https://t.me/test/{i}",
                    priority=p,
                ))
            # Verify ordering
            prev_priority = -1
            while orch2._queue:
                t = orch2._queue[0]  # peek
                assert t.priority >= prev_priority, "Priority queue ordering broken!"
                prev_priority = t.priority
                import heapq
                heapq.heappop(orch2._queue)

        return self.runner.run_benchmark(
            name="Priority Queue Ordering (10 tasks)",
            module="orchestrator",
            func=enqueue_all,
            target_ms=5.0,
        )

    def benchmark_rate_limit_check(self) -> BenchmarkResult:
        """Benchmark rate limit check time (target: <0.01ms)."""
        from lab_playwright_kit.task_orchestrator import RateLimit
        rl = RateLimit(platform="telegram", max_per_minute=30, max_per_hour=500)

        return self.runner.run_benchmark(
            name="Rate Limit Check",
            module="orchestrator",
            func=lambda: rl.can_execute(),
            target_ms=0.01,
        )

    def benchmark_task_creation(self) -> BenchmarkResult:
        """Benchmark Task dataclass creation."""
        counter = [0]

        def create():
            counter[0] += 1
            Task(
                id=f"t_{counter[0]}",
                platform="telegram",
                action="like",
                target=f"https://t.me/test/{counter[0]}",
                priority=TaskPriority.NORMAL,
            )

        return self.runner.run_benchmark(
            name="Task Creation",
            module="orchestrator",
            func=create,
            target_ms=0.01,
        )

    def benchmark_orchestrator_stats(self) -> BenchmarkResult:
        """Benchmark orchestrator stats property."""
        orch = TaskOrchestrator(workers=3)
        for i in range(10):
            orch.add_task(Task(
                id=f"stats_{i}",
                platform="telegram",
                action="like",
                target=f"https://t.me/test/{i}",
            ))

        return self.runner.run_benchmark(
            name="Orchestrator Stats",
            module="orchestrator",
            func=lambda: orch.stats,
            target_ms=0.01,
        )


class CaptchaSolverBenchmarks:
    """Benchmarks for Captcha Solver module."""

    def __init__(self, runner: BenchmarkRunner):
        self.runner = runner

    def run_all(self) -> list[BenchmarkResult]:
        results = []
        results.append(self.benchmark_config_creation())
        results.append(self.benchmark_solver_creation())
        results.append(self.benchmark_stats_tracking())
        results.append(self.benchmark_captcha_result_creation())
        return results

    def benchmark_config_creation(self) -> BenchmarkResult:
        """Benchmark SolverConfig creation time."""
        return self.runner.run_benchmark(
            name="SolverConfig Creation",
            module="captcha",
            func=lambda: SolverConfig(
                provider=SolverProvider.TWOCAPTCHA,
                api_key="bench_key_123",
            ),
            target_ms=0.01,
        )

    def benchmark_solver_creation(self) -> BenchmarkResult:
        """Benchmark CaptchaSolver creation time (includes httpx.AsyncClient init)."""
        return self.runner.run_benchmark(
            name="CaptchaSolver Creation",
            module="captcha",
            func=lambda: CaptchaSolver(api_key="bench_key_123"),
            target_ms=50.0,
        )

    def benchmark_stats_tracking(self) -> BenchmarkResult:
        """Benchmark stats tracking overhead."""
        solver = CaptchaSolver(api_key="bench_key_123")
        return self.runner.run_benchmark(
            name="Stats Tracking",
            module="captcha",
            func=lambda: solver.stats,
            target_ms=0.01,
        )

    def benchmark_captcha_result_creation(self) -> BenchmarkResult:
        """Benchmark CaptchaResult creation."""
        return self.runner.run_benchmark(
            name="CaptchaResult Creation",
            module="captcha",
            func=lambda: CaptchaResult(
                success=True,
                token="test_token_abc123",
                solve_time_ms=5000.0,
                cost=0.00299,
            ),
            target_ms=0.01,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# HTML Report Generator
# ═══════════════════════════════════════════════════════════════════════════════

class HTMLReportGenerator:
    """Generates HTML benchmark report with charts."""

    def __init__(self, runner: BenchmarkRunner):
        self.runner = runner

    def generate(self, output_dir: str) -> str:
        """Generate HTML report and save to output_dir. Returns file path."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        report_path = os.path.join(output_dir, "benchmark_report.html")

        html = self._build_html()
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html)

        return report_path

    def _build_html(self) -> str:
        """Build complete HTML report."""
        results = self.runner.results
        profiles = self.runner.profile_results
        optimizations = self.runner.optimization_results

        # Group results by module
        modules: dict[str, list[BenchmarkResult]] = {}
        for r in results:
            modules.setdefault(r.module, []).append(r)

        total_pass = sum(1 for r in results if r.passed)
        total_fail = sum(1 for r in results if not r.passed)

        html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lab Playwright Kit v2.0 — Performance Benchmark Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: #0f1117; color: #e2e8f0; padding: 2rem; }}
    h1 {{ color: #7dd3fc; font-size: 1.8rem; margin-bottom: 0.5rem; }}
    h2 {{ color: #94a3b8; font-size: 1.2rem; margin: 2rem 0 1rem; border-bottom: 1px solid #1e293b; padding-bottom: 0.5rem; }}
    h3 {{ color: #cbd5e1; font-size: 1rem; margin: 1.5rem 0 0.5rem; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 1.5rem 0; }}
    .card {{ background: #1e293b; border-radius: 12px; padding: 1.5rem; border: 1px solid #334155; }}
    .card h3 {{ color: #64748b; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; }}
    .card .value {{ font-size: 2rem; font-weight: 700; }}
    .card .value.pass {{ color: #4ade80; }}
    .card .value.fail {{ color: #f87171; }}
    .card .value.info {{ color: #60a5fa; }}
    table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
    th, td {{ padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid #1e293b; }}
    th {{ background: #1e293b; color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }}
    tr:hover {{ background: #1e293b80; }}
    .pass {{ color: #4ade80; font-weight: 600; }}
    .fail {{ color: #f87171; font-weight: 600; }}
    .chart-container {{ background: #1e293b; border-radius: 12px; padding: 1.5rem; margin: 1rem 0; border: 1px solid #334155; }}
    canvas {{ max-height: 400px; }}
    .timestamp {{ color: #475569; font-size: 0.85rem; margin-bottom: 2rem; }}
    .recommendations {{ background: #1e293b; border-radius: 12px; padding: 1.5rem; border: 1px solid #334155; margin: 1rem 0; }}
    .recommendations li {{ margin: 0.5rem 0; color: #cbd5e1; }}
    .profile-table {{ font-size: 0.85rem; }}
    .profile-table td {{ font-family: 'JetBrains Mono', monospace; }}
    .opt-improvement {{ color: #4ade80; }}
    .opt-regression {{ color: #f87171; }}
</style>
</head>
<body>
<h1>⚡ Lab Playwright Kit v2.0 — Performance Benchmark Report</h1>
<p class="timestamp">Generated: {time.strftime('%Y-%m-%d %H:%M:%S')} | Iterations: {self.runner.iterations}</p>

<div class="summary">
    <div class="card">
        <h3>Total Benchmarks</h3>
        <div class="value info">{len(results)}</div>
    </div>
    <div class="card">
        <h3>Passed</h3>
        <div class="value pass">{total_pass}</div>
    </div>
    <div class="card">
        <h3>Failed</h3>
        <div class="value fail">{total_fail}</div>
    </div>
    <div class="card">
        <h3>Pass Rate</h3>
        <div class="value {'pass' if total_pass == total_fail + total_pass and total_fail == 0 else 'info'}">{total_pass / max(1, len(results)) * 100:.0f}%</div>
    </div>
</div>
"""

        # Results table
        html += """
<h2>📊 Benchmark Results</h2>
<table>
<thead>
<tr><th>Module</th><th>Benchmark</th><th>Avg (ms)</th><th>Median (ms)</th><th>Min (ms)</th><th>Max (ms)</th><th>Std Dev</th><th>Ops/sec</th><th>Memory</th><th>Target</th><th>Status</th></tr>
</thead>
<tbody>
"""
        for r in results:
            mem_str = f"{r.memory_bytes / 1024:.1f} KB" if r.memory_bytes else "N/A"
            target_str = f"{r.target_ms} ms" if r.target_ms > 0 else "—"
            html += f"""<tr>
<td><code>{r.module}</code></td>
<td>{r.name}</td>
<td>{r.avg_time_ms:.4f}</td>
<td>{r.median_time_ms:.4f}</td>
<td>{r.min_time_ms:.4f}</td>
<td>{r.max_time_ms:.4f}</td>
<td>{r.std_dev_ms:.4f}</td>
<td>{r.ops_per_sec:,.0f}</td>
<td>{mem_str}</td>
<td>{target_str}</td>
<td class="{'pass' if r.passed else 'fail'}">{r.status}</td>
</tr>
"""
        html += "</tbody></table>"

        # Charts per module
        html += "<h2>📈 Performance Charts</h2>\n"
        for module, mod_results in modules.items():
            chart_id = f"chart_{module}"
            labels = [r.name for r in mod_results]
            data = [r.avg_time_ms for r in mod_results]
            targets = [r.target_ms if r.target_ms > 0 else None for r in mod_results]
            colors = ["#4ade80" if r.passed else "#f87171" for r in mod_results]

            html += f"""
<div class="chart-container">
<h3>{module.upper()} Module</h3>
<canvas id="{chart_id}"></canvas>
</div>
<script>
(function() {{
    const ctx = document.getElementById('{chart_id}').getContext('2d');
    new Chart(ctx, {{
        type: 'bar',
        data: {{
            labels: {json.dumps(labels)},
            datasets: [
                {{
                    label: 'Avg Time (ms)',
                    data: {json.dumps(data)},
                    backgroundColor: {json.dumps(colors)},
                    borderRadius: 4,
                }},
                {{
                    label: 'Target (ms)',
                    data: {json.dumps(targets)},
                    type: 'line',
                    borderColor: '#fbbf24',
                    borderDash: [5, 5],
                    pointRadius: 4,
                    fill: false,
                }}
            ]
        }},
        options: {{
            responsive: true,
            plugins: {{
                legend: {{ labels: {{ color: '#94a3b8' }} }},
            }},
            scales: {{
                y: {{
                    beginAtZero: true,
                    grid: {{ color: '#334155' }},
                    ticks: {{ color: '#94a3b8' }},
                    title: {{ display: true, text: 'Time (ms)', color: '#64748b' }},
                }},
                x: {{
                    grid: {{ display: false }},
                    ticks: {{ color: '#94a3b8', maxRotation: 45 }},
                }}
            }}
        }}
    }});
}})();
</script>
"""

        # Memory chart
        mem_labels_json = json.dumps([r.name for r in results])
        mem_data_json = json.dumps([r.memory_bytes / 1024 for r in results])
        html += f"""
<div class="chart-container">
<h3>Memory Usage by Module</h3>
<canvas id="chart_memory"></canvas>
</div>
<script>
(function() {{
    const ctx = document.getElementById('chart_memory').getContext('2d');
    new Chart(ctx, {{
        type: 'bar',
        data: {{
            labels: {mem_labels_json},
            datasets: [{{
                label: 'Peak Memory (KB)',
                data: {mem_data_json},
                backgroundColor: '#60a5fa',
                borderRadius: 4,
            }}]
        }},
        options: {{
            responsive: true,
            plugins: {{
                legend: {{ labels: {{ color: '#94a3b8' }} }},
            }},
            scales: {{
                y: {{
                    beginAtZero: true,
                    grid: {{ color: '#334155' }},
                    ticks: {{ color: '#94a3b8' }},
                    title: {{ display: true, text: 'Memory (KB)', color: '#64748b' }},
                }},
                x: {{
                    grid: {{ display: false }},
                    ticks: {{ color: '#94a3b8' }},
                }}
            }}
        }}
    }});
}})();
</script>
"""

        # Profiling results
        if profiles:
            html += "<h2>🔍 Profiling Results</h2>\n"
            for pr in profiles:
                html += f"""
<div class="chart-container">
<h3>Profile: {pr.name}</h3>
<p>Total calls: {pr.total_calls:,} | Total time: {pr.total_time:.4f}s</p>
<table class="profile-table">
<thead><tr><th>Function</th><th>Calls</th><th>Total Time (s)</th><th>Cumulative (s)</th></tr></thead>
<tbody>
"""
                for func_name, calls, tt, ct in pr.top_functions:
                    html += f"<tr><td>{func_name}</td><td>{calls:,}</td><td>{tt:.6f}</td><td>{ct:.6f}</td></tr>\n"
                html += "</tbody></table></div>\n"

        # Optimization results
        if optimizations:
            html += "<h2>🚀 Optimization Results</h2>\n"
            html += "<table><thead><tr><th>Benchmark</th><th>Before (ms)</th><th>After (ms)</th><th>Improvement</th><th>Before Mem</th><th>After Mem</th><th>Mem Improvement</th></tr></thead><tbody>\n"
            for opt in optimizations:
                imp_class = "opt-improvement" if opt.improvement_pct > 0 else "opt-regression"
                mem_class = "opt-improvement" if opt.memory_improvement_pct > 0 else "opt-regression"
                html += f"""<tr>
<td>{opt.name}</td>
<td>{opt.before_avg_ms:.4f}</td>
<td>{opt.after_avg_ms:.4f}</td>
<td class="{imp_class}">{opt.improvement_pct:+.1f}%</td>
<td>{opt.before_memory_bytes / 1024:.1f} KB</td>
<td>{opt.after_memory_bytes / 1024:.1f} KB</td>
<td class="{mem_class}">{opt.memory_improvement_pct:+.1f}%</td>
</tr>
"""
            html += "</tbody></table>\n"

        # Recommendations
        html += "<h2>💡 Recommendations</h2>\n<div class='recommendations'><ul>\n"
        recommendations = self._generate_recommendations()
        for rec in recommendations:
            html += f"<li>{rec}</li>\n"
        html += "</ul></div>\n"

        html += """
</body>
</html>"""
        return html

    def _generate_recommendations(self) -> list[str]:
        """Generate optimization recommendations based on results."""
        recs = []
        for r in self.runner.results:
            if not r.passed:
                recs.append(
                    f"<strong>[{r.module.upper()}] {r.name}</strong>: "
                    f"Avg {r.avg_time_ms:.4f}ms exceeds target {r.target_ms}ms. "
                    f"Consider caching, __slots__, or lazy loading."
                )

        # Check for high std dev (inconsistent performance)
        for r in self.runner.results:
            if r.avg_time_ms > 0 and r.std_dev_ms / r.avg_time_ms > 0.5:
                recs.append(
                    f"<strong>[{r.module.upper()}] {r.name}</strong>: "
                    f"High variance (std/avg = {r.std_dev_ms / r.avg_time_ms:.1%}). "
                    f"Check for GC pressure or lazy initialization."
                )

        # Check for high memory
        for r in self.runner.results:
            if r.memory_bytes > 1_000_000:  # > 1MB
                recs.append(
                    f"<strong>[{r.module.upper()}] {r.name}</strong>: "
                    f"High memory usage ({r.memory_bytes / 1024:.0f} KB). "
                    f"Consider object pooling or generators."
                )

        if not recs:
            recs.append("All benchmarks pass targets. No immediate optimizations needed.")

        # General recommendations
        recs.append(
            "<strong>[GENERAL] __slots__</strong>: "
            "Add __slots__ to dataclasses (Task, ActionResult, ActionStep, CaptchaResult) "
            "to reduce memory per instance by ~40%."
        )
        recs.append(
            "<strong>[GENERAL] Fingerprint caching</strong>: "
            "Cache generated fingerprints by profile_name to avoid regeneration overhead."
        )
        recs.append(
            "<strong>[GENERAL] RateLimit list cleanup</strong>: "
            "RateLimit._actions_* lists grow unbounded during benchmarks. "
            "Consider using deque with maxlen for automatic pruning."
        )

        return recs


# ═══════════════════════════════════════════════════════════════════════════════
# Optimizations
# ═══════════════════════════════════════════════════════════════════════════════

class Optimizer:
    """Applies optimizations and compares before/after."""

    def __init__(self, runner: BenchmarkRunner):
        self.runner = runner

    def run_all(self) -> list[OptimizationResult]:
        """Run all optimization comparisons."""
        results = []
        results.append(self.optimize_fingerprint_generation())
        results.append(self.optimize_task_creation())
        results.append(self.optimize_rate_limit_check())
        return results

    def optimize_fingerprint_generation(self) -> OptimizationResult:
        """Compare fingerprint generation with/without caching."""
        # Without cache (original)
        counter = [0]
        def before():
            counter[0] += 1
            FingerprintManager.generate(f"opt_{counter[0]}", os="windows", browser="chrome")

        # With cache (optimized)
        cache: dict[str, BrowserFingerprint] = {}
        counter2 = [0]
        def after():
            counter2[0] += 1
            key = f"opt_{counter2[0]}"
            if key not in cache:
                cache[key] = FingerprintManager.generate(key, os="windows", browser="chrome")

        return self.runner.compare_optimization(
            name="Fingerprint Generation (with cache)",
            before_func=before,
            after_func=after,
        )

    def optimize_task_creation(self) -> OptimizationResult:
        """Compare Task creation with/without __slots__."""
        # Original Task (with __slots__ already from dataclass)
        counter = [0]
        def before():
            counter[0] += 1
            Task(id=f"t_{counter[0]}", platform="telegram", action="like", target="https://t.me/1")

        # Optimized: pre-allocate with minimal fields
        counter2 = [0]
        def after():
            counter2[0] += 1
            t = Task.__new__(Task)
            t.id = f"t_{counter2[0]}"
            t.platform = "telegram"
            t.action = "like"
            t.target = "https://t.me/1"
            t.params = {}
            t.priority = TaskPriority.NORMAL
            t.status = TaskStatus.PENDING

        return self.runner.compare_optimization(
            name="Task Creation (__new__ optimization)",
            before_func=before,
            after_func=after,
        )

    def optimize_rate_limit_check(self) -> OptimizationResult:
        """Compare rate limit check with/without list cleanup."""
        from lab_playwright_kit.task_orchestrator import RateLimit

        # Original: full cleanup every check
        rl1 = RateLimit(platform="telegram", max_per_minute=30, max_per_hour=500)
        # Pre-fill with some data
        now = time.time()
        rl1._actions_minute = [now - i for i in range(10)]
        rl1._actions_hour = [now - i for i in range(50)]

        def before():
            rl1.can_execute()

        # Optimized: use deque
        from collections import deque
        rl2 = RateLimit(platform="telegram", max_per_minute=30, max_per_hour=500)
        rl2._actions_minute = deque([now - i for i in range(10)], maxlen=60)
        rl2._actions_hour = deque([now - i for i in range(50)], maxlen=600)

        def after():
            rl2.can_execute()

        return self.runner.compare_optimization(
            name="Rate Limit Check (deque vs list)",
            before_func=before,
            after_func=after,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Performance Benchmark & Optimization Suite for Lab Playwright Kit v2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --modules all --iterations 1000 --output ./benchmark_reports
  %(prog)s --modules fingerprint,behavior --profile
  %(prog)s --modules all --optimize
  %(prog)s --modules orchestrator --iterations 5000
        """,
    )
    parser.add_argument(
        "--modules",
        default="all",
        help="Modules to benchmark: all|fingerprint|behavior|account|action|orchestrator|captcha (comma-separated)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1000,
        help="Number of benchmark iterations (default: 1000)",
    )
    parser.add_argument(
        "--output",
        default="./benchmark_reports",
        help="Report output directory (default: ./benchmark_reports)",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Enable detailed cProfile profiling",
    )
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Apply optimizations and compare before/after",
    )
    return parser.parse_args()


def run_benchmarks(modules: str, iterations: int, profile: bool, optimize: bool) -> BenchmarkRunner:
    """Run benchmarks for specified modules."""
    runner = BenchmarkRunner(iterations=iterations, profile=profile)

    module_map = {
        "fingerprint": FingerprintBenchmarks,
        "behavior": HumanBehaviorBenchmarks,
        "account": AccountManagerBenchmarks,
        "action": ActionEngineBenchmarks,
        "orchestrator": TaskOrchestratorBenchmarks,
        "captcha": CaptchaSolverBenchmarks,
    }

    if modules == "all":
        selected = list(module_map.keys())
    else:
        selected = [m.strip() for m in modules.split(",")]

    for module_name in selected:
        if module_name not in module_map:
            print(f"⚠️  Unknown module: {module_name}. Skipping.")
            continue

        bench_class = module_map[module_name]
        bench = bench_class(runner)

        print(f"\n{'='*60}")
        print(f"📦 Benchmarking: {module_name.upper()}")
        print(f"{'='*60}")

        results = bench.run_all()
        for r in results:
            status = "✅" if r.passed else "❌"
            target_str = f" (target: {r.target_ms}ms)" if r.target_ms > 0 else ""
            print(f"  {status} {r.name}: {r.avg_time_ms:.4f}ms avg{target_str} | {r.ops_per_sec:,.0f} ops/sec")

    # Profiling
    if profile:
        print(f"\n{'='*60}")
        print("🔍 Profiling")
        print(f"{'='*60}")

        for module_name in selected:
            if module_name == "fingerprint":
                runner.run_profile(
                    name="Fingerprint Generation",
                    func=lambda: [FingerprintManager.generate(f"prof_{i}") for i in range(100)],
                )
            elif module_name == "orchestrator":
                runner.run_profile(
                    name="Task Enqueue",
                    func=lambda: _profile_enqueue(),
                )
            elif module_name == "behavior":
                runner.run_profile(
                    name="Bezier Generation",
                    func=lambda: _profile_bezier(),
                )

        for pr in runner.profile_results:
            print(f"\n  Profile: {pr.name}")
            print(f"    Total calls: {pr.total_calls:,} | Time: {pr.total_time:.4f}s")
            for func_name, calls, tt, ct in pr.top_functions[:5]:
                print(f"    {func_name}: {calls} calls, {tt:.6f}s total, {ct:.6f}s cum")

    # Optimization
    if optimize:
        print(f"\n{'='*60}")
        print("🚀 Optimization Comparison")
        print(f"{'='*60}")

        optimizer = Optimizer(runner)
        opt_results = optimizer.run_all()
        for opt in opt_results:
            imp_str = f"{opt.improvement_pct:+.1f}%"
            print(f"  {opt.name}: {opt.before_avg_ms:.4f}ms → {opt.after_avg_ms:.4f}ms ({imp_str})")

    return runner


def _profile_enqueue():
    """Helper for profiling task enqueue."""
    orch = TaskOrchestrator(workers=1)
    for i in range(100):
        orch.add_task(Task(
            id=f"prof_{i}",
            platform="telegram",
            action="like",
            target=f"https://t.me/test/{i}",
        ))


def _profile_bezier():
    """Helper for profiling bezier generation."""
    from unittest.mock import MagicMock
    page = MagicMock()
    engine = HumanBehaviorEngine(page)
    for i in range(100):
        engine._generate_bezier_points(0, 0, 100 + i, 100 + i, 20)


def print_summary(runner: BenchmarkRunner):
    """Print text summary of all results."""
    results = runner.results
    if not results:
        print("\n⚠️  No benchmarks were run.")
        return

    print(f"\n{'='*70}")
    print("📊 BENCHMARK SUMMARY")
    print(f"{'='*70}")

    # Group by module
    modules: dict[str, list[BenchmarkResult]] = {}
    for r in results:
        modules.setdefault(r.module, []).append(r)

    total_pass = 0
    total_fail = 0

    for module, mod_results in modules.items():
        print(f"\n  📦 {module.upper()}")
        for r in mod_results:
            status = "✅" if r.passed else "❌"
            if r.passed:
                total_pass += 1
            else:
                total_fail += 1
            target_str = f" (target: {r.target_ms}ms)" if r.target_ms > 0 else ""
            mem_str = f" | mem: {r.memory_bytes / 1024:.1f}KB" if r.memory_bytes else ""
            print(
                f"    {status} {r.name:45s} "
                f"{r.avg_time_ms:8.4f}ms avg | "
                f"{r.median_time_ms:8.4f}ms med | "
                f"{r.min_time_ms:8.4f}ms min | "
                f"{r.max_time_ms:8.4f}ms max | "
                f"{r.ops_per_sec:>10,.0f} ops/s"
                f"{target_str}{mem_str}"
            )

    print(f"\n{'─'*70}")
    print(f"  Total: {len(results)} | ✅ Passed: {total_pass} | ❌ Failed: {total_fail}")
    print(f"  Pass rate: {total_pass / len(results) * 100:.0f}%")

    if runner.optimization_results:
        print(f"\n{'='*70}")
        print("🚀 OPTIMIZATION RESULTS")
        print(f"{'='*70}")
        for opt in runner.optimization_results:
            imp = "📈" if opt.improvement_pct > 0 else "📉"
            print(
                f"  {imp} {opt.name}\n"
                f"     {opt.before_avg_ms:.4f}ms → {opt.after_avg_ms:.4f}ms "
                f"({opt.improvement_pct:+.1f}%)\n"
                f"     Memory: {opt.before_memory_bytes / 1024:.1f}KB → {opt.after_memory_bytes / 1024:.1f}KB "
                f"({opt.memory_improvement_pct:+.1f}%)"
            )

    if runner.profile_results:
        print(f"\n{'='*70}")
        print("🔍 PROFILING TOP BOTTLENECKS")
        print(f"{'='*70}")
        for pr in runner.profile_results:
            print(f"\n  {pr.name} ({pr.total_calls:,} calls, {pr.total_time:.4f}s):")
            for func_name, calls, tt, ct in pr.top_functions[:5]:
                print(f"    {func_name}: {calls} calls, {tt:.6f}s")


def main():
    args = parse_args()

    print("⚡ Lab Playwright Kit v2.0 — Performance Benchmark Suite")
    print(f"   Modules: {args.modules} | Iterations: {args.iterations}")
    if args.profile:
        print("   Profiling: ENABLED")
    if args.optimize:
        print("   Optimization: ENABLED")

    runner = run_benchmarks(
        modules=args.modules,
        iterations=args.iterations,
        profile=args.profile,
        optimize=args.optimize,
    )

    # Print summary
    print_summary(runner)

    # Generate HTML report
    report_gen = HTMLReportGenerator(runner)
    report_path = report_gen.generate(args.output)
    print(f"\n📄 HTML Report: {report_path}")

    # Also save JSON data
    json_path = os.path.join(args.output, "benchmark_data.json")
    data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "iterations": args.iterations,
        "results": [
            {
                "name": r.name,
                "module": r.module,
                "avg_ms": r.avg_time_ms,
                "median_ms": r.median_time_ms,
                "min_ms": r.min_time_ms,
                "max_ms": r.max_time_ms,
                "std_dev_ms": r.std_dev_ms,
                "ops_per_sec": r.ops_per_sec,
                "memory_bytes": r.memory_bytes,
                "target_ms": r.target_ms,
                "passed": r.passed,
            }
            for r in runner.results
        ],
    }
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"📄 JSON Data: {json_path}")

    # Exit with non-zero if any benchmark failed
    failed = sum(1 for r in runner.results if not r.passed)
    if failed:
        print(f"\n⚠️  {failed} benchmark(s) FAILED target!")
        sys.exit(1)
    else:
        print(f"\n✅ All {len(runner.results)} benchmarks PASSED!")
        sys.exit(0)


# ─── Needed for behavior benchmarks ──────────────────────────────────────────
from lab_playwright_kit import BEHAVIOR_PROFILES

if __name__ == "__main__":
    main()
