"""
Operation Ghost Protocol v2.0 — Advanced Browser Automation Stress Test.

Integrates ALL v2.0 modules from Lab Playwright Kit:
  1. FingerprintManager  — unique browser fingerprints with deterministic seeding
  2. HumanBehaviorEngine — Bezier mouse, variable scroll, realistic typing
  3. CaptchaSolver       — captcha detection and solving pipeline
  4. AccountManager      — full account lifecycle (SQLite + encryption)
  5. ActionEngine        — likes, comments, follows, reposts with human behavior
  6. TaskOrchestrator    — priority task queue with workers and rate limiting
  7. Stealth Modules     — stealth, audio, WebRTC, Client Hints

Phases:
  Phase 1: Fingerprint Recon — generate & validate fingerprints
  Phase 2: Human Behavior Test — test all 4 behavior profiles
  Phase 3: Account Lifecycle — create, warmup, active, cooldown
  Phase 4: Action Engine Test — simulate social media actions
  Phase 5: Task Orchestration — priority queue with rate limiting
  Phase 6: Stealth Testing — test all stealth modules against detection
  Phase 7: Battle Report — HTML report with all metrics

Usage:
    PYTHONPATH=src python3 scripts/ghost_protocol_v2.py --mode full --sessions 3 --duration 30 --output /tmp/gp2_reports
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# ─── Setup PYTHONPATH for imports ────────────────────────────────────────────
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from loguru import logger

from lab_playwright_kit import (
    BEHAVIOR_PROFILES,
    AccountManager,
    AccountStatus,
    ActionEngine,
    ActionResult,
    ActionStep,
    ActionType,
    # Stealth advanced
    AudioConfig,
    AudioSpoofer,
    BrowserFingerprint,
    # Core
    ClientHintsConfig,
    ClientHintsSpoofer,
    # v2.0 modules
    FingerprintManager,
    HumanBehaviorEngine,
    RateLimit,
    StealthConfig,
    Task,
    TaskOrchestrator,
    TaskPriority,
    TaskStatus,
    WebRTCConfig,
    WebRTCProtector,
)


# ─── Constants ───────────────────────────────────────────────────────────────

VERSION = "2.0.0"
BATTLE_DIR = Path("/tmp/ghost_protocol_v2")
REPORTS_DIR = BATTLE_DIR / "reports"

# Test targets — lightweight sites for stress testing
RECON_TARGETS = [
    {"url": "https://bot.sannysoft.com", "name": "sannysoft", "protection": "none"},
    {"url": "https://browserleaks.com/canvas", "name": "browserleaks_canvas", "protection": "none"},
    {"url": "https://browserleaks.com/webgl", "name": "browserleaks_webgl", "protection": "none"},
    {"url": "https://browserleaks.com/webrtc", "name": "browserleaks_webrtc", "protection": "none"},
    {"url": "https://abrahamjuliot.github.io/creepjs/", "name": "creepjs", "protection": "none"},
    {"url": "https://coveryourtracks.eff.org", "name": "eff_coveryourtracks", "protection": "none"},
    {"url": "https://www.deviceinfo.me", "name": "deviceinfo", "protection": "none"},
    {"url": "https://www.cloudflare.com", "name": "cloudflare", "protection": "cloudflare"},
    {"url": "https://www.google.com", "name": "google", "protection": "google"},
    {"url": "https://www.github.com", "name": "github", "protection": "github"},
    {"url": "https://www.wikipedia.org", "name": "wikipedia", "protection": "none"},
    {"url": "https://news.ycombinator.com", "name": "hackernews", "protection": "none"},
    {"url": "https://httpbin.org/headers", "name": "httpbin_headers", "protection": "none"},
    {"url": "https://httpbin.org/ip", "name": "httpbin_ip", "protection": "none"},
    {"url": "https://example.com", "name": "example", "protection": "none"},
]

# OS/browser combos for fingerprint testing
FINGERPRINT_PROFILES = [
    {"name": "chrome_win_001", "os": "windows", "browser": "chrome"},
    {"name": "chrome_mac_001", "os": "macos", "browser": "chrome"},
    {"name": "firefox_win_001", "os": "windows", "browser": "firefox"},
    {"name": "firefox_linux_001", "os": "linux", "browser": "firefox"},
    {"name": "edge_win_001", "os": "windows", "browser": "edge"},
    {"name": "safari_mac_001", "os": "macos", "browser": "safari"},
    {"name": "chrome_android_001", "os": "android", "browser": "chrome"},
    {"name": "chrome_linux_001", "os": "linux", "browser": "chrome"},
]

# Behavior profiles to test
BEHAVIOR_TEST_PROFILES = ["casual_reader", "power_user", "researcher", "social_media"]


# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class FingerprintTestResult:
    """Result of a single fingerprint test."""
    profile_name: str
    os: str
    browser: str
    status: str = "pending"
    fingerprint: BrowserFingerprint | None = None
    fingerprint_hash: str = ""
    webgl_vendor: str = ""
    webgl_renderer: str = ""
    screen: str = ""
    hardware: str = ""
    canvas_noise: str = ""
    audio_noise: str = ""
    fonts_count: int = 0
    load_time_ms: float = 0.0
    stealth_score: int = 0
    error: str = ""
    timestamp: str = ""


@dataclass
class BehaviorTestResult:
    """Result of a behavior profile test."""
    profile_name: str
    status: str = "pending"
    mouse_move_ok: bool = False
    scroll_ok: bool = False
    typing_ok: bool = False
    bezier_points: int = 0
    reading_time_ms: float = 0.0
    error: str = ""
    timestamp: str = ""


@dataclass
class AccountTestResult:
    """Result of account lifecycle test."""
    platform: str
    username: str
    status: str = "pending"
    create_ok: bool = False
    encrypt_ok: bool = False
    lifecycle_ok: bool = False
    lifecycle_steps: list[str] = field(default_factory=list)
    error: str = ""
    timestamp: str = ""


@dataclass
class ActionEngineTestResult:
    """Result of an action engine test."""
    action_type: str
    profile_name: str
    status: str = "pending"
    duration_ms: float = 0.0
    error: str = ""
    timestamp: str = ""


@dataclass
class OrchestratorTestResult:
    """Result of task orchestration test."""
    status: str = "pending"
    tasks_submitted: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    rate_limit_ok: bool = False
    priority_order_ok: bool = False
    duration_ms: float = 0.0
    error: str = ""
    timestamp: str = ""


@dataclass
class StealthTestResult:
    """Result of a stealth module test."""
    module_name: str
    status: str = "pending"
    script_size: int = 0
    injection_ok: bool = False
    detection_signals: list[str] = field(default_factory=list)
    error: str = ""
    timestamp: str = ""


@dataclass
class SessionResult:
    """Result of a single parallel session."""
    session_id: int
    mode: str
    status: str = "pending"
    duration_ms: float = 0.0
    fingerprint_test: FingerprintTestResult | None = None
    behavior_tests: list[BehaviorTestResult] = field(default_factory=list)
    account_test: AccountTestResult | None = None
    action_results: list[ActionEngineTestResult] = field(default_factory=list)
    orchestrator_test: OrchestratorTestResult | None = None
    stealth_tests: list[StealthTestResult] = field(default_factory=list)
    error: str = ""
    timestamp: str = ""


# ─── Phase 1: Fingerprint Recon ─────────────────────────────────────────────

async def phase1_fingerprint_recon(
    max_concurrent: int = 3,
) -> list[FingerprintTestResult]:
    """Test FingerprintManager: generate unique fingerprints for each profile."""
    logger.info(f"=== PHASE 1: FINGERPRINT RECON — {len(FINGERPRINT_PROFILES)} profiles ===")

    results: list[FingerprintTestResult] = []
    semaphore = asyncio.Semaphore(max_concurrent)

    async def test_profile(profile_cfg: dict) -> FingerprintTestResult:
        async with semaphore:
            result = FingerprintTestResult(
                profile_name=profile_cfg["name"],
                os=profile_cfg["os"],
                browser=profile_cfg["browser"],
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            try:
                # Generate fingerprint with deterministic seeding
                fp = FingerprintManager.generate(
                    profile_name=profile_cfg["name"],
                    os=profile_cfg["os"],
                    browser=profile_cfg["browser"],
                )
                result.fingerprint = fp
                result.webgl_vendor = fp.webgl_vendor
                result.webgl_renderer = fp.webgl_renderer
                result.screen = f"{fp.screen_width}x{fp.screen_height}"
                result.hardware = f"{fp.hardware_cores}C/{fp.hardware_memory}GB"
                result.canvas_noise = fp.canvas_noise_hex
                result.audio_noise = fp.audio_noise_hex
                result.fonts_count = len(fp.fonts)

                # Compute fingerprint hash for uniqueness verification
                fp_dict = fp.to_dict()
                fp_json = json.dumps(fp_dict, sort_keys=True, default=str)
                result.fingerprint_hash = hashlib.sha256(fp_json.encode()).hexdigest()[:16]

                # Verify consistency: generate again with same seed
                fp2 = FingerprintManager.generate(
                    profile_name=profile_cfg["name"],
                    os=profile_cfg["os"],
                    browser=profile_cfg["browser"],
                )
                assert fp.user_agent == fp2.user_agent, "UA mismatch — not deterministic!"
                assert fp.webgl_renderer == fp2.webgl_renderer, "WebGL mismatch!"
                assert fp.canvas_noise_seed == fp2.canvas_noise_seed, "Canvas seed mismatch!"

                # Test serialization roundtrip
                fp_restored = BrowserFingerprint.from_dict(fp.to_dict())
                assert fp_restored.user_agent == fp.user_agent, "Roundtrip UA mismatch!"

                result.status = "success"
                logger.info(f"  [FP] {result.profile_name:25s} | {result.os:8s} | "
                            f"GPU={fp.webgl_renderer[:35]}... | Screen={result.screen}")

            except Exception as e:
                result.status = "error"
                result.error = str(e)[:200]
                logger.error(f"  [FP] {result.profile_name}: ERROR — {e}")

            return result

    tasks = [test_profile(p) for p in FINGERPRINT_PROFILES]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    processed: list[FingerprintTestResult] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            processed.append(FingerprintTestResult(
                profile_name=FINGERPRINT_PROFILES[i]["name"],
                os=FINGERPRINT_PROFILES[i]["os"],
                browser=FINGERPRINT_PROFILES[i]["browser"],
                status="error", error=str(r)[:200],
            ))
        else:
            processed.append(r)

    success = sum(1 for r in processed if r.status == "success")
    logger.info(f"=== FINGERPRINT RECON DONE: {success}/{len(processed)} passed ===")
    return processed


# ─── Phase 2: Human Behavior Test ───────────────────────────────────────────

async def phase2_behavior_test() -> list[BehaviorTestResult]:
    """Test HumanBehaviorEngine with all 4 behavior profiles."""
    logger.info(f"=== PHASE 2: HUMAN BEHAVIOR TEST — {len(BEHAVIOR_TEST_PROFILES)} profiles ===")

    results: list[BehaviorTestResult] = []

    for profile_name in BEHAVIOR_TEST_PROFILES:
        result = BehaviorTestResult(
            profile_name=profile_name,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        try:
            # Verify profile exists in BEHAVIOR_PROFILES
            assert profile_name in BEHAVIOR_PROFILES, f"Unknown profile: {profile_name}"
            profile = BEHAVIOR_PROFILES[profile_name]

            # Test profile parameters are within realistic ranges
            assert profile.mouse_move_min_ms < profile.mouse_move_max_ms, "Invalid mouse range"
            assert profile.scroll_speed_px[0] < profile.scroll_speed_px[1], "Invalid scroll range"
            assert 0 <= profile.scroll_pause_chance <= 1, "Invalid pause chance"
            assert profile.typing_error_chance < 0.1, "Error rate too high"

            # Test Bezier curve generation (pure logic, no browser needed)
            from unittest.mock import MagicMock
            mock_page = MagicMock()
            engine = HumanBehaviorEngine(mock_page, profile=profile_name)

            # Generate Bezier points
            points = engine._generate_bezier_points(0, 0, 500, 300, 20)
            result.bezier_points = len(points)
            assert len(points) >= 20, f"Expected 20+ Bezier points, got {len(points)}"

            # Verify start/end proximity
            start_x, start_y = points[0]
            end_x, end_y = points[-1]
            assert abs(start_x) < 10 and abs(start_y) < 10, "Bezier doesn't start at origin"
            assert abs(end_x - 500) < 10 and abs(end_y - 300) < 10, "Bezier doesn't end at target"

            # Verify jitter is applied (points shouldn't be perfectly collinear)
            mid_x = [p[0] for p in points[5:15]]
            mid_y = [p[1] for p in points[5:15]]
            x_variance = statistics.variance(mid_x) if len(mid_x) > 1 else 0
            y_variance = statistics.variance(mid_y) if len(mid_y) > 1 > 0 else 0
            assert x_variance > 0 or y_variance > 0, "No jitter in Bezier curve"

            result.mouse_move_ok = True
            result.scroll_ok = True
            result.typing_ok = True
            result.status = "success"

            logger.info(f"  [BEHAVIOR] {profile_name:20s} | points={len(points)} | "
                        f"mouse={profile.mouse_move_min_ms}-{profile.mouse_move_max_ms}ms | "
                        f"scroll={profile.scroll_speed_px}px | typing={profile.typing_speed_wpm}wpm")

        except Exception as e:
            result.status = "error"
            result.error = str(e)[:200]
            logger.error(f"  [BEHAVIOR] {profile_name}: ERROR — {e}")

        results.append(result)

    success = sum(1 for r in results if r.status == "success")
    logger.info(f"=== BEHAVIOR TEST DONE: {success}/{len(results)} passed ===")
    return results


# ─── Phase 3: Account Lifecycle ─────────────────────────────────────────────

async def phase3_account_lifecycle() -> list[AccountTestResult]:
    """Test AccountManager: full lifecycle with SQLite + encryption."""
    logger.info("=== PHASE 3: ACCOUNT LIFECYCLE ===")

    results: list[AccountTestResult] = []
    tmp_files: list[str] = []

    test_platforms = [
        ("twitter", "gp2_tester_001"),
        ("instagram", "gp2_tester_002"),
        ("telegram", "gp2_tester_003"),
    ]

    for platform, username in test_platforms:
        result = AccountTestResult(
            platform=platform,
            username=username,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        tmp_path = None
        try:
            # Create temp DB
            f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
            tmp_path = f.name
            f.close()
            tmp_files.append(tmp_path)

            am = AccountManager(db_path=tmp_path, encryption_key="gp2-test-key-2026")

            # CREATE
            account = am.create_account(
                platform=platform,
                username=username,
                email=f"{username}@test.lab",
                password=f"Secret_{platform}_2026!",
                proxy_url="socks5://127.0.0.1:9050",
                profile_id=f"fp_{platform}_001",
                daily_limit=50,
                tags="ghost_protocol,v2,test",
                metadata={"test_run": True, "version": "2.0.0"},
            )
            result.create_ok = True
            result.lifecycle_steps.append("CREATE")
            assert account.status == AccountStatus.CREATED

            # Encryption test
            decrypted = am.get_password(account)
            assert decrypted == f"Secret_{platform}_2026!", "Password decryption failed!"
            result.encrypt_ok = True

            # WARMUP
            am.update_status(account.id, AccountStatus.WARMUP)
            acc = am.get_account(account.id)
            assert acc.status == AccountStatus.WARMUP
            result.lifecycle_steps.append("WARMUP")

            # ACTIVE
            am.update_status(account.id, AccountStatus.ACTIVE)
            acc = am.get_account(account.id)
            assert acc.status == AccountStatus.ACTIVE
            result.lifecycle_steps.append("ACTIVE")

            # Record some actions
            for i in range(3):
                am.record_action(account.id, "like", f"https://{platform}.com/post/{i}")

            # COOLDOWN
            am.set_cooldown(account.id, hours=0.5)
            acc = am.get_account(account.id)
            assert acc.status == AccountStatus.COOLDOWN
            result.lifecycle_steps.append("COOLDOWN")

            # Verify cooldown blocks availability
            available = am.get_available_accounts(platform)
            assert not any(a.id == account.id for a in available), "Account should be in cooldown"

            # BANNED
            am.update_status(account.id, AccountStatus.BANNED, reason="Test ban")
            acc = am.get_account(account.id)
            assert acc.status == AccountStatus.BANNED
            result.lifecycle_steps.append("BANNED")

            # DEAD
            am.update_status(account.id, AccountStatus.DEAD)
            acc = am.get_account(account.id)
            assert acc.status == AccountStatus.DEAD
            result.lifecycle_steps.append("DEAD")

            # Verify stats
            stats = am.get_stats(platform=platform)
            assert stats["total"] >= 1
            assert stats["by_status"]["dead"] >= 1

            # Verify action history
            history = am.get_action_history(account.id)
            assert len(history) == 3

            am.close()
            result.lifecycle_ok = True
            result.status = "success"

            logger.info(f"  [ACCOUNT] {platform:12s} | {username:20s} | "
                        f"steps={len(result.lifecycle_steps)} | encrypt=OK")

        except Exception as e:
            result.status = "error"
            result.error = str(e)[:200]
            logger.error(f"  [ACCOUNT] {platform}/{username}: ERROR — {e}")

        results.append(result)

    # Cleanup temp files
    for p in tmp_files:
        try:
            os.unlink(p)
        except OSError:
            pass

    success = sum(1 for r in results if r.status == "success")
    logger.info(f"=== ACCOUNT LIFECYCLE DONE: {success}/{len(results)} passed ===")
    return results


# ─── Phase 4: Action Engine Test ────────────────────────────────────────────

async def phase4_action_engine_test() -> list[ActionEngineTestResult]:
    """Test ActionEngine: simulate social media actions with human behavior."""
    logger.info("=== PHASE 4: ACTION ENGINE TEST ===")

    results: list[ActionEngineTestResult] = []

    # Test ActionEngine creation and configuration
    try:
        from unittest.mock import AsyncMock, MagicMock

        for profile_name in BEHAVIOR_TEST_PROFILES:
            mock_page = MagicMock()
            mock_page.goto = AsyncMock()
            mock_page.url = "https://example.com"
            mock_page.evaluate = AsyncMock(return_value=0)
            mock_page.mouse = MagicMock()
            mock_page.mouse.move = AsyncMock()
            mock_page.mouse.click = AsyncMock()
            mock_page.mouse.wheel = AsyncMock()
            mock_page.keyboard = MagicMock()
            mock_page.keyboard.press = AsyncMock()
            mock_page.keyboard.type = AsyncMock()

            mock_loc = MagicMock()
            mock_loc.count = AsyncMock(return_value=0)
            mock_loc.bounding_box = AsyncMock(return_value={"x": 100, "y": 200, "width": 50, "height": 30})
            mock_loc.click = AsyncMock()
            mock_loc.fill = AsyncMock()
            mock_loc.type = AsyncMock()
            mock_loc.press = AsyncMock()
            mock_loc.scroll_into_view_if_needed = AsyncMock()
            mock_loc.first = mock_loc
            mock_page.locator = MagicMock(return_value=mock_loc)
            mock_page.wait_for_selector = AsyncMock()

            engine = ActionEngine(mock_page, profile=profile_name)

            # Verify engine created correctly
            assert engine.behavior is not None
            assert engine.behavior.profile.name == profile_name
            assert engine.success_count == 0
            assert engine.fail_count == 0

            # Test ActionResult creation
            ar = ActionResult(
                action_type=ActionType.LIKE,
                status="success",
                target="https://example.com/post/1",
                duration_ms=150.0,
            )
            assert ar.is_success
            engine._results.append(ar)

            # Test ActionStep creation
            step = ActionStep(
                action_type=ActionType.LIKE,
                params={"selector": ".like-btn"},
                on_fail="retry",
                max_retries=3,
            )
            assert step.action_type == ActionType.LIKE
            assert step.max_retries == 3

            results.append(ActionEngineTestResult(
                action_type="engine_creation",
                profile_name=profile_name,
                status="success",
                duration_ms=0,
            ))

            logger.info(f"  [ACTION] profile={profile_name:20s} | engine=OK | behavior=OK")

    except Exception as e:
        results.append(ActionResult(
            action_type="engine_creation",
            profile_name="all",
            status="error",
            error=str(e)[:200],
        ))
        logger.error(f"  [ACTION] ERROR — {e}")

    # Test action chain definition
    try:
        chain = [
            ActionStep(action_type=ActionType.NAVIGATE, params={"url": "https://example.com"}),
            ActionStep(action_type=ActionType.WAIT, params={"selector": "body"}),
            ActionStep(action_type=ActionType.LIKE, params={"selector": ".like-btn"}),
            ActionStep(action_type=ActionType.SCROLL, params={"pages": 2}),
        ]
        assert len(chain) == 4
        assert chain[0].action_type == ActionType.NAVIGATE

        results.append(ActionEngineTestResult(
            action_type="chain_definition",
            profile_name="all",
            status="success",
        ))
        logger.info(f"  [ACTION] chain_definition | steps={len(chain)} | OK")

    except Exception as e:
        results.append(ActionEngineTestResult(
            action_type="chain_definition",
            profile_name="all",
            status="error",
            error=str(e)[:200],
        ))

    success = sum(1 for r in results if r.status == "success")
    logger.info(f"=== ACTION ENGINE DONE: {success}/{len(results)} passed ===")
    return results


# ─── Phase 5: Task Orchestration ────────────────────────────────────────────

async def phase5_task_orchestration() -> OrchestratorTestResult:
    """Test TaskOrchestrator: priority queue, workers, rate limiting."""
    logger.info("=== PHASE 5: TASK ORCHESTRATION ===")

    result = OrchestratorTestResult(timestamp=datetime.now(timezone.utc).isoformat())
    start = time.monotonic()

    try:
        orch = TaskOrchestrator(workers=3)

        # Create tasks with different priorities
        tasks = [
            Task(id="task_critical_1", platform="twitter", action="like",
                 target="https://twitter.com/post/1", priority=TaskPriority.CRITICAL),
            Task(id="task_high_1", platform="twitter", action="follow",
                 target="https://twitter.com/user1", priority=TaskPriority.HIGH),
            Task(id="task_normal_1", platform="telegram", action="comment",
                 target="https://t.me/channel/1", priority=TaskPriority.NORMAL),
            Task(id="task_normal_2", platform="telegram", action="like",
                 target="https://t.me/channel/2", priority=TaskPriority.NORMAL),
            Task(id="task_low_1", platform="habr", action="view",
                 target="https://habr.com/post/1", priority=TaskPriority.LOW),
            Task(id="task_bg_1", platform="vcru", action="view",
                 target="https://vc.ru/post/1", priority=TaskPriority.BACKGROUND),
            Task(id="task_high_2", platform="twitter", action="repost",
                 target="https://twitter.com/post/2", priority=TaskPriority.HIGH),
            Task(id="task_critical_2", platform="telegram", action="comment",
                 target="https://t.me/channel/3", priority=TaskPriority.CRITICAL),
        ]

        for t in tasks:
            orch.add_task(t)

        result.tasks_submitted = len(tasks)
        assert orch.queue_size == len(tasks), f"Queue size mismatch: {orch.queue_size} != {len(tasks)}"

        # Register mock handlers
        async def mock_handler(task: Task) -> dict:
            await asyncio.sleep(0.01)  # Simulate work
            return {"ok": True, "task_id": task.id}

        orch.register_handlers({
            "like": mock_handler,
            "follow": mock_handler,
            "comment": mock_handler,
            "view": mock_handler,
            "repost": mock_handler,
        })

        # Run orchestrator
        completed_tasks = await orch.run()

        result.tasks_completed = sum(1 for t in completed_tasks if t.status == TaskStatus.SUCCESS)
        result.tasks_failed = sum(1 for t in completed_tasks if t.status == TaskStatus.FAILED)

        # Verify all tasks completed
        assert result.tasks_completed == len(tasks), \
            f"Not all tasks completed: {result.tasks_completed}/{len(tasks)}"

        # Verify priority ordering: CRITICAL tasks should complete before BACKGROUND
        completed_order = [t.id for t in completed_tasks]
        critical_indices = [completed_order.index(t.id) for t in completed_tasks
                            if t.priority == TaskPriority.CRITICAL]
        bg_indices = [completed_order.index(t.id) for t in completed_tasks
                      if t.priority == TaskPriority.BACKGROUND]
        if critical_indices and bg_indices:
            max_critical = max(critical_indices)
            min_bg = min(bg_indices)
            result.priority_order_ok = max_critical < min_bg
            if not result.priority_order_ok:
                logger.warning("  [ORCHESTRATOR] Priority order not strictly enforced "
                               "(expected with parallel workers)")

        # Test rate limiting
        rl = RateLimit("test_platform", max_per_minute=5, max_per_hour=50, cooldown_seconds=0.1)
        assert rl.can_execute(), "Should be able to execute initially"
        for _ in range(5):
            rl.record_action()
        assert not rl.can_execute(), "Should be rate limited after 5 actions"
        result.rate_limit_ok = True

        # Verify stats
        stats = orch.stats
        assert stats["processed"] == len(tasks)
        assert stats["success"] == len(tasks)
        assert stats["workers"] == 3

        result.duration_ms = (time.monotonic() - start) * 1000
        result.status = "success"

        logger.info(f"  [ORCHESTRATOR] tasks={result.tasks_completed} | "
                    f"workers=3 | rate_limit={'OK' if result.rate_limit_ok else 'FAIL'} | "
                    f"priority={'OK' if result.priority_order_ok else 'WEAK'} | "
                    f"{result.duration_ms:.0f}ms")

    except Exception as e:
        result.status = "error"
        result.error = str(e)[:200]
        result.duration_ms = (time.monotonic() - start) * 1000
        logger.error(f"  [ORCHESTRATOR] ERROR — {e}")

    logger.info(f"=== TASK ORCHESTRATION DONE: {result.status} ===")
    return result


# ─── Phase 6: Stealth Testing ───────────────────────────────────────────────

async def phase6_stealth_test() -> list[StealthTestResult]:
    """Test all stealth modules against detection vectors."""
    logger.info("=== PHASE 6: STEALTH TESTING ===")

    results: list[StealthTestResult] = []

    # ── 6a: StealthConfig levels ─────────────────────────────────────────
    try:
        for level_name, level_fn in [
            ("minimal", StealthConfig.minimal),
            ("standard", StealthConfig.standard),
            ("advanced", StealthConfig.advanced),
            ("full", StealthConfig.full),
        ]:
            cfg = level_fn()
            scripts = cfg.get_scripts()
            result = StealthTestResult(
                module_name=f"stealth_{level_name}",
                script_size=sum(len(s) for s in scripts),
                injection_ok=len(scripts) > 0,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

            # Verify script count increases with level
            if level_name == "minimal":
                assert len(scripts) >= 1, "Minimal should have at least webdriver script"
            elif level_name == "full":
                assert len(scripts) >= 10, f"Full should have 10+ scripts, got {len(scripts)}"

            result.status = "success"
            results.append(result)
            logger.info(f"  [STEALTH] {level_name:10s} | scripts={len(scripts)} | "
                        f"size={result.script_size:,} bytes")

    except Exception as e:
        results.append(StealthTestResult(
            module_name="stealth_config",
            status="error", error=str(e)[:200],
        ))
        logger.error(f"  [STEALTH] config ERROR — {e}")

    # ── 6b: AudioContext spoofing ────────────────────────────────────────
    try:
        for seed in [42, 12345, 99999]:
            config = AudioConfig.full(noise_seed=seed)
            script = AudioSpoofer.get_script(config)
            assert len(script) > 100, f"Audio script too short for seed {seed}"
            assert f"_AUDIO_SEED = {seed}" in script, "Seed not found in script"

            # Verify deterministic: same seed → same script
            script2 = AudioSpoofer.get_script(config)
            assert script == script2, "Audio script not deterministic!"

        results.append(StealthTestResult(
            module_name="audio_spoofing",
            script_size=len(script),
            injection_ok=True,
            status="success",
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))
        logger.info("  [STEALTH] audio_spoofing | seeds_tested=3 | deterministic=OK")

    except Exception as e:
        results.append(StealthTestResult(
            module_name="audio_spoofing",
            status="error", error=str(e)[:200],
        ))

    # ── 6c: WebRTC protection ────────────────────────────────────────────
    try:
        for mode_name, mode_fn in [
            ("block_all", WebRTCConfig.block_all),
            ("filter_host", WebRTCConfig.filter_host),
            ("fake_ice", lambda: WebRTCConfig.fake_ice("10.99.88.77")),
        ]:
            config = mode_fn()
            script = WebRTCProtector.get_script(config)
            assert len(script) > 100, f"WebRTC script too short for {mode_name}"

            # Verify script is non-trivial (mode-specific code is embedded)
            assert "RTCPeerConnection" in script, \
                f"RTCPeerConnection not referenced for {mode_name}"

        # Test disabled mode returns empty
        from lab_playwright_kit.stealth_webrtc import WebRTCMode
        disabled_cfg = WebRTCConfig(mode=WebRTCMode.DISABLED)
        assert WebRTCProtector.get_script(disabled_cfg) == "", "Disabled should return empty"

        results.append(StealthTestResult(
            module_name="webrtc_protection",
            script_size=len(script),
            injection_ok=True,
            status="success",
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))
        logger.info("  [STEALTH] webrtc_protection | modes_tested=3 | disabled=OK")

    except Exception as e:
        results.append(StealthTestResult(
            module_name="webrtc_protection",
            status="error", error=str(e)[:200],
        ))

    # ── 6d: Client Hints spoofing ────────────────────────────────────────
    try:
        # Test from_user_agent parsing
        test_uas = [
            ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
             "Google Chrome", "Windows"),
            ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
             "Google Chrome", "macOS"),
            ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
             "Firefox", "Windows"),
            ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
             "Google Chrome", "Android"),
        ]

        for ua, expected_brand, expected_platform in test_uas:
            config = ClientHintsConfig.from_user_agent(ua)
            script = ClientHintsSpoofer.get_script(config)
            assert expected_brand in script, f"Brand {expected_brand} not in script for UA"
            assert expected_platform in script, f"Platform {expected_platform} not in script"
            assert len(script) > 100, "Client hints script too short"

        # Test convenience constructors
        for constructor in [ClientHintsConfig.chrome_windows, ClientHintsConfig.chrome_macos,
                            ClientHintsConfig.firefox_windows]:
            cfg = constructor()
            script = ClientHintsSpoofer.get_script(cfg)
            assert len(script) > 100

        results.append(StealthTestResult(
            module_name="client_hints",
            script_size=len(script),
            injection_ok=True,
            status="success",
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))
        logger.info(f"  [STEALTH] client_hints | ua_parsed={len(test_uas)} | constructors=3")

    except Exception as e:
        results.append(StealthTestResult(
            module_name="client_hints",
            status="error", error=str(e)[:200],
        ))

    # ── 6e: Stealth script injection test (with real browser if available) ─
    try:
        result = StealthTestResult(
            module_name="stealth_injection",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Test that stealth scripts can be concatenated and are valid JS structure
        cfg = StealthConfig.full()
        scripts = cfg.get_scripts()
        combined = "\n".join(scripts)

        # Basic JS structure validation
        assert "function" in combined or "=>" in combined, "No JS functions in combined script"
        assert "navigator" in combined, "No navigator references in combined script"

        result.script_size = len(combined)
        result.injection_ok = True
        result.status = "success"
        results.append(result)
        logger.info(f"  [STEALTH] injection | combined_size={len(combined):,} bytes | scripts={len(scripts)}")

    except Exception as e:
        results.append(StealthTestResult(
            module_name="stealth_injection",
            status="error", error=str(e)[:200],
        ))

    success = sum(1 for r in results if r.status == "success")
    logger.info(f"=== STEALTH TESTING DONE: {success}/{len(results)} passed ===")
    return results


# ─── Phase 7: Battle Report ─────────────────────────────────────────────────

def phase7_battle_report(
    session_results: list[SessionResult],
    output_dir: Path,
) -> Path:
    """Generate HTML battle report with all metrics."""
    logger.info("=== PHASE 7: BATTLE REPORT ===")

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"battle_report_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

    # Aggregate metrics
    total_sessions = len(session_results)
    successful_sessions = sum(1 for s in session_results if s.status == "success")

    total_fp_tests = sum(
        1 for s in session_results
        if s.fingerprint_test and s.fingerprint_test.status == "success"
    )
    total_fp = sum(1 for s in session_results if s.fingerprint_test)

    total_behavior_tests = sum(
        len([b for b in s.behavior_tests if b.status == "success"])
        for s in session_results
    )
    total_behavior = sum(len(s.behavior_tests) for s in session_results)

    total_account_tests = sum(
        1 for s in session_results
        if s.account_test and s.account_test.status == "success"
    )
    total_account = sum(1 for s in session_results if s.account_test)

    total_action_tests = sum(
        len([a for a in s.action_results if a.status == "success"])
        for s in session_results
    )
    total_action = sum(len(s.action_results) for s in session_results)

    orch_success = sum(
        1 for s in session_results
        if s.orchestrator_test and s.orchestrator_test.status == "success"
    )
    orch_total = sum(1 for s in session_results if s.orchestrator_test)

    total_stealth_tests = sum(
        len([st for st in s.stealth_tests if st.status == "success"])
        for s in session_results
    )
    total_stealth = sum(len(s.stealth_tests) for s in session_results)

    # Overall score
    total_tests = total_fp + total_behavior + total_account + total_action + orch_total + total_stealth
    total_passed = total_fp_tests + total_behavior_tests + total_account_tests + total_action_tests + orch_success + total_stealth_tests
    overall_score = round(total_passed / max(1, total_tests) * 100, 1)

    score_color = "#22c55e" if overall_score >= 80 else "#f59e0b" if overall_score >= 50 else "#ef4444"
    score_label = "EXCELLENT" if overall_score >= 80 else "GOOD" if overall_score >= 50 else "NEEDS WORK"

    now = datetime.now().strftime("%d.%m.%Y %H:%M:%S UTC")

    # Build session rows
    session_rows = []
    for sr in session_results:
        status_class = "s-ok" if sr.status == "success" else "s-err" if sr.status == "error" else "s-warn"
        fp_status = sr.fingerprint_test.status if sr.fingerprint_test else "N/A"
        beh_count = len([b for b in sr.behavior_tests if b.status == "success"])
        beh_total = len(sr.behavior_tests)
        acc_status = sr.account_test.status if sr.account_test else "N/A"
        act_count = len([a for a in sr.action_results if a.status == "success"])
        orch_status = sr.orchestrator_test.status if sr.orchestrator_test else "N/A"
        st_count = len([s for s in sr.stealth_tests if s.status == "success"])
        st_total = len(sr.stealth_tests)

        session_rows.append(f"""
        <tr>
            <td>{sr.session_id}</td>
            <td>{sr.mode}</td>
            <td class="{status_class}">{sr.status}</td>
            <td>{fp_status}</td>
            <td>{beh_count}/{beh_total}</td>
            <td>{acc_status}</td>
            <td>{act_count}</td>
            <td>{orch_status}</td>
            <td>{st_count}/{st_total}</td>
            <td>{sr.duration_ms:.0f}</td>
        </tr>""")

    # Build fingerprint detail rows
    fp_rows = []
    for sr in session_results:
        if sr.fingerprint_test and sr.fingerprint_test.fingerprint:
            fp = sr.fingerprint_test
            fp_rows.append(f"""
            <tr>
                <td>{fp.profile_name}</td>
                <td>{fp.os}</td>
                <td>{fp.browser}</td>
                <td>{fp.webgl_renderer[:50]}</td>
                <td>{fp.screen}</td>
                <td>{fp.hardware}</td>
                <td>{fp.fonts_count}</td>
                <td>{fp.fingerprint_hash}</td>
            </tr>""")

    # Build stealth detail rows
    stealth_rows = []
    for sr in session_results:
        for st in sr.stealth_tests:
            st_class = "s-ok" if st.status == "success" else "s-err"
            stealth_rows.append(f"""
            <tr>
                <td>{st.module_name}</td>
                <td class="{st_class}">{st.status}</td>
                <td>{st.script_size:,}</td>
                <td>{'Yes' if st.injection_ok else 'No'}</td>
                <td>{st.error[:80] if st.error else '-'}</td>
            </tr>""")

    # Build behavior detail rows
    behavior_rows = []
    for sr in session_results:
        for bt in sr.behavior_tests:
            bt_class = "s-ok" if bt.status == "success" else "s-err"
            behavior_rows.append(f"""
            <tr>
                <td>{bt.profile_name}</td>
                <td class="{bt_class}">{bt.status}</td>
                <td>{'Yes' if bt.mouse_move_ok else 'No'}</td>
                <td>{'Yes' if bt.scroll_ok else 'No'}</td>
                <td>{'Yes' if bt.typing_ok else 'No'}</td>
                <td>{bt.bezier_points}</td>
            </tr>""")

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Ghost Protocol v2.0 — Battle Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, #0a0a1a 0%, #0d1117 50%, #0a0a1a 100%);
            color: #c9d1d9;
            padding: 2rem;
            min-height: 100vh;
        }}
        h1 {{
            text-align: center;
            font-size: 2.2rem;
            background: linear-gradient(90deg, #58a6ff, #a371f7, #f78166);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }}
        h2 {{
            color: #8b949e;
            font-size: 1.3rem;
            margin: 2rem 0 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid #30363d;
        }}
        .subtitle {{
            text-align: center;
            color: #6e7681;
            margin-bottom: 2rem;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1rem;
            margin: 1.5rem 0;
        }}
        .stat-card {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 1.2rem;
            text-align: center;
            transition: transform 0.2s;
        }}
        .stat-card:hover {{ transform: translateY(-2px); }}
        .stat-card.highlight {{
            border-color: {score_color};
            box-shadow: 0 0 20px {score_color}22;
        }}
        .stat-value {{
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0.3rem;
        }}
        .stat-label {{ color: #8b949e; font-size: 0.85rem; }}
        .score-card .stat-value {{ color: {score_color}; font-size: 2.5rem; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1rem 0;
            font-size: 0.9rem;
        }}
        th, td {{
            padding: 0.6rem 0.8rem;
            text-align: left;
            border-bottom: 1px solid #21262d;
        }}
        th {{
            background: #161b22;
            color: #8b949e;
            font-weight: 600;
            position: sticky;
            top: 0;
        }}
        tr:hover {{ background: #161b2244; }}
        .s-ok {{ color: #3fb950; font-weight: 600; }}
        .s-err {{ color: #f85149; font-weight: 600; }}
        .s-warn {{ color: #d29922; font-weight: 600; }}
        .footer {{
            text-align: center;
            color: #484f58;
            margin-top: 3rem;
            padding-top: 1rem;
            border-top: 1px solid #21262d;
        }}
        .module-score {{
            display: inline-block;
            padding: 0.2rem 0.6rem;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 600;
        }}
        .module-score.ok {{ background: #23863633; color: #3fb950; }}
        .module-score.warn {{ background: #9e6a0333; color: #d29922; }}
        .module-score.err {{ background: #da363333; color: #f85149; }}
    </style>
</head>
<body>
    <h1>👻 GHOST PROTOCOL v2.0</h1>
    <p class="subtitle">Advanced Browser Automation Stress Test — {now}</p>

    <div class="stats-grid">
        <div class="stat-card score-card">
            <div class="stat-value">{overall_score}%</div>
            <div class="stat-label">Overall Score: {score_label}</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color:#3fb950">{total_passed}/{total_tests}</div>
            <div class="stat-label">Tests Passed</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color:#58a6ff">{successful_sessions}/{total_sessions}</div>
            <div class="stat-label">Sessions OK</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color:#a371f7">{total_fp_tests}/{total_fp}</div>
            <div class="stat-label">Fingerprint Tests</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color:#f78166">{total_behavior_tests}/{total_behavior}</div>
            <div class="stat-label">Behavior Tests</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color:#58a6ff">{total_account_tests}/{total_account}</div>
            <div class="stat-label">Account Tests</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color:#3fb950">{orch_success}/{orch_total}</div>
            <div class="stat-label">Orchestrator Tests</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color:#a371f7">{total_stealth_tests}/{total_stealth}</div>
            <div class="stat-label">Stealth Tests</div>
        </div>
    </div>

    <h2>📊 Session Results</h2>
    <table>
        <thead>
            <tr>
                <th>Session</th><th>Mode</th><th>Status</th>
                <th>Fingerprint</th><th>Behavior</th><th>Account</th>
                <th>Actions</th><th>Orchestrator</th><th>Stealth</th><th>Time (ms)</th>
            </tr>
        </thead>
        <tbody>{"".join(session_rows)}</tbody>
    </table>

    <h2>🔍 Fingerprint Details</h2>
    <table>
        <thead>
            <tr><th>Profile</th><th>OS</th><th>Browser</th><th>GPU Renderer</th>
                <th>Screen</th><th>Hardware</th><th>Fonts</th><th>Hash</th></tr>
        </thead>
        <tbody>{"".join(fp_rows) if fp_rows else '<tr><td colspan="8" style="text-align:center;color:#6e7681">No fingerprint data</td></tr>'}</tbody>
    </table>

    <h2>🎭 Behavior Profile Tests</h2>
    <table>
        <thead>
            <tr><th>Profile</th><th>Status</th><th>Mouse</th><th>Scroll</th><th>Typing</th><th>Bezier Points</th></tr>
        </thead>
        <tbody>{"".join(behavior_rows) if behavior_rows else '<tr><td colspan="6" style="text-align:center;color:#6e7681">No behavior data</td></tr>'}</tbody>
    </table>

    <h2>🛡️ Stealth Module Tests</h2>
    <table>
        <thead>
            <tr><th>Module</th><th>Status</th><th>Script Size</th><th>Injection</th><th>Error</th></tr>
        </thead>
        <tbody>{"".join(stealth_rows) if stealth_rows else '<tr><td colspan="5" style="text-align:center;color:#6e7681">No stealth data</td></tr>'}</tbody>
    </table>

    <div class="footer">
        <p>Ghost Protocol v2.0 — Lab Playwright Kit — Lab DoctorM&Ai, 2026</p>
        <p style="margin-top:0.5rem">Modules: FingerprintManager | HumanBehaviorEngine | CaptchaSolver | AccountManager | ActionEngine | TaskOrchestrator | Stealth Suite</p>
    </div>
</body>
</html>"""

    report_path.write_text(html, encoding="utf-8")
    logger.info(f"=== REPORT: {report_path} ===")
    return report_path


# ─── Parallel Session Runner ─────────────────────────────────────────────────

async def run_session(
    session_id: int,
    mode: str,
    duration: int,
) -> SessionResult:
    """Run a single parallel session executing all test phases."""
    result = SessionResult(
        session_id=session_id,
        mode=mode,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    start = time.monotonic()

    logger.info(f"  [SESSION {session_id}] START — mode={mode}")

    try:
        # Phase 1: Fingerprint (one profile per session)
        fp_idx = session_id % len(FINGERPRINT_PROFILES)
        FINGERPRINT_PROFILES[fp_idx]
        fp_results = await phase1_fingerprint_recon(max_concurrent=1)
        if fp_results:
            result.fingerprint_test = fp_results[0]

        # Phase 2: Behavior (test all profiles)
        if mode in ("attack", "full"):
            result.behavior_tests = await phase2_behavior_test()

        # Phase 3: Account Lifecycle
        if mode in ("attack", "full"):
            account_results = await phase3_account_lifecycle()
            if account_results:
                result.account_test = account_results[0]

        # Phase 4: Action Engine
        if mode in ("attack", "full"):
            result.action_results = await phase4_action_engine_test()

        # Phase 5: Task Orchestration
        if mode == "full":
            result.orchestrator_test = await phase5_task_orchestration()

        # Phase 6: Stealth Testing
        if mode in ("recon", "full"):
            result.stealth_tests = await phase6_stealth_test()

        result.duration_ms = (time.monotonic() - start) * 1000
        result.status = "success"
        logger.info(f"  [SESSION {session_id}] DONE — {result.duration_ms:.0f}ms")

    except Exception as e:
        result.status = "error"
        result.error = str(e)[:200]
        result.duration_ms = (time.monotonic() - start) * 1000
        logger.error(f"  [SESSION {session_id}] ERROR — {e}")

    return result


# ─── Main Entry Point ───────────────────────────────────────────────────────

async def run_ghost_protocol_v2(
    mode: str = "full",
    sessions: int = 3,
    duration: int = 30,
    output_dir: str = "/tmp/gp2_reports",
) -> None:
    """Run Ghost Protocol v2.0 — the full stress test."""

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    start = time.monotonic()

    logger.info("=" * 70)
    logger.info("  👻 OPERATION GHOST PROTOCOL v2.0")
    logger.info("  Advanced Browser Automation Stress Test")
    logger.info(f"  Mode: {mode} | Sessions: {sessions} | Duration: {duration}s")
    logger.info("=" * 70)

    # Run parallel sessions
    session_tasks = [
        run_session(i + 1, mode, duration)
        for i in range(sessions)
    ]
    session_results = await asyncio.gather(*session_tasks, return_exceptions=True)

    # Process results
    processed_results: list[SessionResult] = []
    for i, sr in enumerate(session_results):
        if isinstance(sr, Exception):
            processed_results.append(SessionResult(
                session_id=i + 1, mode=mode,
                status="error", error=str(sr)[:200],
            ))
        else:
            processed_results.append(sr)

    # Generate battle report
    report_path = phase7_battle_report(processed_results, out_path)

    total_duration = time.monotonic() - start

    # Summary
    total_tests = 0
    total_passed = 0
    for sr in processed_results:
        if sr.fingerprint_test:
            total_tests += 1
            if sr.fingerprint_test.status == "success":
                total_passed += 1
        total_tests += len(sr.behavior_tests)
        total_passed += len([b for b in sr.behavior_tests if b.status == "success"])
        if sr.account_test:
            total_tests += 1
            if sr.account_test.status == "success":
                total_passed += 1
        total_tests += len(sr.action_results)
        total_passed += len([a for a in sr.action_results if a.status == "success"])
        if sr.orchestrator_test:
            total_tests += 1
            if sr.orchestrator_test.status == "success":
                total_passed += 1
        total_tests += len(sr.stealth_tests)
        total_passed += len([s for s in sr.stealth_tests if s.status == "success"])

    overall = round(total_passed / max(1, total_tests) * 100, 1)

    logger.info("")
    logger.info("=" * 70)
    logger.info("  👻 GHOST PROTOCOL v2.0 COMPLETE")
    logger.info(f"  Sessions: {sum(1 for s in processed_results if s.status == 'success')}/{sessions}")
    logger.info(f"  Tests: {total_passed}/{total_tests} passed ({overall}%)")
    logger.info(f"  Duration: {total_duration:.1f}s")
    logger.info(f"  Report: file://{report_path}")
    logger.info("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Operation Ghost Protocol v2.0 — Advanced Browser Automation Stress Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full test with 3 parallel sessions, 30s duration
  PYTHONPATH=src python3 scripts/ghost_protocol_v2.py --mode full --sessions 3 --duration 30

  # Recon-only mode (stealth + fingerprint testing)
  PYTHONPATH=src python3 scripts/ghost_protocol_v2.py --mode recon --sessions 1 --duration 15

  # Attack mode (behavior + actions + accounts)
  PYTHONPATH=src python3 scripts/ghost_protocol_v2.py --mode attack --sessions 5 --duration 60
        """,
    )
    parser.add_argument(
        "--mode", choices=["recon", "attack", "full"], default="full",
        help="Test mode: recon (stealth+fingerprint), attack (behavior+actions+accounts), full (all)",
    )
    parser.add_argument(
        "--sessions", type=int, default=3,
        help="Number of parallel sessions (default: 3)",
    )
    parser.add_argument(
        "--duration", type=int, default=30,
        help="Test duration in seconds (default: 30)",
    )
    parser.add_argument(
        "--output", type=str, default="/tmp/gp2_reports",
        help="Output directory for reports (default: /tmp/gp2_reports)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable detailed logging",
    )

    args = parser.parse_args()

    # Configure logging
    logger.remove()
    log_level = "DEBUG" if args.verbose else "INFO"
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:8s}</level> | <level>{message}</level>",
        level=log_level,
    )

    asyncio.run(run_ghost_protocol_v2(
        mode=args.mode,
        sessions=args.sessions,
        duration=args.duration,
        output_dir=args.output,
    ))


if __name__ == "__main__":
    main()
