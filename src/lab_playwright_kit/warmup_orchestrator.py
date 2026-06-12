"""
Account Warmup Playbook — оркестрация прогрева аккаунтов.

Реализует стратегию постепенного прогрева новых аккаунтов:
  - Day 1: 5-10 действий (просмотр, скроллинг)
  - Day 2-3: 10-20 действий (+ лайки, подписки)
  - Day 4-7: 20-50 действий (+ комментарии, репосты)
  - Week 2+: 50-100 действий (полная активность)

Каждое действие имитирует человеческое поведение:
  - Случайные задержки между действиями
  - Скроллинг с переменной скоростью
  - Паузы «чтения» контента
  - Случайные отклонения от паттерна

Использование:
    >>> orchestrator = WarmupOrchestrator(account_manager)
    >>> await orchestrator.warmup(account, platform="twitter")
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger


class WarmupPhase(str, Enum):
    """Фаза прогрева."""
    PHASE_1 = "phase_1"  # Day 1: наблюдение
    PHASE_2 = "phase_2"  # Day 2-3: лёгкое взаимодействие
    PHASE_3 = "phase_3"  # Day 4-7: активное взаимодействие
    PHASE_4 = "phase_4"  # Week 2+: полная активность
    COMPLETE = "complete"


# Конфигурация фаз: (мин_действия, макс_действия, мин_пауза_сек, макс_пауза_сек)
PHASE_CONFIG: dict[WarmupPhase, tuple[int, int, float, float]] = {
    WarmupPhase.PHASE_1: (5, 10, 30.0, 120.0),
    WarmupPhase.PHASE_2: (10, 20, 15.0, 60.0),
    WarmupPhase.PHASE_3: (20, 50, 5.0, 30.0),
    WarmupPhase.PHASE_4: (50, 100, 2.0, 15.0),
}


class WarmupAction(str, Enum):
    """Типы действий прогрева."""
    SCROLL = "scroll"
    VIEW = "view"
    LIKE = "like"
    FOLLOW = "follow"
    COMMENT = "comment"
    REPOST = "repost"
    CLICK_LINK = "click_link"
    READ_CONTENT = "read_content"


# Доступные действия по фазам
PHASE_ACTIONS: dict[WarmupPhase, list[WarmupAction]] = {
    WarmupPhase.PHASE_1: [
        WarmupAction.SCROLL,
        WarmupAction.VIEW,
        WarmupAction.READ_CONTENT,
    ],
    WarmupPhase.PHASE_2: [
        WarmupAction.SCROLL,
        WarmupAction.VIEW,
        WarmupAction.LIKE,
        WarmupAction.CLICK_LINK,
        WarmupAction.READ_CONTENT,
    ],
    WarmupPhase.PHASE_3: [
        WarmupAction.SCROLL,
        WarmupAction.VIEW,
        WarmupAction.LIKE,
        WarmupAction.FOLLOW,
        WarmupAction.COMMENT,
        WarmupAction.CLICK_LINK,
        WarmupAction.READ_CONTENT,
    ],
    WarmupPhase.PHASE_4: [
        WarmupAction.SCROLL,
        WarmupAction.VIEW,
        WarmupAction.LIKE,
        WarmupAction.FOLLOW,
        WarmupAction.COMMENT,
        WarmupAction.REPOST,
        WarmupAction.CLICK_LINK,
        WarmupAction.READ_CONTENT,
    ],
}


@dataclass
class WarmupState:
    """Состояние прогрева аккаунта."""
    account_id: int
    platform: str
    phase: WarmupPhase = WarmupPhase.PHASE_1
    actions_completed: int = 0
    actions_in_phase: int = 0
    started_at: float = 0
    last_action_at: float = 0
    total_actions: int = 0
    errors: int = 0

    @property
    def is_complete(self) -> bool:
        return self.phase == WarmupPhase.COMPLETE

    @property
    def phase_progress(self) -> float:
        if self.actions_in_phase == 0:
            return 0.0
        return min(1.0, self.actions_completed / self.actions_in_phase)


@dataclass
class WarmupResult:
    """Результат прогрева."""
    account_id: int
    success: bool
    actions_performed: int
    errors: int
    duration_seconds: float
    final_phase: WarmupPhase
    message: str = ""


class WarmupOrchestrator:
    """Оркестратор прогрева аккаунтов."""

    def __init__(self, account_manager=None):
        self.account_manager = account_manager
        self._states: dict[int, WarmupState] = {}

    def get_phase_for_account(self, total_actions: int) -> WarmupPhase:
        """Определить фазу по общему количеству действий."""
        if total_actions < 10:
            return WarmupPhase.PHASE_1
        elif total_actions < 30:
            return WarmupPhase.PHASE_2
        elif total_actions < 80:
            return WarmupPhase.PHASE_3
        elif total_actions < 200:
            return WarmupPhase.PHASE_4
        else:
            return WarmupPhase.COMPLETE

    async def warmup(
        self,
        account,
        platform: str,
        action_callback=None,
    ) -> WarmupResult:
        """Прогреть аккаунт.

        Args:
            account: Account object
            platform: платформа
            action_callback: async callback(action_type, account) -> bool

        Returns:
            WarmupResult
        """
        start_time = time.time()
        state = WarmupState(
            account_id=account.id,
            platform=platform,
            phase=self.get_phase_for_account(account.total_actions),
            started_at=start_time,
        )
        self._states[account.id] = state

        if state.is_complete:
            return WarmupResult(
                account_id=account.id,
                success=True,
                actions_performed=0,
                errors=0,
                duration_seconds=0,
                final_phase=state.phase,
                message="Account already fully warmed up",
            )

        # Определить количество действий для текущей фазы
        min_actions, max_actions, min_pause, max_pause = PHASE_CONFIG[state.phase]
        target_actions = random.randint(min_actions, max_actions)
        state.actions_in_phase = target_actions

        logger.info(
            f"Warmup [{platform}] account={account.username} "
            f"phase={state.phase.value} target={target_actions} actions"
        )

        actions_performed = 0
        errors = 0

        for i in range(target_actions):
            # Проверить не заблокирован ли аккаунт
            if hasattr(account, 'status') and account.status in ("banned", "dead"):
                logger.warning(f"Account {account.username} is {account.status}, stopping warmup")
                break

            # Выбрать случайное действие для текущей фазы
            available_actions = PHASE_ACTIONS.get(state.phase, [WarmupAction.VIEW])
            action = random.choice(available_actions)

            # Выполнить действие
            try:
                if action_callback:
                    success = await action_callback(action, account)
                else:
                    success = await self._default_action(action, account)

                if success:
                    actions_performed += 1
                    state.actions_completed += 1
                    state.total_actions += 1
                else:
                    errors += 1
                    state.errors += 1

            except Exception as e:
                logger.warning(f"Warmup action {action} failed for {account.username}: {e}")
                errors += 1
                state.errors += 1

            state.last_action_at = time.time()

            # Пауза между действиями (человеческое поведение)
            if i < target_actions - 1:
                pause = random.uniform(min_pause, max_pause)
                # Добавить случайные длинные паузы («ушёл на обед»)
                if random.random() < 0.05:
                    pause *= random.uniform(3, 10)
                    logger.debug(f"Long pause: {pause:.0f}s")
                await asyncio.sleep(pause)

        # Обновить фазу
        new_phase = self.get_phase_for_account(account.total_actions + actions_performed)
        state.phase = new_phase

        duration = time.time() - start_time
        success = errors < actions_performed  # успех если ошибок меньше чем действий

        result = WarmupResult(
            account_id=account.id,
            success=success,
            actions_performed=actions_performed,
            errors=errors,
            duration_seconds=round(duration, 1),
            final_phase=state.phase,
            message=f"Warmup {state.phase.value}: {actions_performed}/{target_actions} actions",
        )

        logger.info(
            f"Warmup complete for {account.username}: "
            f"{actions_performed} actions, {errors} errors, "
            f"phase={state.phase.value}, {duration:.0f}s"
        )

        return result

    async def _default_action(self, action: WarmupAction, account) -> bool:
        """Действие по умолчанию (заглушка — должна быть переопределена)."""
        logger.debug(f"Default warmup action: {action.value} for {account.username}")
        await asyncio.sleep(random.uniform(0.5, 2.0))
        return True

    def get_state(self, account_id: int) -> WarmupState | None:
        """Получить состояние прогрева аккаунта."""
        return self._states.get(account_id)

    def get_recommended_schedule(self, account) -> dict[str, Any]:
        """Получить рекомендуемый график прогрева."""
        phase = self.get_phase_for_account(account.total_actions)
        min_a, max_a, min_p, max_p = PHASE_CONFIG.get(phase, (5, 10, 30.0, 120.0))
        actions = PHASE_ACTIONS.get(phase, [])

        return {
            "phase": phase.value,
            "total_actions_so_far": account.total_actions,
            "recommended_actions": f"{min_a}-{max_a}",
            "recommended_pause": f"{min_p:.0f}-{max_p:.0f}s",
            "available_actions": [a.value for a in actions],
            "next_phase": self._next_phase(phase).value if phase != WarmupPhase.COMPLETE else None,
            "actions_to_next_phase": self._actions_to_next_phase(phase, account.total_actions),
        }

    def _next_phase(self, phase: WarmupPhase) -> WarmupPhase:
        order = [WarmupPhase.PHASE_1, WarmupPhase.PHASE_2, WarmupPhase.PHASE_3, WarmupPhase.PHASE_4, WarmupPhase.COMPLETE]
        idx = order.index(phase)
        return order[min(idx + 1, len(order) - 1)]

    def _actions_to_next_phase(self, phase: WarmupPhase, total: int) -> int:
        thresholds = {
            WarmupPhase.PHASE_1: 10,
            WarmupPhase.PHASE_2: 30,
            WarmupPhase.PHASE_3: 80,
            WarmupPhase.PHASE_4: 200,
        }
        target = thresholds.get(phase, 999)
        return max(0, target - total)
