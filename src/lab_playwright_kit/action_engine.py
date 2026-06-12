"""
Action Engine — выполнение действий на сайтах.

Унифицированный API для действий на разных платформах:
  - Лайки, репосты, подписки
  - Комментарии
  - Просмотры
  - Навигация
  - Формы

Каждое действие обёрнуто в human behavior — рандомные задержки,
реалистичные движения мыши, естественный набор текста.

Использование:
    >>> engine = ActionEngine(page, behavior_profile="social_media")
    >>> await engine.like_post("https://twitter.com/user/status/123")
    >>> await engine.comment("https://habr.com/post/123", "Отличная статья!")
    >>> await engine.follow("https://twitter.com/target_user")
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger
from playwright.async_api import Page

from .human_behavior import HumanBehaviorEngine


class ActionType(str, Enum):
    """Типы действий."""
    LIKE = "like"
    REPOST = "repost"
    COMMENT = "comment"
    FOLLOW = "follow"
    UNFOLLOW = "unfollow"
    VIEW = "view"
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    NAVIGATE = "navigate"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    CUSTOM = "custom"


class ActionResultStatus(str, Enum):
    """Результат действия."""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    RATE_LIMITED = "rate_limited"
    CAPTCHA = "captcha"


@dataclass
class ActionResult:
    """Результат выполнения действия."""
    action_type: str
    status: str = ActionResultStatus.SUCCESS
    target: str = ""
    message: str = ""
    duration_ms: float = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.status == ActionResultStatus.SUCCESS


@dataclass
class ActionStep:
    """Шаг в цепочке действий."""
    action_type: str
    params: dict[str, Any] = field(default_factory=dict)
    condition: str | None = None  # условие выполнения
    on_fail: str = "continue"  # continue, abort, retry
    max_retries: int = 3
    retry_delay_ms: int = 5000


class ActionEngine:
    """Движок действий на сайтах.

    Выполняет действия с человечным поведением:
    рандомные задержки, реалистичные движения мыши,
    естественный набор текста.

    Использование:
        >>> engine = ActionEngine(page, profile="social_media")
        >>> result = await engine.navigate("https://twitter.com")
        >>> result = await engine.wait_for_content("article")
        >>> result = await engine.scroll_and_read(pages=3)
    """

    def __init__(
        self,
        page: Page,
        profile: str = "social_media",
        seed: int | None = None,
    ):
        self.page = page
        self.behavior = HumanBehaviorEngine(page, profile=profile, seed=seed)
        self._action_count = 0
        self._results: list[ActionResult] = []

    async def navigate(
        self,
        url: str,
        wait_for: str = "domcontentloaded",
        timeout: int = 30000,
    ) -> ActionResult:
        """Навигация на URL с человечным поведением.

        Args:
            url: Целевой URL
            wait_for: Событие ожидания (domcontentloaded, networkidle, load)
            timeout: Таймаут в мс

        Returns:
            ActionResult
        """
        start = time.monotonic()
        try:
            await self.page.goto(url, wait_until=wait_for, timeout=timeout)

            # Небольшая пауза после загрузки (как реальный юзер)
            await self.behavior.wait_between_actions()

            duration = (time.monotonic() - start) * 1000
            result = ActionResult(
                action_type=ActionType.NAVIGATE,
                status=ActionResultStatus.SUCCESS,
                target=url,
                duration_ms=duration,
            )
        except Exception as e:
            duration = (time.monotonic() - start) * 1000
            result = ActionResult(
                action_type=ActionType.NAVIGATE,
                status=ActionResultStatus.FAILED,
                target=url,
                message=str(e),
                duration_ms=duration,
            )

        self._results.append(result)
        return result

    async def wait_for_content(
        self,
        selector: str,
        timeout: int = 10000,
    ) -> ActionResult:
        """Подождать появления контента на странице.

        Args:
            selector: CSS селектор элемента
            timeout: Таймаут в мс

        Returns:
            ActionResult
        """
        start = time.monotonic()
        try:
            await self.page.wait_for_selector(selector, timeout=timeout)
            duration = (time.monotonic() - start) * 1000
            result = ActionResult(
                action_type=ActionType.WAIT,
                status=ActionResultStatus.SUCCESS,
                target=selector,
                duration_ms=duration,
            )
        except Exception as e:
            duration = (time.monotonic() - start) * 1000
            result = ActionResult(
                action_type=ActionType.WAIT,
                status=ActionResultStatus.FAILED,
                target=selector,
                message=str(e),
                duration_ms=duration,
            )

        self._results.append(result)
        return result

    async def like(
        self,
        selector: str = '[data-testid="like"], [aria-label="Like"], .like-button, .heart',
    ) -> ActionResult:
        """Поставить лайк.

        Пытается найти кнопку лайка по нескольким селекторам.

        Args:
            selector: CSS селектор кнопки лайка

        Returns:
            ActionResult
        """
        start = time.monotonic()

        try:
            # Ищем кнопку лайка
            like_btn = self.page.locator(selector).first
            if await like_btn.count() == 0:
                # Пробуем альтернативные селекторы
                alt_selectors = [
                    '[data-testid="like"]',
                    '[aria-label="Like"]',
                    '[aria-label="Нравится"]',
                    '.like',
                    '.heart',
                    'button:has-text("Like")',
                    'button:has-text("Нравится")',
                ]
                for sel in alt_selectors:
                    like_btn = self.page.locator(sel).first
                    if await like_btn.count() > 0:
                        break

            if await like_btn.count() == 0:
                result = ActionResult(
                    action_type=ActionType.LIKE,
                    status=ActionResultStatus.SKIPPED,
                    message="Like button not found",
                )
                self._results.append(result)
                return result

            # Скроллим к кнопке и кликаем с человечным поведением
            await self.behavior.scroll_to_element(like_btn)
            await self.behavior.click(locator=like_btn)

            duration = (time.monotonic() - start) * 1000
            result = ActionResult(
                action_type=ActionType.LIKE,
                status=ActionResultStatus.SUCCESS,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.monotonic() - start) * 1000
            result = ActionResult(
                action_type=ActionType.LIKE,
                status=ActionResultStatus.FAILED,
                message=str(e),
                duration_ms=duration,
            )

        self._results.append(result)
        return result

    async def comment(
        self,
        text: str,
        input_selector: str = '[data-testid="tweetTextarea"], textarea, [contenteditable="true"], .comment-input',
        submit_selector: str = '[data-testid="tweetButton"], [type="submit"], .comment-submit, button:has-text("Reply")',
    ) -> ActionResult:
        """Написать комментарий.

        Args:
            text: Текст комментария
            input_selector: Селектор поля ввода
            submit_selector: Селектор кнопки отправки

        Returns:
            ActionResult
        """
        start = time.monotonic()

        try:
            # Находим поле ввода
            input_el = self.page.locator(input_selector).first
            if await input_el.count() == 0:
                result = ActionResult(
                    action_type=ActionType.COMMENT,
                    status=ActionResultStatus.SKIPPED,
                    message="Comment input not found",
                )
                self._results.append(result)
                return result

            # Кликаем на поле и печатаем текст
            await self.behavior.click(locator=input_el)
            await asyncio.sleep(0.5)

            # Набираем текст с человечной скоростью
            await self.behavior.type_like_human(text, locator=input_el)

            # Пауза перед отправкой (как будто проверяем текст)
            await asyncio.sleep(1.0)

            # Отправляем
            submit_btn = self.page.locator(submit_selector).first
            if await submit_btn.count() > 0:
                await self.behavior.click(locator=submit_btn)
            else:
                # Enter как fallback
                await self.page.keyboard.press("Enter")

            duration = (time.monotonic() - start) * 1000
            result = ActionResult(
                action_type=ActionType.COMMENT,
                status=ActionResultStatus.SUCCESS,
                target=text[:50],
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.monotonic() - start) * 1000
            result = ActionResult(
                action_type=ActionType.COMMENT,
                status=ActionResultStatus.FAILED,
                message=str(e),
                duration_ms=duration,
            )

        self._results.append(result)
        return result

    async def follow(
        self,
        selector: str = '[data-testid="follow"], button:has-text("Follow"), button:has-text("Подписаться")',
    ) -> ActionResult:
        """Подписаться на пользователя/канал.

        Args:
            selector: Селектор кнопки подписки

        Returns:
            ActionResult
        """
        start = time.monotonic()

        try:
            follow_btn = self.page.locator(selector).first
            if await follow_btn.count() == 0:
                result = ActionResult(
                    action_type=ActionType.FOLLOW,
                    status=ActionResultStatus.SKIPPED,
                    message="Follow button not found",
                )
                self._results.append(result)
                return result

            await self.behavior.scroll_to_element(follow_btn)
            await self.behavior.click(locator=follow_btn)

            duration = (time.monotonic() - start) * 1000
            result = ActionResult(
                action_type=ActionType.FOLLOW,
                status=ActionResultStatus.SUCCESS,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.monotonic() - start) * 1000
            result = ActionResult(
                action_type=ActionType.FOLLOW,
                status=ActionResultStatus.FAILED,
                message=str(e),
                duration_ms=duration,
            )

        self._results.append(result)
        return result

    async def repost(
        self,
        selector: str = '[data-testid="retweet"], [aria-label="Repost"], .repost-button',
    ) -> ActionResult:
        """Репостнуть запись.

        Args:
            selector: Селектор кнопки репоста

        Returns:
            ActionResult
        """
        start = time.monotonic()

        try:
            repost_btn = self.page.locator(selector).first
            if await repost_btn.count() == 0:
                result = ActionResult(
                    action_type=ActionType.REPOST,
                    status=ActionResultStatus.SKIPPED,
                    message="Repost button not found",
                )
                self._results.append(result)
                return result

            await self.behavior.scroll_to_element(repost_btn)
            await self.behavior.click(locator=repost_btn)

            # Подтверждение репоста (если есть)
            await asyncio.sleep(0.5)
            confirm = self.page.locator('[data-testid="retweetConfirm"], button:has-text("Repost")').first
            if await confirm.count() > 0:
                await self.behavior.click(locator=confirm)

            duration = (time.monotonic() - start) * 1000
            result = ActionResult(
                action_type=ActionType.REPOST,
                status=ActionResultStatus.SUCCESS,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.monotonic() - start) * 1000
            result = ActionResult(
                action_type=ActionType.REPOST,
                status=ActionResultStatus.FAILED,
                message=str(e),
                duration_ms=duration,
            )

        self._results.append(result)
        return result

    async def view_content(
        self,
        duration_seconds: float = 10.0,
    ) -> ActionResult:
        """Просмотр контента с имитацией чтения.

        Args:
            duration_seconds: Длительность просмотра

        Returns:
            ActionResult
        """
        start = time.monotonic()

        try:
            await self.behavior.read_page()

            # Дополнительная пауза
            remaining = duration_seconds - (time.monotonic() - start)
            if remaining > 0:
                await asyncio.sleep(remaining)

            duration = (time.monotonic() - start) * 1000
            result = ActionResult(
                action_type=ActionType.VIEW,
                status=ActionResultStatus.SUCCESS,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.monotonic() - start) * 1000
            result = ActionResult(
                action_type=ActionType.VIEW,
                status=ActionResultStatus.FAILED,
                message=str(e),
                duration_ms=duration,
            )

        self._results.append(result)
        return result

    async def scroll_and_read(
        self,
        pages: float = 2.0,
    ) -> ActionResult:
        """Скроллить и читать страницу.

        Args:
            pages: Количество страниц для скролла

        Returns:
            ActionResult
        """
        start = time.monotonic()

        try:
            await self.behavior.read_page()
            duration = (time.monotonic() - start) * 1000
            result = ActionResult(
                action_type=ActionType.SCROLL,
                status=ActionResultStatus.SUCCESS,
                duration_ms=duration,
            )
        except Exception as e:
            duration = (time.monotonic() - start) * 1000
            result = ActionResult(
                action_type=ActionType.SCROLL,
                status=ActionResultStatus.FAILED,
                message=str(e),
                duration_ms=duration,
            )

        self._results.append(result)
        return result

    async def click_element(
        self,
        selector: str,
    ) -> ActionResult:
        """Кликнуть по элементу с человечным поведением.

        Args:
            selector: CSS селектор

        Returns:
            ActionResult
        """
        start = time.monotonic()

        try:
            el = self.page.locator(selector).first
            if await el.count() == 0:
                result = ActionResult(
                    action_type=ActionType.CLICK,
                    status=ActionResultStatus.SKIPPED,
                    target=selector,
                    message="Element not found",
                )
                self._results.append(result)
                return result

            await self.behavior.scroll_to_element(el)
            await self.behavior.click(locator=el)

            duration = (time.monotonic() - start) * 1000
            result = ActionResult(
                action_type=ActionType.CLICK,
                status=ActionResultStatus.SUCCESS,
                target=selector,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.monotonic() - start) * 1000
            result = ActionResult(
                action_type=ActionType.CLICK,
                status=ActionResultStatus.FAILED,
                target=selector,
                message=str(e),
                duration_ms=duration,
            )

        self._results.append(result)
        return result

    async def type_in_field(
        self,
        selector: str,
        text: str,
        clear_first: bool = True,
    ) -> ActionResult:
        """Набрать текст в поле с человечной скоростью.

        Args:
            selector: Селектор поля ввода
            text: Текст
            clear_first: Очистить поле перед вводом

        Returns:
            ActionResult
        """
        start = time.monotonic()

        try:
            field = self.page.locator(selector).first
            if await field.count() == 0:
                result = ActionResult(
                    action_type=ActionType.TYPE,
                    status=ActionResultStatus.SKIPPED,
                    target=selector,
                    message="Field not found",
                )
                self._results.append(result)
                return result

            await self.behavior.click(locator=field)
            if clear_first:
                await field.fill("")

            await self.behavior.type_like_human(text, locator=field)

            duration = (time.monotonic() - start) * 1000
            result = ActionResult(
                action_type=ActionType.TYPE,
                status=ActionResultStatus.SUCCESS,
                target=selector,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.monotonic() - start) * 1000
            result = ActionResult(
                action_type=ActionType.TYPE,
                status=ActionResultStatus.FAILED,
                target=selector,
                message=str(e),
                duration_ms=duration,
            )

        self._results.append(result)
        return result

    async def execute_chain(
        self,
        steps: list[ActionStep],
    ) -> list[ActionResult]:
        """Выполнить цепочку действий.

        Args:
            steps: Список ActionStep

        Returns:
            Список ActionResult для каждого шага
        """
        results = []

        for i, step in enumerate(steps):
            logger.info(f"Action chain step {i+1}/{len(steps)}: {step.action_type}")

            result = await self._execute_step(step)
            results.append(result)

            if not result.is_success:
                if step.on_fail == "abort":
                    logger.warning(f"Chain aborted at step {i+1}: {result.message}")
                    break
                elif step.on_fail == "retry":
                    for retry in range(step.max_retries):
                        logger.info(f"Retry {retry+1}/{step.max_retries}")
                        await asyncio.sleep(step.retry_delay_ms / 1000)
                        result = await self._execute_step(step)
                        results[-1] = result
                        if result.is_success:
                            break

            # Пауза между шагами
            await self.behavior.wait_between_actions()

        return results

    async def _execute_step(self, step: ActionStep) -> ActionResult:
        """Выполнить один шаг цепочки."""
        action_map = {
            ActionType.NAVIGATE: lambda: self.navigate(**step.params),
            ActionType.CLICK: lambda: self.click_element(**step.params),
            ActionType.TYPE: lambda: self.type_in_field(**step.params),
            ActionType.LIKE: lambda: self.like(**step.params),
            ActionType.COMMENT: lambda: self.comment(**step.params),
            ActionType.FOLLOW: lambda: self.follow(**step.params),
            ActionType.REPOST: lambda: self.repost(**step.params),
            ActionType.VIEW: lambda: self.view_content(**step.params),
            ActionType.SCROLL: lambda: self.scroll_and_read(**step.params),
            ActionType.WAIT: lambda: self.wait_for_content(**step.params),
        }

        handler = action_map.get(step.action_type)
        if handler:
            return await handler()

        return ActionResult(
            action_type=step.action_type,
            status=ActionResultStatus.FAILED,
            message=f"Unknown action type: {step.action_type}",
        )

    @property
    def results(self) -> list[ActionResult]:
        """Все результаты действий."""
        return list(self._results)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self._results if r.is_success)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self._results if not r.is_success)
