"""
Тесты для WarmupOrchestrator — оркестрация прогрева аккаунтов.
"""
import pytest

from lab_playwright_kit.warmup_orchestrator import (
    PHASE_ACTIONS, PHASE_CONFIG, WarmupAction, WarmupOrchestrator,
    WarmupPhase, WarmupResult, WarmupState,
)


class TestWarmupPhase:
    def test_values(self):
        assert WarmupPhase.PHASE_1.value == "phase_1"
        assert WarmupPhase.COMPLETE.value == "complete"


class TestWarmupAction:
    def test_all(self):
        assert len(set(WarmupAction)) == 8


class TestPhaseConfig:
    def test_all_phases(self):
        for p in [WarmupPhase.PHASE_1, WarmupPhase.PHASE_2, WarmupPhase.PHASE_3, WarmupPhase.PHASE_4]:
            assert p in PHASE_CONFIG
            mn, mx, mp, mp2 = PHASE_CONFIG[p]
            assert 0 < mn <= mx

    def test_progressive(self):
        phases = [WarmupPhase.PHASE_1, WarmupPhase.PHASE_2, WarmupPhase.PHASE_3, WarmupPhase.PHASE_4]
        for i in range(1, len(phases)):
            assert set(PHASE_ACTIONS[phases[i-1]]).issubset(set(PHASE_ACTIONS[phases[i]]))


class TestWarmupState:
    def test_default(self):
        s = WarmupState(account_id=1, platform="tw")
        assert s.phase == WarmupPhase.PHASE_1
        assert s.is_complete is False
        assert s.phase_progress == 0.0

    def test_progress(self):
        s = WarmupState(account_id=1, platform="tw", actions_completed=5, actions_in_phase=10)
        assert s.phase_progress == 0.5

    def test_complete(self):
        s = WarmupState(account_id=1, platform="tw", phase=WarmupPhase.COMPLETE)
        assert s.is_complete is True


class TestWarmupOrchestrator:
    def test_init(self):
        o = WarmupOrchestrator()
        assert o.account_manager is None

    def test_phases(self):
        o = WarmupOrchestrator()
        assert o.get_phase_for_account(0) == WarmupPhase.PHASE_1
        assert o.get_phase_for_account(15) == WarmupPhase.PHASE_2
        assert o.get_phase_for_account(50) == WarmupPhase.PHASE_3
        assert o.get_phase_for_account(100) == WarmupPhase.PHASE_4
        assert o.get_phase_for_account(200) == WarmupPhase.COMPLETE

    def test_schedule(self):
        o = WarmupOrchestrator()
        class FA:
            total_actions = 0
        s = o.get_recommended_schedule(FA())
        assert s["phase"] == "phase_1"
        assert "recommended_actions" in s

    def test_next_phase(self):
        o = WarmupOrchestrator()
        assert o._next_phase(WarmupPhase.PHASE_1) == WarmupPhase.PHASE_2
        assert o._next_phase(WarmupPhase.PHASE_4) == WarmupPhase.COMPLETE
        assert o._next_phase(WarmupPhase.COMPLETE) == WarmupPhase.COMPLETE
