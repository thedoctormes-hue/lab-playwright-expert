"""
WorkflowRunner — мост между task_template (шаблоны) и task_orchestrator (планировщик).

Соединяет два мира:
  - task_template: BaseTask + наследники (SocialMediaTask, CrossPostTask, ...)
  - task_orchestrator: TaskOrchestrator (очередь, rate limits, воркеры)

Использование:
    >>> runner = WorkflowRunner(browser_manager, workers=3)
    >>> runner.register_task_type("crosspost", CrossPostTask, platforms=["telegraph", "habr"])
    >>> runner.register_task_type("social", SocialMediaTask, platforms=["twitter"])
    >>> runner.add_work("crosspost", title="Hello", content="World", platforms=["telegraph"])
    >>> runner.add_work("social", action="like", target="https://t.me/test/1")
    >>> results = await runner.run()

Паттерн: Bridge + Strategy.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Type

from loguru import logger

from .browser import BrowserManager
from .task_orchestrator import (
    DEFAULT_RATE_LIMITS,
    RateLimit,
    Task,
    TaskOrchestrator,
    TaskPriority,
    TaskStatus,
)
from .task_template import BaseTask, TaskContext


@dataclass
class WorkItem:
    """Единица работы — параметры для конкретного шаблона."""
    task_type: str
    params: dict[str, Any] = field(default_factory=dict)
    priority: int = TaskPriority.NORMAL
    platform: str = ""


@dataclass
class WorkflowResult:
    """Результат выполнения одной работы через WorkflowRunner."""
    work_item: WorkItem
    task_contexts: list[TaskContext] = field(default_factory=list)
    success: bool = False
    error: str = ""
    elapsed_seconds: float = 0.0

    @property
    def summary(self) -> str:
        if self.success:
            return f"✓ {self.work_item.task_type} ({self.elapsed_seconds:.2f}s)"
        return f"✗ {self.work_item.task_type}: {self.error}"


class WorkflowRunner:
    """Запускает шаблоны задач через оркестратор.

    Регистрирует типы задач, создаёт из них Task для оркестратора
    и выполняет параллельно с rate limiting.

    Example:
        >>> runner = WorkflowRunner(browser_manager)
        >>> runner.register_task_type("crosspost", CrossPostTask)
        >>> runner.add_work("crosspost", title="Hi", content="Body", platforms=["telegraph"])
        >>> results = await runner.run()
    """

    def __init__(
        self,
        browser_manager: BrowserManager,
        workers: int = 3,
        rate_limits: dict[str, RateLimit] | None = None,
    ):
        self._browser_mgr = browser_manager
        self._orchestrator = TaskOrchestrator(workers=workers, rate_limits=rate_limits)
        self._task_types: dict[str, Type[BaseTask]] = {}
        self._pending_work: list[WorkItem] = []
        self._results: list[WorkflowResult] = []

    def register_task_type(
        self,
        name: str,
        task_class: Type[BaseTask],
        platforms: list[str] | None = None,
    ) -> None:
        """Зарегистрировать тип задачи.

        Args:
            name: Уникальное имя типа ("crosspost", "social", etc.)
            task_class: Класс-наследник BaseTask
            platforms: Платформы для rate limiting (опционально)
        """
        self._task_types[name] = task_class
        cls_name = getattr(task_class, "__name__", str(task_class))
        logger.debug(f"WorkflowRunner: registered task type '{name}' → {cls_name}")

    def add_work(
        self,
        task_type: str,
        priority: int = TaskPriority.NORMAL,
        platform: str = "",
        **params,
    ) -> None:
        """Добавить работу в очередь.

        Args:
            task_type: Зарегистрированный тип задачи
            priority: Приоритет (TaskPriority.LOW/NORMAL/HIGH/CRITICAL)
            platform: Платформа для rate limiting
            **params: Параметры, передаваемые в шаблон задачи
        """
        if task_type not in self._task_types:
            raise ValueError(
                f"Unknown task type: {task_type}. "
                f"Registered: {list(self._task_types.keys())}"
            )
        work = WorkItem(
            task_type=task_type,
            params=params,
            priority=priority,
            platform=platform,
        )
        self._pending_work.append(work)
        logger.debug(f"WorkflowRunner: added work '{task_type}' with {len(params)} params")

    async def run(self) -> list[WorkflowResult]:
        """Выполнить все добавленные работы через оркестратор.

        Returns:
            Список WorkflowResult для каждой работы.
        """
        if not self._pending_work:
            logger.info("WorkflowRunner: no work items")
            return []

        self._results = []
        start = time.monotonic()

        logger.info(
            f"WorkflowRunner: starting {len(self._pending_work)} work items, "
            f"{self._orchestrator._workers} workers"
        )

        # Создаём handler-ы для каждого типа задачи и регистрируем в оркестраторе
        for work in self._pending_work:
            task_class = self._task_types[work.task_type]

            # Создаём задачу для оркестратора
            task = Task(
                id=f"{work.task_type}_{len(self._results)}",
                platform=work.platform or work.task_type,
                action=work.task_type,
                target=work.params.get("target", ""),
                params=work.params,
                priority=work.priority,
            )

            # Создаём handler, который инстанцирует BaseTask и выполняет
            handler = self._make_handler(task_class, work)
            self._orchestrator.register_handler(work.task_type, handler)
            self._orchestrator.add_task(task)

        # Запускаем оркестратор
        completed_tasks = await self._orchestrator.run()

        # Собираем результаты
        for task in completed_tasks:
            work = next(
                (w for w in self._pending_work
                 if task.params == w.params and task.action == w.task_type),
                None,
            )
            if work is None:
                continue

            result = WorkflowResult(
                work_item=work,
                success=task.status == TaskStatus.SUCCESS,
                error=task.error,
                elapsed_seconds=(task.completed_at - task.started_at)
                if task.completed_at and task.started_at
                else 0.0,
            )

            # Извлекаем TaskContext из результата
            if task.result and "contexts" in task.result:
                result.task_contexts = task.result["contexts"]

            self._results.append(result)

        elapsed = time.monotonic() - start
        success_count = sum(1 for r in self._results if r.success)
        logger.info(
            f"WorkflowRunner: completed in {elapsed:.2f}s — "
            f"{success_count}/{len(self._results)} success"
        )

        return self._results

    def _make_handler(self, task_class: Type[BaseTask], work: WorkItem):
        """Создать handler-функцию для оркестратора.

        Инстанцирует BaseTask и вызывает соответствующий метод.
        """
        async def handler(task: Task) -> dict[str, Any]:
            instance = task_class(browser_manager=self._browser_mgr)
            params = {**work.params, **task.params}

            # Вызываем метод execute, если есть, иначе run
            if hasattr(instance, "execute"):
                contexts = await instance.execute(**params)
            elif hasattr(instance, "run"):
                contexts = await instance.run(**params)
            elif hasattr(instance, "crosspost") and work.task_type == "crosspost":
                contexts = await instance.crosspost(**params)
            else:
                raise RuntimeError(
                    f"Task class {task_class.__name__} has no execute/run method"
                )

            return {"contexts": contexts if isinstance(contexts, list) else [contexts]}

        return handler

    @property
    def stats(self) -> dict[str, Any]:
        """Статистика выполнения."""
        return {
            "pending": len(self._pending_work),
            "completed": len(self._results),
            "success": sum(1 for r in self._results if r.success),
            "failed": sum(1 for r in self._results if not r.success),
            "registered_types": list(self._task_types.keys()),
            **self._orchestrator.stats,
        }
