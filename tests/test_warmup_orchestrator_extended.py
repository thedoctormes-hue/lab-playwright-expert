"""
Extended tests for warmup_orchestrator.py — WarmupPhase, WarmupState, WarmupResult, WarmupOrchestrator.
Covers: enums, dataclasses, WarmupOrchestrator logic.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lab_playwright_kit.warmup_orchestrator import (
    PHASE_CONFIG,
    WarmupOrchestrator,
    WarmupPhase,
    WarmupResult,
    WarmupState,
)


class TestWarmupPhase:
    def test_all_phases(self):
        assert WarmupPhase.INIT.value == "init"
        assert WarmupPhase.BROWSER_START.value == "browser_start"
        assert WarmupPhase.LOGIN.value == "login"
        assert WarmupPhase.BROWSE.value == "browse"
        assert WarmupPhase.ENGAGE.value == "engage"
        assert WarmupPhase.COMPLETE.value == "complete"
        assert WarmupPhase.FAILED.value == "failed"

    def test_from_string(self):
        assert WarmupPhase.from_string("init") == WarmupPhase.INIT
        assert WarmupPhase.from_string("browse") == WarmupPhase.BROWSE
        assert WarmupPhase.from_string("complete") == WarmupPhase.COMPLETE

    def test_from_string_invalid(self):
        assert WarmupPhase.from_string("nonexistent") is None


class TestWarmupState:
    def test_defaults(self):
        state = WarmupState()
        assert state.phase == WarmupPhase.INIT
        assert state.attempt == 0
        assert state.max_attempts == 3
        assert state.progress == 0.0
        assert state.errors == []
        assert state.metadata == {}

    def test_current_phase_name(self):
        state = WarmupState(phase=WarmupPhase.BROWSE)
        assert state.current_phase_name == "browse"

    def test_is_complete(self):
        assert WarmupState(phase=WarmupPhase.COMPLETE).is_complete is True
        assert WarmupState(phase=WarmupPhase.BROWSE).is_complete is False

    def test_is_failed(self):
        assert WarmupState(phase=WarmupPhase.FAILED).is_failed is True
        assert WarmupState(phase=WarmupPhase.BROWSE).is_failed is False

    def test_can_retry(self):
        state = WarmupState(attempt=1, max_attempts=3)
        assert state.can_retry is True

    def test_cannot_retry(self):
        state = WarmupState(attempt=3, max_attempts=3)
        assert state.can_retry is False

    def test_to_dict(self):
        state = WarmupState(phase=WarmupPhase.BROWSE, attempt=1, progress=50.0)
        d = state.to_dict()
        assert d["phase"] == "browse"
        assert d["attempt"] == 1
        assert d["progress"] == 50.0


class TestWarmupResult:
    def test_defaults(self):
        result = WarmupResult()
        assert result.success is False
        assert result.account == ""
        assert result.platform == ""
        assert result.duration_seconds == 0.0
        assert result.phases_completed == []
        assert result.errors == []

    def test_success(self):
        result = WarmupResult(success=True, account="test", platform="tg", duration_seconds=60.0)
        assert result.success is True
        assert result.account == "test"

    def test_phases_count(self):
        result = WarmupResult(
            phases_completed=["init", "browser_start", "browse", "engage", "complete"]
        )
        assert result.phases_count == 5

    def test_to_dict(self):
        result = WarmupResult(success=True, account="test", platform="tg", duration_seconds=30.0)
        d = result.to_dict()
        assert d["success"] is True
        assert d["account"] == "test"
        assert d["duration_seconds"] == 30.0


class TestWarmupOrchestrator:
    def test_init(self):
        orch = WarmupOrchestrator()
        assert orch._bm is None
        assert orch._states == {}
        assert orch._results == []

    def test_init_with_browser(self):
        bm = MagicMock()
        orch = WarmupOrchestrator(browser_manager=bm)
        assert orch._bm is bm

    def test_phase_config(self):
        assert "init" in PHASE_CONFIG
        assert "browse" in PHASE_CONFIG
        assert "complete" in PHASE_CONFIG

    def test_get_state_empty(self):
        orch = WarmupOrchestrator()
        assert orch.get_state("nonexistent") is None

    @pytest.mark.asyncio
    async def test_run_empty(self):
        orch = WarmupOrchestrator()
        with patch.object(
            orch,
            "_execute_phase",
            new_callable=AsyncMock,
            return_value=WarmupState(phase=WarmupPhase.COMPLETE),
        ):
            result = await orch.run("test_account", "telegram")
            assert isinstance(result, WarmupResult)

    @pytest.mark.asyncio
    async def test_run_success(self):
        orch = WarmupOrchestrator()
        states = [
            WarmupState(phase=WarmupPhase.BROWSER_START, progress=20.0),
            WarmupState(phase=WarmupPhase.LOGIN, progress=40.0),
            WarmupState(phase=WarmupPhase.BROWSE, progress=60.0),
            WarmupState(phase=WarmupPhase.ENGAGE, progress=80.0),
            WarmupState(phase=WarmupPhase.COMPLETE, progress=100.0),
        ]
        with patch.object(orch, "_execute_phase", new_callable=AsyncMock, side_effect=states):
            with patch.object(
                orch, "_init_state", return_value=WarmupState(phase=WarmupPhase.INIT)
            ):
                result = await orch.run("test", "tg")
                assert result.success is True

    @pytest.mark.asyncio
    async def test_run_failure(self):
        orch = WarmupOrchestrator()
        with patch.object(
            orch,
            "_execute_phase",
            new_callable=AsyncMock,
            return_value=WarmupState(phase=WarmupPhase.FAILED),
        ):
            with patch.object(
                orch, "_init_state", return_value=WarmupState(phase=WarmupPhase.INIT)
            ):
                result = await orch.run("test", "tg")
                assert result.success is False

    def test_get_results(self):
        orch = WarmupOrchestrator()
        orch._results.append(WarmupResult(success=True))
        assert len(orch.get_results()) == 1

    def test_reset(self):
        orch = WarmupOrchestrator()
        orch._states["test"] = WarmupState()
        orch._results.append(WarmupResult())
        orch.reset()
        assert orch._states == {}
        assert orch._results == []
