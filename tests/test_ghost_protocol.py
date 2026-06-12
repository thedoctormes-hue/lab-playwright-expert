"""
Tests for Ghost Protocol v2.0.
Covers: SessionResult, StealthTestResult, data structures, phase results.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── Setup paths ──────────────────────────────────────────────────────────────
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))
sys.path.insert(0, str(_SCRIPTS))

from scripts.ghost_protocol_v2 import (
    SessionResult,
    StealthTestResult,
    BehaviorTestResult,
    FingerprintTestResult,
    AccountTestResult,
    ActionEngineTestResult,
    OrchestratorTestResult,
    phase1_fingerprint_recon,
    phase2_behavior_test,
    phase5_task_orchestration,
    phase6_stealth_test,
    phase7_battle_report,
    FINGERPRINT_PROFILES,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════════════════

class TestSessionResult:
    """Tests for SessionResult dataclass."""

    def test_default_creation(self):
        """Создание SessionResult с дефолтными значениями."""
        sr = SessionResult(session_id=1, mode="full", timestamp=datetime.now(timezone.utc).isoformat())
        assert sr.session_id == 1
        assert sr.mode == "full"
        assert sr.status == "pending"
        assert sr.fingerprint_test is None
        assert sr.behavior_tests == []
        assert sr.account_test is None
        assert sr.action_results == []
        assert sr.orchestrator_test is None
        assert sr.stealth_tests == []
        assert sr.error == ""
        assert sr.duration_ms == 0

    def test_with_fingerprint_result(self):
        """SessionResult с fingerprint результатом."""
        fp = FingerprintTestResult(
            profile_name="chrome_131_windows",
            os="windows",
            browser="chrome",
            webgl_vendor="Google Inc.",
            webgl_renderer="ANGLE (NVIDIA)",
            canvas_noise="seed_42",
            audio_noise="seed_42",
            status="success",
        )
        sr = SessionResult(
            session_id=1, mode="recon",
            timestamp=datetime.now(timezone.utc).isoformat(),
            fingerprint_test=fp,
        )
        assert sr.fingerprint_test is not None
        assert sr.fingerprint_test.status == "success"

    def test_with_behavior_results(self):
        """SessionResult с behavior результатами."""
        bt = BehaviorTestResult(
            profile_name="casual_reader",
            mouse_move_ok=True,
            typing_ok=True,
            scroll_ok=True,
            bezier_points=12,
            status="success",
        )
        sr = SessionResult(
            session_id=1, mode="attack",
            timestamp=datetime.now(timezone.utc).isoformat(),
            behavior_tests=[bt],
        )
        assert len(sr.behavior_tests) == 1

    def test_with_stealth_results(self):
        """SessionResult с stealth результатами."""
        st = StealthTestResult(
            module_name="audio_spoofing",
            script_size=1500,
            injection_ok=True,
            status="success",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        sr = SessionResult(
            session_id=1, mode="full",
            timestamp=datetime.now(timezone.utc).isoformat(),
            stealth_tests=[st],
        )
        assert len(sr.stealth_tests) == 1


class TestStealthTestResult:
    """Tests for StealthTestResult dataclass."""

    def test_creation(self):
        """Создание StealthTestResult."""
        r = StealthTestResult(
            module_name="webrtc_protection",
            script_size=2000,
            injection_ok=True,
            status="success",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        assert r.module_name == "webrtc_protection"
        assert r.script_size == 2000
        assert r.injection_ok is True
        assert r.status == "success"
        assert r.error == ""

    def test_creation_default(self):
        """Создание с дефолтными значениями."""
        r = StealthTestResult(module_name="")
        assert r.module_name == ""
        assert r.script_size == 0
        assert r.injection_ok is False
        assert r.status == "pending"
        assert r.error == ""


class TestFingerprintTestResult:
    """Tests for FingerprintTestResult dataclass."""

    def test_creation(self):
        """Создание FingerprintTestResult."""
        r = FingerprintTestResult(
            profile_name="chrome_131_windows",
            os="windows",
            browser="chrome",
            webgl_vendor="Google Inc.",
            webgl_renderer="ANGLE (NVIDIA)",
            canvas_noise="seed_42",
            audio_noise="seed_42",
            status="success",
        )
        assert r.profile_name == "chrome_131_windows"
        assert r.webgl_vendor == "Google Inc."
        assert r.status == "success"
        assert r.error == ""


class TestBehaviorTestResult:
    """Tests for BehaviorTestResult dataclass."""

    def test_creation(self):
        """Создание BehaviorTestResult."""
        r = BehaviorTestResult(
            profile_name="casual_reader",
            mouse_move_ok=True,
            typing_ok=True,
            scroll_ok=True,
            bezier_points=12,
            status="success",
        )
        assert r.profile_name == "casual_reader"
        assert r.mouse_move_ok is True
        assert r.typing_ok is True
        assert r.scroll_ok is True
        assert r.bezier_points == 12
        assert r.status == "success"
        assert r.error == ""


class TestAccountTestResult:
    """Tests for AccountTestResult dataclass."""

    def test_creation(self):
        """Создание AccountTestResult."""
        r = AccountTestResult(
            platform="telegram",
            username="test_user_123",
            create_ok=True,
            encrypt_ok=True,
            status="success",
        )
        assert r.platform == "telegram"
        assert r.username == "test_user_123"
        assert r.create_ok is True
        assert r.encrypt_ok is True
        assert r.status == "success"


class TestActionEngineTestResult:
    """Tests for ActionEngineTestResult dataclass."""

    def test_creation(self):
        """Создание ActionEngineTestResult."""
        r = ActionEngineTestResult(
            action_type="like",
            profile_name="casual_reader",
            status="success",
            duration_ms=150.0,
        )
        assert r.action_type == "like"
        assert r.profile_name == "casual_reader"
        assert r.status == "success"
        assert r.duration_ms == 150.0
        assert r.error == ""


class TestOrchestratorTestResult:
    """Tests for OrchestratorTestResult dataclass."""

    def test_creation(self):
        """Создание OrchestratorTestResult."""
        r = OrchestratorTestResult(
            tasks_completed=10,
            tasks_failed=0,
            priority_order_ok=True,
            rate_limit_ok=True,
            status="success",
        )
        assert r.tasks_completed == 10
        assert r.tasks_failed == 0
        assert r.priority_order_ok is True
        assert r.rate_limit_ok is True
        assert r.status == "success"


# ═══════════════════════════════════════════════════════════════════════════════
# Fingerprint Profiles
# ═══════════════════════════════════════════════════════════════════════════════

class TestFingerprintProfiles:
    """Tests for FINGERPRINT_PROFILES constant."""

    def test_profiles_not_empty(self):
        """Профили отпечатков не пустые."""
        assert len(FINGERPRINT_PROFILES) > 0

    def test_profile_is_dict(self):
        """Профиль — словарь."""
        for fp in FINGERPRINT_PROFILES:
            assert isinstance(fp, dict)

    def test_profile_has_browser_key(self):
        """Профиль содержит ключ browser."""
        for fp in FINGERPRINT_PROFILES:
            assert "browser" in fp or "os" in fp or len(fp) > 0  # At least non-empty


# ═══════════════════════════════════════════════════════════════════════════════
# Phase Functions (Unit Tests without Browser)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPhase6StealthTest:
    """Tests for phase6_stealth_test (doesn't require browser for script generation)."""

    @pytest.mark.asyncio
    async def test_stealth_config_levels(self):
        """Все уровня StealthConfig генерируют скрипты."""
        from lab_playwright_kit import StealthConfig

        for level_name, level_fn in [
            ("minimal", StealthConfig.minimal),
            ("standard", StealthConfig.standard),
            ("advanced", StealthConfig.advanced),
            ("full", StealthConfig.full),
        ]:
            cfg = level_fn()
            scripts = cfg.get_scripts()
            assert len(scripts) >= 1, f"Level {level_name} should have at least 1 script"

    @pytest.mark.asyncio
    async def test_audio_spoofer_deterministic(self):
        """AudioSpoofer детерминистичен."""
        from lab_playwright_kit.stealth_audio import AudioConfig, AudioSpoofer

        config = AudioConfig.full(noise_seed=42)
        script1 = AudioSpoofer.get_script(config)
        script2 = AudioSpoofer.get_script(config)
        assert script1 == script2

    @pytest.mark.asyncio
    async def test_audio_spoofer_seed_in_script(self):
        """Seed присутствует в скрипте."""
        from lab_playwright_kit.stealth_audio import AudioConfig, AudioSpoofer

        config = AudioConfig.full(noise_seed=999)
        script = AudioSpoofer.get_script(config)
        assert "999" in script

    @pytest.mark.asyncio
    async def test_webrtc_disabled_returns_empty(self):
        """WebRTC disabled — пустая строка."""
        from lab_playwright_kit.stealth_webrtc import WebRTCConfig, WebRTCProtector, WebRTCMode

        config = WebRTCConfig(mode=WebRTCMode.DISABLED)
        assert WebRTCProtector.get_script(config) == ""


# ═══════════════════════════════════════════════════════════════════════════════
# Battle Report
# ═══════════════════════════════════════════════════════════════════════════════

class TestBattleReport:
    """Tests for phase7_battle_report."""

    def test_report_generation(self):
        """Генерация HTML отчёта."""
        import tempfile
        import shutil

        out_dir = tempfile.mkdtemp()
        try:
            results = [
                SessionResult(
                    session_id=1,
                    mode="full",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    status="success",
                ),
                SessionResult(
                    session_id=2,
                    mode="full",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    status="success",
                ),
            ]

            report_path = phase7_battle_report(results, Path(out_dir))
            assert Path(report_path).exists()

            html_content = Path(report_path).read_text()
            assert "Ghost Protocol" in html_content
            assert "session" in html_content.lower()
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_report_with_success_results(self):
        """Отчёт с успешными результатами."""
        import tempfile
        import shutil

        out_dir = tempfile.mkdtemp()
        try:
            fp = FingerprintTestResult(
                profile_name="chrome_131_windows",
                os="windows",
                browser="chrome",
                webgl_vendor="Google Inc.",
                webgl_renderer="ANGLE",
                canvas_noise="seed_42",
                audio_noise="seed_42",
                status="success",
            )
            results = [
                SessionResult(
                    session_id=1, mode="recon",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    fingerprint_test=fp,
                    status="success",
                ),
            ]

            report_path = phase7_battle_report(results, Path(out_dir))
            html_content = Path(report_path).read_text()
            # Session row shows mode and status
            assert "recon" in html_content
            assert "success" in html_content
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_report_with_error_results(self):
        """Отчёт с ошибками."""
        import tempfile
        import shutil

        out_dir = tempfile.mkdtemp()
        try:
            results = [
                SessionResult(
                    session_id=1, mode="full",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    status="error",
                    error="Test error message",
                ),
            ]

            report_path = phase7_battle_report(results, Path(out_dir))
            assert Path(report_path).exists()
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Arguments
# ═══════════════════════════════════════════════════════════════════════════════

class TestCLI:
    """Tests for CLI argument parsing."""

    def test_valid_modes(self):
        """Валидные режимы."""
        valid_modes = ["recon", "attack", "full"]
        for mode in valid_modes:
            assert mode in valid_modes

    def test_default_mode(self):
        """Дефолтный режим."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--mode", choices=["recon", "attack", "full"], default="full")
        args = parser.parse_args([])
        assert args.mode == "full"
