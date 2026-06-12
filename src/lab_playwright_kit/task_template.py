"""
TaskTemplate — система шаблонов типовых сценариев автоматизации.

Паттерн Template Method для браузерных задач:
- Предустановленные шаблоны для частых сценариев
- Композиция шагов с условиями и повторами
- Интеграция с ActionEngine, DataParser, HealthMonitor
- Логирование, retry, уведомления

Типовые шаблоны:
- SocialMediaTask: лайки, подписки, комментарии
- ContentPublishTask: публикация контента
- DataCollectionTask: сбор данных с сайтов
- AuthTask: авторизация на сайтах
- MonitoringTask: мониторинг изменений
- CrossPostTask: кросспостинг между платформами

Использование:
    >>> template = SocialMediaTask(browser_manager, platform="twitter")
    >>> result = await template.like_and_follow("https://twitter.com/user/status/123")
    >>> result = await template.mass_follow(["https://twitter.com/u1", ...], delay_range=(5, 15))
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from loguru import logger
from playwright.async_api import Page

from .action_engine import ActionEngine, ActionResult, ActionStep, ActionType
from .browser import BrowserManager
from .health_monitor import HealthMonitor, HealthCheck, HealthStatus
from .task_orchestrator import TaskStatus


# ─── Task Context ────────────────────────────────────────────────────────────

@dataclass
class TaskContext:
    """Контекст выполнения задачи — пробрасывается между шагами."""
    task_id: str = ""
    task_name: str = ""
    status: TaskStatus = TaskStatus.PENDING
    current_step: int = 0
    total_steps: int = 0
    results: list[ActionResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""
    page: Any = None
    browser_manager: Any = None

    @property
    def duration_ms(self) -> float:
        if not self.started_at:
            return 0.0
        start = datetime.fromisoformat(self.started_at)
        end = datetime.fromisoformat(self.finished_at) if self.finished_at else datetime.now(timezone.utc)
        return (end - start).total_seconds() * 1000

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.is_success)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if not r.is_success)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "status": self.status.value,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "errors": self.errors,
            "duration_ms": self.duration_ms,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


# ─── Task Step ───────────────────────────────────────────────────────────────

@dataclass
class TaskStep:
    """Один шаг в шаблоне задачи."""
    name: str
    action: str  # ActionType value or custom
    params: dict[str, Any] = field(default_factory=dict)
    condition: str | None = None  # условие выполнения (eval expression)
    on_fail: str = "continue"  # continue, abort, retry
    max_retries: int = 3
    retry_delay: float = 1.0
    pre_delay: float = 0.0  # задержка ДО шага
    post_delay: float = 0.0  # задержка ПОСЛЕ шага
    timeout: float = 30.0
    description: str = ""


# ─── Base Task Template ──────────────────────────────────────────────────────

class BaseTask(ABC):
    """Базовый класс шаблона задачи (Template Method pattern)."""

    def __init__(
        self,
        browser_manager: BrowserManager,
        health_monitor: HealthMonitor | None = None,
        max_retries: int = 3,
        step_delay: tuple[float, float] = (1.0, 3.0),
    ):
        self._browser_mgr = browser_manager
        self._health = health_monitor
        self._max_retries = max_retries
        self._step_delay = step_delay
        self._action_engine: ActionEngine | None = None
        self._page: Page | None = None

    async def _ensure_page(self) -> Page:
        if self._page is None:
            ctx = await self._browser_mgr.get_context()
            self._page = await ctx.new_page()
        return self._page

    async def _ensure_action_engine(self) -> ActionEngine:
        if self._action_engine is None:
            page = await self._ensure_page()
            self._action_engine = ActionEngine(page)
        return self._action_engine

    async def execute_step(self, step: TaskStep, ctx: TaskContext) -> ActionResult:
        """Выполнить один шаг с retry и задержками."""
        engine = await self._ensure_action_engine()

        for attempt in range(step.max_retries):
            try:
                # Pre-delay
                if step.pre_delay > 0:
                    await asyncio.sleep(step.pre_delay)

                # Выполнить действие
                start = time.monotonic()

                action_method = getattr(engine, step.action, None)
                if action_method:
                    result = await action_method(**step.params)
                else:
                    # Кастомное действие через page
                    result = await self._execute_custom_action(step, ctx)

                elapsed = (time.monotonic() - start) * 1000

                if isinstance(result, ActionResult):
                    result.duration_ms = elapsed
                else:
                    result = ActionResult(
                        action_type=step.action,
                        status="success" if result else "failed",
                        duration_ms=elapsed,
                    )

                # Post-delay
                if step.post_delay > 0:
                    await asyncio.sleep(step.post_delay)

                return result

            except Exception as e:
                logger.warning(f"Step '{step.name}' attempt {attempt + 1} failed: {e}")
                if attempt < step.max_retries - 1:
                    await asyncio.sleep(step.retry_delay * (attempt + 1))
                else:
                    return ActionResult(
                        action_type=step.action,
                        status="failed",
                        message=str(e),
                    )

        return ActionResult(action_type=step.action, status="failed", message="Max retries exceeded")

    async def _execute_custom_action(self, step: TaskStep, ctx: TaskContext) -> ActionResult:
        """Выполнить кастомное действие (переопределяется в наследниках)."""
        return ActionResult(action_type=step.action, status="skipped", message="Custom action not implemented")

    @abstractmethod
    def get_steps(self) -> list[TaskStep]:
        """Получить список шагов для задачи."""
        ...

    @abstractmethod
    def get_task_name(self) -> str:
        """Получить имя задачи."""
        ...

    async def run(self, **kwargs) -> TaskContext:
        """Запустить задачу (Template Method)."""
        import uuid

        ctx = TaskContext(
            task_id=str(uuid.uuid4())[:8],
            task_name=self.get_task_name(),
            status=TaskStatus.RUNNING,
            started_at=datetime.now(timezone.utc).isoformat(),
            browser_manager=self._browser_mgr,
            metadata=kwargs,
        )

        logger.info(f"Task '{ctx.task_name}' [{ctx.task_id}] started")

        try:
            # Pre-run hook
            await self._pre_run(ctx)

            steps = self.get_steps()
            ctx.total_steps = len(steps)

            for i, step in enumerate(steps):
                ctx.current_step = i + 1

                # Проверить условие
                if step.condition and not self._eval_condition(step.condition, ctx):
                    logger.debug(f"Step '{step.name}' skipped (condition: {step.condition})")
                    continue

                logger.info(f"Step {i + 1}/{len(steps)}: {step.name}")
                result = await self.execute_step(step, ctx)
                ctx.results.append(result)

                # Обработка ошибки
                if not result.is_success:
                    ctx.errors.append(f"Step '{step.name}': {result.message}")
                    if step.on_fail == "abort":
                        ctx.status = TaskStatus.FAILED
                        logger.error(f"Task aborted at step '{step.name}'")
                        break
                    elif step.on_fail == "retry":
                        # Retry уже внутри execute_step
                        pass

                # Задержка между шагами
                if i < len(steps) - 1:
                    import random
                    delay = random.uniform(*self._step_delay)
                    await asyncio.sleep(delay)

            # Если не aborted — значит completed
            if ctx.status != TaskStatus.FAILED:
                ctx.status = TaskStatus.COMPLETED

            # Post-run hook
            await self._post_run(ctx)

        except Exception as e:
            ctx.status = TaskStatus.FAILED
            ctx.errors.append(str(e))
            logger.error(f"Task '{ctx.task_name}' failed: {e}")

        ctx.finished_at = datetime.now(timezone.utc).isoformat()

        # Health check
        if self._health:
            self._health._record_check(HealthCheck(
                name=f"task_{ctx.task_name}",
                status=HealthStatus.OK if ctx.status == TaskStatus.COMPLETED else HealthStatus.FAIL,
                metadata=ctx.to_dict(),
            ))

        logger.info(
            f"Task '{ctx.task_name}' [{ctx.task_id}] {ctx.status.value} | "
            f"steps: {ctx.success_count}/{ctx.total_steps} | "
            f"duration: {ctx.duration_ms:.0f}ms"
        )

        return ctx

    async def _pre_run(self, ctx: TaskContext) -> None:
        """Hook перед запуском — переопределяется в наследниках."""
        pass

    async def _post_run(self, ctx: TaskContext) -> None:
        """Hook после завершения — переопределяется в наследниках."""
        pass

    def _eval_condition(self, condition: str, ctx: TaskContext) -> bool:
        """Вычислить условие (простой eval с контекстом)."""
        try:
            safe_builtins = {"len": len, "any": any, "all": all, "bool": bool, "int": int, "str": str}
            namespace = {
                "ctx": ctx,
                "results": ctx.results,
                "errors": ctx.errors,
                "metadata": ctx.metadata,
                **safe_builtins,
            }
            return bool(eval(condition, {"__builtins__": {}}, namespace))
        except Exception:
            return True  # при ошибке условия — выполняем шаг

    async def close(self) -> None:
        if self._page:
            try:
                await self._page.close()
            except Exception:
                pass
            self._page = None


# ─── Social Media Task ───────────────────────────────────────────────────────

class SocialMediaTask(BaseTask):
    """Задачи для социальных сетей: лайки, подписки, комментарии."""

    PLATFORM_SELECTORS = {
        "twitter": {
            "like": "[data-testid='like']",
            "retweet": "[data-testid='retweet']",
            "follow": "[data-testid='follow']",
            "comment": "[data-testid='tweetTextarea_0']",
            "submit_comment": "[data-testid='tweetButtonInline']",
        },
        "instagram": {
            "like": "article svg[aria-label='Like']",
            "follow": "header button",
            "comment": "textarea[aria-label='Add a comment…']",
        },
        "telegram_web": {
            "message": ".message",
            "reply": ".reply-btn",
            "send": ".send-btn",
        },
    }

    def __init__(self, browser_manager: BrowserManager, platform: str = "twitter", **kwargs):
        super().__init__(browser_manager, **kwargs)
        self._platform = platform
        self._selectors = self.PLATFORM_SELECTORS.get(platform, {})

    def get_task_name(self) -> str:
        return f"social_{self._platform}"

    def get_steps(self) -> list[TaskStep]:
        return []  # Определяются в конкретных методах

    async def like_post(self, url: str) -> TaskContext:
        """Лайкнуть пост."""
        steps = [
            TaskStep(
                name="navigate",
                action="navigate",
                params={"url": url},
                post_delay=2.0,
            ),
            TaskStep(
                name="like",
                action="click",
                params={"selector": self._selectors.get("like", "[data-testid='like']")},
                on_fail="abort",
                post_delay=1.0,
            ),
        ]
        return await self.run(url=url, action="like")

    async def follow_user(self, url: str) -> TaskContext:
        """Подписаться на пользователя."""
        steps = [
            TaskStep(
                name="navigate",
                action="navigate",
                params={"url": url},
                post_delay=2.0,
            ),
            TaskStep(
                name="follow",
                action="click",
                params={"selector": self._selectors.get("follow", "button")},
                on_fail="abort",
            ),
        ]
        return await self.run(url=url, action="follow")

    async def mass_follow(self, urls: list[str], delay_range: tuple[float, float] = (5.0, 15.0)) -> list[TaskContext]:
        """Массовая подписка с рандомными задержками."""
        results = []
        for url in urls:
            ctx = await self.follow_user(url)
            results.append(ctx)
            if ctx.status == TaskStatus.FAILED:
                logger.warning(f"Mass follow stopped at {url}")
                break
            import random
            await asyncio.sleep(random.uniform(*delay_range))
        return results


# ─── Content Publish Task ────────────────────────────────────────────────────

class ContentPublishTask(BaseTask):
    """Публикация контента на платформах."""

    def __init__(
        self,
        browser_manager: BrowserManager,
        platform: str = "generic",
        credentials: dict[str, str] | None = None,
        **kwargs,
    ):
        super().__init__(browser_manager, **kwargs)
        self._platform = platform
        self._credentials = credentials or {}

    def get_task_name(self) -> str:
        return f"publish_{self._platform}"

    def get_steps(self) -> list[TaskStep]:
        return []

    async def publish(
        self,
        url: str,
        title: str = "",
        content: str = "",
        tags: list[str] | None = None,
        **kwargs,
    ) -> TaskContext:
        """Опубликовать контент."""
        return await self.run(
            url=url,
            title=title,
            content=content,
            tags=tags or [],
            **kwargs,
        )


# ─── Data Collection Task ────────────────────────────────────────────────────

class DataCollectionTask(BaseTask):
    """Сбор данных с сайтов через DataParser."""

    def __init__(
        self,
        browser_manager: BrowserManager,
        niche: str = "generic",
        **kwargs,
    ):
        super().__init__(browser_manager, **kwargs)
        self._niche = niche

    def get_task_name(self) -> str:
        return f"collect_{self._niche}"

    def get_steps(self) -> list[TaskStep]:
        return []

    async def collect(
        self,
        urls: list[str],
        niche: str | None = None,
    ) -> list[TaskContext]:
        """Собрать данные с списка URL."""
        from .data_parser import DataParser, NicheType, detect_niche

        results = []
        parser = DataParser(
            self._browser_mgr,
            niche=NicheType(niche) if niche else None,
        )

        for url in urls:
            try:
                parse_result = await parser.parse(url)
                ctx = TaskContext(
                    task_name=self.get_task_name(),
                    status=TaskStatus.COMPLETED if parse_result.is_valid else TaskStatus.FAILED,
                    results=[ActionResult(
                        action_type="parse",
                        status="success" if parse_result.is_valid else "failed",
                        target=url,
                        metadata=parse_result.to_dict(),
                    )],
                    started_at=parse_result.parsed_at,
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    metadata={"url": url, "niche": parse_result.niche.value},
                )
                if not parse_result.is_valid:
                    ctx.errors = parse_result.errors
                results.append(ctx)
            except Exception as e:
                results.append(TaskContext(
                    task_name=self.get_task_name(),
                    status=TaskStatus.FAILED,
                    errors=[str(e)],
                    metadata={"url": url},
                ))

        await parser.close()
        return results


# ─── Auth Task ───────────────────────────────────────────────────────────────

class AuthTask(BaseTask):
    """Авторизация на сайтах."""

    # Пресеты для популярных платформ
    PLATFORM_PRESETS: dict[str, dict[str, Any]] = {
        "habr": {
            "login_url": "https://habr.com/ru/auth/",
            "auth_url": "https://habr.com/ru/articles/",
            "auth_selectors": [
                "a[href*='editor']",
                ".user-panel",
                ".avatar",
                ".user-login",
            ],
            "username_selector": "input[name='email'], input[type='email'], #email",
            "password_selector": "input[name='password'], input[type='password'], #password",
            "submit_selector": "button[type='submit'], .auth-form__button, .m-button",
            "success_indicator": ".user-panel, .avatar",
        },
        "vc_ru": {
            "login_url": "https://vc.ru/auth",
            "auth_url": "https://vc.ru/write",
            "auth_selectors": [
                ".user-menu",
                ".avatar",
                "a[href*='write']",
                ".user_login",
            ],
            "username_selector": "input[name='email'], input[name='login'], input[type='email']",
            "password_selector": "input[name='password'], input[type='password']",
            "submit_selector": "button[type='submit'], .button, input[type='submit']",
            "success_indicator": ".user-menu, .avatar",
        },
        "tenchat": {
            "login_url": "https://tenchat.ru/login",
            "auth_url": "https://tenchat.ru/post/new",
            "auth_selectors": [
                ".user-menu",
                ".avatar",
                ".user_login",
            ],
            "username_selector": "input[name='email'], input[name='login']",
            "password_selector": "input[name='password']",
            "submit_selector": "button[type='submit'], .button",
            "success_indicator": ".user-menu",
        },
    }

    def __init__(
        self,
        browser_manager: BrowserManager,
        credentials: dict[str, str] | None = None,
        **kwargs,
    ):
        super().__init__(browser_manager, **kwargs)
        self._credentials = credentials or {}
        self._cookies: list[dict] = []

    def get_task_name(self) -> str:
        return "auth"

    def get_steps(self) -> list[TaskStep]:
        return []

    async def login(
        self,
        login_url: str,
        username_selector: str = "input[name='username'], input[name='email'], #username, #email",
        password_selector: str = "input[name='password'], input[type='password'], #password",
        submit_selector: str = "button[type='submit'], input[type='submit'], .login-btn, #login-btn",
        success_indicator: str = "",
        username: str = "",
        password: str = "",
    ) -> TaskContext:
        """Выполнить авторизацию."""
        creds = self._credentials
        username = username or creds.get("username", "")
        password = password or creds.get("password", "")

        if not username or not password:
            return TaskContext(
                task_name="auth",
                status=TaskStatus.FAILED,
                errors=["Missing credentials"],
            )

        ctx = TaskContext(
            task_name="auth",
            status=TaskStatus.RUNNING,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        try:
            page = await self._ensure_page()
            engine = await self._ensure_action_engine()

            # Перейти на страницу логина
            await page.goto(login_url, wait_until="domcontentloaded")
            await asyncio.sleep(1)

            # Ввести логин
            await page.fill(username_selector, username)
            await asyncio.sleep(0.5)

            # Ввести пароль
            await page.fill(password_selector, password)
            await asyncio.sleep(0.5)

            # Нажать submit
            await page.click(submit_selector)

            # Ждём навигации или индикатора успеха
            try:
                if success_indicator:
                    await page.wait_for_selector(success_indicator, timeout=10000)
                else:
                    await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass

            # Сохранить куки
            self._cookies = await page.context.cookies()

            ctx.status = TaskStatus.COMPLETED
            ctx.results.append(ActionResult(
                action_type="login",
                status="success",
                target=login_url,
            ))

        except Exception as e:
            ctx.status = TaskStatus.FAILED
            ctx.errors.append(str(e))
            logger.error(f"Auth failed: {e}")

        ctx.finished_at = datetime.now(timezone.utc).isoformat()
        return ctx

    async def load_cookies(self, cookies: list[dict]) -> None:
        """Загрузить сохранённые куки."""
        self._cookies = cookies
        if self._page:
            await self._page.context.add_cookies(cookies)

    def get_cookies(self) -> list[dict]:
        return self._cookies

    async def check_auth(
        self,
        url: str,
        auth_selectors: list[str],
        timeout: float = 5.0,
    ) -> bool:
        """Проверить авторизацию на сайте по селекторам."""
        try:
            page = await self._ensure_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(1)

            for sel in auth_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=timeout * 1000):
                        return True
                except Exception:
                    continue

            return False
        except Exception:
            return False

    async def ensure_auth(
        self,
        url: str,
        auth_selectors: list[str],
        login_url: str = "",
        username_selector: str = "",
        password_selector: str = "",
        submit_selector: str = "",
        success_indicator: str = "",
        username: str = "",
        password: str = "",
    ) -> TaskContext:
        """Проверить авторизацию и если нет — выполнить логин."""
        is_auth = await self.check_auth(url, auth_selectors)
        if is_auth:
            return TaskContext(
                task_name="auth",
                status=TaskStatus.COMPLETED,
                results=[ActionResult(
                    action_type="check_auth",
                    status="success",
                    target=url,
                    message="Already authenticated",
                )],
            )

        # Не авторизованы — нужен логин
        if not login_url or not username or not password:
            return TaskContext(
                task_name="auth",
                status=TaskStatus.FAILED,
                errors=["Not authenticated and no credentials provided"],
            )

        return await self.login(
            login_url=login_url,
            username_selector=username_selector,
            password_selector=password_selector,
            submit_selector=submit_selector,
            success_indicator=success_indicator,
            username=username,
            password=password,
        )

    async def ensure_auth_preset(self, platform: str, username: str = "", password: str = "") -> TaskContext:
        """Авторизация через пресет платформы."""
        preset = self.PLATFORM_PRESETS.get(platform)
        if not preset:
            return TaskContext(
                task_name="auth",
                status=TaskStatus.FAILED,
                errors=[f"Unknown platform preset: {platform}"],
            )

        creds = self._credentials
        username = username or creds.get("username", "")
        password = password or creds.get("password", "")

        return await self.ensure_auth(
            url=preset["auth_url"],
            auth_selectors=preset["auth_selectors"],
            login_url=preset["login_url"],
            username_selector=preset["username_selector"],
            password_selector=preset["password_selector"],
            submit_selector=preset["submit_selector"],
            success_indicator=preset.get("success_indicator", ""),
            username=username,
            password=password,
        )


# ─── Monitoring Task ─────────────────────────────────────────────────────────

class MonitoringTask(BaseTask):
    """Мониторинг изменений на сайтах."""

    def __init__(
        self,
        browser_manager: BrowserManager,
        check_interval: float = 300.0,  # 5 минут
        **kwargs,
    ):
        super().__init__(browser_manager, **kwargs)
        self._interval = check_interval
        self._snapshots: dict[str, str] = {}  # url -> content_hash

    def get_task_name(self) -> str:
        return "monitor"

    def get_steps(self) -> list[TaskStep]:
        return []

    async def check_once(
        self,
        url: str,
        selector: str = "body",
        notify_on_change: bool = True,
    ) -> TaskContext:
        """Однократная проверка изменений."""
        ctx = TaskContext(
            task_name="monitor",
            status=TaskStatus.RUNNING,
            started_at=datetime.now(timezone.utc).isoformat(),
            metadata={"url": url, "selector": selector},
        )

        try:
            page = await self._ensure_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Извлечь контент
            if selector == "body":
                content = await page.evaluate("() => document.body.innerText")
            else:
                el = await page.query_selector(selector)
                content = await el.inner_text() if el else ""

            new_hash = hashlib.md5(content.encode()).hexdigest()
            old_hash = self._snapshots.get(url, "")

            changed = old_hash != "" and new_hash != old_hash
            self._snapshots[url] = new_hash

            ctx.status = TaskStatus.COMPLETED
            ctx.results.append(ActionResult(
                action_type="check",
                status="success",
                target=url,
                metadata={
                    "changed": changed,
                    "old_hash": old_hash,
                    "new_hash": new_hash,
                    "content_length": len(content),
                },
            ))

            if changed and notify_on_change:
                logger.info(f"🔔 Change detected on {url}")

        except Exception as e:
            ctx.status = TaskStatus.FAILED
            ctx.errors.append(str(e))

        ctx.finished_at = datetime.now(timezone.utc).isoformat()
        return ctx

    async def monitor_loop(
        self,
        url: str,
        selector: str = "body",
        max_checks: int = 0,  # 0 = бесконечно
    ) -> None:
        """Цикл мониторинга."""
        check_count = 0
        while max_checks == 0 or check_count < max_checks:
            check_count += 1
            ctx = await self.check_once(url, selector)
            logger.info(f"Monitor check #{check_count}: {ctx.status.value}")
            await asyncio.sleep(self._interval)


# ─── Cross Post Task ─────────────────────────────────────────────────────────

class CrossPostTask(BaseTask):
    """Кросспостинг контента между платформами."""

    PLATFORM_URLS = {
        "habr": "https://habr.com/ru/articles/",
        "vc_ru": "https://vc.ru/",
        "medium": "https://medium.com/",
        "telegraph": "https://telegra.ph/",
    }

    def __init__(
        self,
        browser_manager: BrowserManager,
        credentials: dict[str, dict[str, str]] | None = None,
        **kwargs,
    ):
        super().__init__(browser_manager, **kwargs)
        self._credentials = credentials or {}

    def get_task_name(self) -> str:
        return "crosspost"

    def get_steps(self) -> list[TaskStep]:
        return []

    async def crosspost(
        self,
        title: str,
        content: str,
        source_url: str = "",
        platforms: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[TaskContext]:
        """Опубликовать контент на нескольких платформах."""
        platforms = platforms or ["telegraph"]
        results = []

        for platform in platforms:
            ctx = TaskContext(
                task_name=f"crosspost_{platform}",
                status=TaskStatus.RUNNING,
                started_at=datetime.now(timezone.utc).isoformat(),
                metadata={"platform": platform, "title": title},
            )

            try:
                page = await self._ensure_page()

                if platform == "telegraph":
                    result = await self._post_telegraph(page, title, content)
                elif platform == "habr":
                    result = await self._post_habr(page, title, content, tags)
                elif platform == "vc_ru":
                    result = await self._post_vcru(page, title, content, tags)
                else:
                    result = ActionResult(
                        action_type="publish",
                        status="failed",
                        message=f"Unsupported platform: {platform}",
                    )

                ctx.status = TaskStatus.COMPLETED if result.is_success else TaskStatus.FAILED
                ctx.results.append(result)

            except Exception as e:
                ctx.status = TaskStatus.FAILED
                ctx.errors.append(str(e))

            ctx.finished_at = datetime.now(timezone.utc).isoformat()
            results.append(ctx)

        return results

    async def _post_telegraph(self, page: Page, title: str, content: str) -> ActionResult:
        """Опубликовать на Telegraph."""
        try:
            await page.goto("https://telegra.ph/", wait_until="networkidle", timeout=30000)

            # Заголовок
            title_sel = "[placeholder='Title'], .editor-title, #title"
            try:
                await page.wait_for_selector(title_sel, timeout=5000)
                await page.fill(title_sel, title)
            except Exception:
                pass

            # Контент
            content_sel = "[placeholder='Your story...'], .editor-content, #content"
            try:
                await page.wait_for_selector(content_sel, timeout=5000)
                await page.fill(content_sel, content)
            except Exception:
                pass

            # Publish
            publish_sel = "[type='submit'], .publish-btn, button:has-text('Publish')"
            try:
                await page.click(publish_sel)
                await page.wait_for_url("https://telegra.ph/*", timeout=15000)
            except Exception:
                pass

            return ActionResult(action_type="publish", status="success", target="telegraph")
        except Exception as e:
            return ActionResult(action_type="publish", status="failed", message=str(e))

    async def _post_habr(self, page: Page, title: str, content: str, tags: list[str] | None) -> ActionResult:
        """Опубликовать на Habr (требует авторизации)."""
        try:
            await page.goto("https://habr.com/ru/articles/", wait_until="domcontentloaded", timeout=30000)
            # Habr требует авторизацию — базовая реализация
            # Полная реализация через AuthTask + cookies
            return ActionResult(
                action_type="publish",
                status="skipped",
                target="habr",
                message="Habr publishing requires auth — use AuthTask first",
            )
        except Exception as e:
            return ActionResult(action_type="publish", status="failed", message=str(e))

    async def _post_vcru(self, page: Page, title: str, content: str, tags: list[str] | None) -> ActionResult:
        """Опубликовать на VC.ru (требует авторизации)."""
        try:
            await page.goto("https://vc.ru/", wait_until="domcontentloaded", timeout=30000)
            return ActionResult(
                action_type="publish",
                status="skipped",
                target="vc_ru",
                message="VC.ru publishing requires auth — use AuthTask first",
            )
        except Exception as e:
            return ActionResult(action_type="publish", status="failed", message=str(e))
