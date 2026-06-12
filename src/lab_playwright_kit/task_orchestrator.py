"""
Task Orchestrator — оркестратор задач с очередью и воркерами.

Управляет выполнением задач:
  - Очередь с приоритетами
  - Параллельные воркеры
  - Rate limiting по платформам
  - Автоматические ретраи
  - Распределение нагрузки между аккаунтами

Использование:
    >>> orchestrator = TaskOrchestrator(workers=3)
    >>> orchestrator.add_task(Task(platform="twitter", action="like", target="https://..."))
    >>> orchestrator.add_task(Task(platform="habr", action="comment", target="https://...", priority=1))
    >>> results = await orchestrator.run()
"""
from __future__ import annotations

import asyncio
import heapq
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger


class TaskPriority(int, Enum):
    """Приоритеты задач."""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


class TaskStatus(str, Enum):
    """Статус задачи."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    RETRYING = "retrying"


@dataclass
class Task:
    """Задача для выполнения."""
    id: str = ""
    platform: str = ""
    action: str = ""
    target: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    priority: int = TaskPriority.NORMAL
    status: str = TaskStatus.PENDING
    account_id: int = 0
    max_retries: int = 3
    retry_count: int = 0
    retry_delay_seconds: float = 5.0
    created_at: float = field(default_factory=time.time)
    started_at: float = 0
    completed_at: float = 0
    error: str = ""
    result: dict[str, Any] = field(default_factory=dict)

    # Для heapq — сравнение по приоритету
    def __lt__(self, other: Task) -> bool:
        return self.priority < other.priority


@dataclass
class RateLimit:
    """Rate limit для платформы."""
    platform: str = ""
    max_per_minute: int = 30
    max_per_hour: int = 500
    max_per_day: int = 5000
    cooldown_seconds: float = 2.0  # минимальная пауза между действиями

    # Внутренние счётчики
    _actions_minute: list[float] = field(default_factory=list)
    _actions_hour: list[float] = field(default_factory=list)
    _actions_day: list[float] = field(default_factory=list)
    _last_action: float = 0

    def can_execute(self) -> bool:
        """Проверить можно ли выполнить действие."""
        now = time.time()

        # Очищаем старые записи
        self._actions_minute = [t for t in self._actions_minute if now - t < 60]
        self._actions_hour = [t for t in self._actions_hour if now - t < 3600]
        self._actions_day = [t for t in self._actions_day if now - t < 86400]

        # Проверяем лимиты
        if len(self._actions_minute) >= self.max_per_minute:
            return False
        if len(self._actions_hour) >= self.max_per_hour:
            return False
        if len(self._actions_day) >= self.max_per_day:
            return False

        # Проверяем cooldown
        if now - self._last_action < self.cooldown_seconds:
            return False

        return True

    def record_action(self) -> None:
        """Записать действие."""
        now = time.time()
        self._actions_minute.append(now)
        self._actions_hour.append(now)
        self._actions_day.append(now)
        self._last_action = now

    @property
    def wait_time(self) -> float:
        """Сколько ждать до следующего действия.

        Возвращает минимальное время ожидания, чтобы все лимиты были соблюдены.
        Если лимит не превышен — ожидание не требуется (0).
        """
        now = time.time()
        waits = []

        # Лимит по минуте: ждём пока старое действие выйдет из окна
        if len(self._actions_minute) >= self.max_per_minute:
            oldest = min(self._actions_minute)
            waits.append(max(0, 60 - (now - oldest)))

        # Лимит по часу
        if len(self._actions_hour) >= self.max_per_hour:
            oldest = min(self._actions_hour)
            waits.append(max(0, 3600 - (now - oldest)))

        # Лимит по дню
        if len(self._actions_day) >= self.max_per_day:
            oldest = min(self._actions_day)
            waits.append(max(0, 86400 - (now - oldest)))

        # Cooldown между действиями
        cooldown_wait = self.cooldown_seconds - (now - self._last_action)
        if cooldown_wait > 0:
            waits.append(cooldown_wait)

        return max(waits) if waits else 0


# ─── Дефолтные rate limits по платформам ────────────────────────────────────

DEFAULT_RATE_LIMITS: dict[str, RateLimit] = {
    "twitter": RateLimit("twitter", max_per_minute=20, max_per_hour=300, max_per_day=3000, cooldown_seconds=3),
    "instagram": RateLimit("instagram", max_per_minute=15, max_per_hour=200, max_per_day=2000, cooldown_seconds=5),
    "facebook": RateLimit("facebook", max_per_minute=20, max_per_hour=300, max_per_day=3000, cooldown_seconds=3),
    "telegram": RateLimit("telegram", max_per_minute=30, max_per_hour=500, max_per_day=5000, cooldown_seconds=1),
    "vk": RateLimit("vk", max_per_minute=20, max_per_hour=300, max_per_day=3000, cooldown_seconds=3),
    "reddit": RateLimit("reddit", max_per_minute=10, max_per_hour=100, max_per_day=1000, cooldown_seconds=5),
    "discord": RateLimit("discord", max_per_minute=10, max_per_hour=100, max_per_day=1000, cooldown_seconds=5),
    "github": RateLimit("github", max_per_minute=30, max_per_hour=500, max_per_day=5000, cooldown_seconds=1),
    "habr": RateLimit("habr", max_per_minute=10, max_per_hour=100, max_per_day=1000, cooldown_seconds=5),
    "vcru": RateLimit("vcru", max_per_minute=10, max_per_hour=100, max_per_day=1000, cooldown_seconds=5),
    "yandex": RateLimit("yandex", max_per_minute=20, max_per_hour=300, max_per_day=3000, cooldown_seconds=2),
    "mailru": RateLimit("mailru", max_per_minute=20, max_per_hour=300, max_per_day=3000, cooldown_seconds=2),
    "tiktok": RateLimit("tiktok", max_per_minute=10, max_per_hour=100, max_per_day=1000, cooldown_seconds=5),
    "youtube": RateLimit("youtube", max_per_minute=20, max_per_hour=300, max_per_day=3000, cooldown_seconds=2),
    "linkedin": RateLimit("linkedin", max_per_minute=10, max_per_hour=100, max_per_day=1000, cooldown_seconds=5),
}


class TaskOrchestrator:
    """Оркестратор задач с очередью и воркерами.

    Управляет выполнением задач с учётом:
    - Приоритетов
    - Rate limits по платформам
    - Автоматических ретраев
    - Параллельных воркеров

    Использование:
        >>> orchestrator = TaskOrchestrator(workers=3)
        >>> orchestrator.add_task(Task(platform="twitter", action="like", target="..."))
        >>> orchestrator.add_task(Task(platform="habr", action="comment", target="...", priority=TaskPriority.HIGH))
        >>> results = await orchestrator.run()
    """

    def __init__(
        self,
        workers: int = 3,
        rate_limits: dict[str, RateLimit] | None = None,
    ):
        self._queue: list[Task] = []  # min-heap по приоритету
        self._results: list[Task] = []
        self._workers = workers
        if rate_limits is not None:
            self._rate_limits = rate_limits
        else:
            self._rate_limits = {
                k: RateLimit(
                    v.platform,
                    max_per_minute=v.max_per_minute,
                    max_per_hour=v.max_per_hour,
                    max_per_day=v.max_per_day,
                    cooldown_seconds=v.cooldown_seconds,
                )
                for k, v in DEFAULT_RATE_LIMITS.items()
            }
        self._handlers: dict[str, Callable] = {}
        self._running = False
        self._total_processed = 0
        self._total_success = 0
        self._total_failed = 0

    def add_task(self, task: Task) -> None:
        """Добавить задачу в очередь.

        Args:
            task: Задача для выполнения
        """
        heapq.heappush(self._queue, task)
        logger.debug(f"Task added: {task.platform}/{task.action} -> {task.target} (priority={task.priority})")

    def add_tasks(self, tasks: list[Task]) -> None:
        """Добавить несколько задач."""
        for task in tasks:
            self.add_task(task)

    def register_handler(
        self,
        action: str,
        handler: Callable,
    ) -> None:
        """Зарегистрировать обработчик действия.

        Args:
            action: Название действия (like, comment, follow, etc.)
            handler: Асинхронная функция-обработчик
        """
        self._handlers[action] = handler
        logger.debug(f"Handler registered: {action}")

    def register_handlers(
        self,
        handlers: dict[str, Callable],
    ) -> None:
        """Зарегистрировать несколько обработчиков."""
        for action, handler in handlers.items():
            self.register_handler(action, handler)

    async def run(self) -> list[Task]:
        """Запустить выполнение всех задач в очереди.

        Returns:
            Список выполненных задач с результатами
        """
        if not self._queue:
            logger.info("No tasks in queue")
            return []

        self._running = True
        self._results = []

        logger.info(f"Starting orchestrator: {len(self._queue)} tasks, {self._workers} workers")

        # Запускаем воркеры
        workers = [
            asyncio.create_task(self._worker(i))
            for i in range(self._workers)
        ]

        # Ждём завершения всех воркеров
        await asyncio.gather(*workers)

        self._running = False

        logger.info(
            f"Orchestrator complete: "
            f"{self._total_success} success, "
            f"{self._total_failed} failed, "
            f"{self._total_processed} total"
        )

        return self._results

    async def run_single(self, task: Task) -> Task:
        """Выполнить одну задачу.

        Args:
            task: Задача

        Returns:
            Задача с результатом
        """
        return await self._execute_task(task)

    async def _worker(self, worker_id: int) -> None:
        """Воркер — забирает задачи из очереди и выполняет."""
        logger.debug(f"Worker {worker_id} started")

        while self._running and self._queue:
            try:
                task = heapq.heappop(self._queue)
            except IndexError:
                break

            # Проверяем rate limit
            rate_limit = self._rate_limits.get(task.platform)
            if rate_limit and not rate_limit.can_execute():
                wait = rate_limit.wait_time
                logger.info(f"Rate limit for {task.platform}, waiting {wait:.1f}s")
                await asyncio.sleep(wait)

            # Выполняем задачу
            result_task = await self._execute_task(task)

            # Записываем action в rate limit
            if rate_limit:
                rate_limit.record_action()

            self._results.append(result_task)
            self._total_processed += 1

            if result_task.status == TaskStatus.SUCCESS:
                self._total_success += 1
            else:
                self._total_failed += 1

        logger.debug(f"Worker {worker_id} finished")

    async def _execute_task(self, task: Task) -> Task:
        """Выполнить одну задачу с ретраями."""
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()

        handler = self._handlers.get(task.action)
        if not handler:
            task.status = TaskStatus.FAILED
            task.error = f"No handler for action: {task.action}"
            task.completed_at = time.time()
            return task

        for attempt in range(task.max_retries + 1):
            try:
                result = await handler(task)
                task.status = TaskStatus.SUCCESS
                task.result = result or {}
                task.completed_at = time.time()
                return task

            except Exception as e:
                task.retry_count = min(attempt + 1, task.max_retries)
                task.error = str(e)

                if attempt < task.max_retries:
                    task.status = TaskStatus.RETRY
                    logger.warning(
                        f"Task {task.id} failed (attempt {attempt + 1}/{task.max_retries}): {e}"
                    )
                    await asyncio.sleep(task.retry_delay_seconds * (attempt + 1))
                else:
                    task.status = TaskStatus.FAILED
                    task.completed_at = time.time()
                    logger.error(f"Task {task.id} failed after {task.max_retries} retries: {e}")
                    return task

        return task

    def set_rate_limit(self, platform: str, rate_limit: RateLimit) -> None:
        """Установить rate limit для платформы."""
        self._rate_limits[platform] = rate_limit

    @property
    def queue_size(self) -> int:
        """Размер очереди."""
        return len(self._queue)

    @property
    def results(self) -> list[Task]:
        """Результаты выполнения."""
        return list(self._results)

    @property
    def stats(self) -> dict[str, Any]:
        """Статистика оркестратора."""
        return {
            "queue_size": len(self._queue),
            "processed": self._total_processed,
            "success": self._total_success,
            "failed": self._total_failed,
            "success_rate": (
                self._total_success / max(1, self._total_processed)
            ) * 100,
            "workers": self._workers,
            "running": self._running,
        }
