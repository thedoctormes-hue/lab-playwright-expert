"""
Extended tests for action_engine.py — ActionEngine, ActionResult, ActionStep.

Covers: enums, dataclasses, ActionEngine methods (mocked page).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from lab_playwright_kit.action_engine import (
    ActionEngine,
    ActionResult,
    ActionResultStatus,
    ActionStep,
    ActionType,
)


# ─── Enum Tests ──────────────────────────────────────────────────────────────


class TestActionType:
    def test_all_types(self):
        assert ActionType.LIKE.value == "like"
        assert ActionType.REPOST.value == "repost"
        assert ActionType.COMMENT.value == "comment"
        assert ActionType.FOLLOW.value == "follow"
        assert ActionType.UNFOLLOW.value == "unfollow"
        assert ActionType.VIEW.value == "view"
        assert ActionType.CLICK.value == "click"
        assert ActionType.TYPE.value == "type"
        assert ActionType.SCROLL.value == "scroll"
        assert ActionType.NAVIGATE.value == "navigate"
        assert ActionType.WAIT.value == "wait"
        assert ActionType.SCREENSHOT.value == "screenshot"
        assert ActionType.CUSTOM.value == "custom"


class TestActionResultStatus:
    def test_all_statuses(self):
        assert ActionResultStatus.SUCCESS.value == "success"
        assert ActionResultStatus.FAILED.value == "failed"
        assert ActionResultStatus.SKIPPED.value == "skipped"
        assert ActionResultStatus.BLOCKED.value == "blocked"
        assert ActionResultStatus.RATE_LIMITED.value == "rate_limited"
        assert ActionResultStatus.CAPTCHA.value == "captcha"


# ─── ActionResult Tests ──────────────────────────────────────────────────────


class TestActionResult:
    def test_defaults(self):
        r = ActionResult(action_type="like")
        assert r.action_type == "like"
        assert r.status == ActionResultStatus.SUCCESS
        assert r.target == ""
        assert r.message == ""
        assert r.duration_ms == 0
        assert r.metadata == {}

    def test_is_success(self):
        r = ActionResult(action_type="like", status=ActionResultStatus.SUCCESS)
        assert r.is_success is True

    def test_is_not_success(self):
        r = ActionResult(action_type="like", status=ActionResultStatus.FAILED)
        assert r.is_success is False

    def test_is_not_success_skipped(self):
        r = ActionResult(action_type="like", status=ActionResultStatus.SKIPPED)
        assert r.is_success is False


# ─── ActionStep Tests ────────────────────────────────────────────────────────


class TestActionStep:
    def test_defaults(self):
        step = ActionStep(action_type="navigate")
        assert step.action_type == "navigate"
        assert step.params == {}
        assert step.condition is None
        assert step.on_fail == "continue"
        assert step.max_retries == 3
        assert step.retry_delay_ms == 5000

    def test_custom(self):
        step = ActionStep(
            action_type="click",
            params={"selector": ".btn"},
            on_fail="abort",
            max_retries=5,
        )
        assert step.params["selector"] == ".btn"
        assert step.on_fail == "abort"
        assert step.max_retries == 5


# ─── ActionEngine Tests ──────────────────────────────────────────────────────


class TestActionEngine:
    def test_init_defaults(self):
        page = MagicMock()
        engine = ActionEngine(page)
        assert engine.page is page
        assert engine.results == []
        assert engine.success_count == 0
        assert engine.fail_count == 0

    def test_init_with_profile(self):
        page = MagicMock()
        engine = ActionEngine(page, profile="social_media", seed=42)
        assert engine.page is page

    def test_results_property(self):
        page = MagicMock()
        engine = ActionEngine(page)
        # Simulate adding results
        r1 = ActionResult(action_type="navigate", status=ActionResultStatus.SUCCESS)
        r2 = ActionResult(action_type="like", status=ActionResultStatus.FAILED)
        engine._results = [r1, r2]
        assert len(engine.results) == 2
        assert engine.success_count == 1
        assert engine.fail_count == 1

    @pytest.mark.asyncio
    async def test_navigate_success(self):
        page = MagicMock()
        page.goto = AsyncMock()
        engine = ActionEngine(page)
        engine.behavior = MagicMock()
        engine.behavior.wait_between_actions = AsyncMock()

        result = await engine.navigate("https://example.com")
        assert result.action_type == ActionType.NAVIGATE
        assert result.status == ActionResultStatus.SUCCESS
        assert result.target == "https://example.com"
        page.goto.assert_called_once()

    @pytest.mark.asyncio
    async def test_navigate_failure(self):
        page = MagicMock()
        page.goto = AsyncMock(side_effect=Exception("Timeout"))
        engine = ActionEngine(page)
        engine.behavior = MagicMock()

        result = await engine.navigate("https://example.com")
        assert result.status == ActionResultStatus.FAILED
        assert "Timeout" in result.message

    @pytest.mark.asyncio
    async def test_wait_for_content_success(self):
        page = MagicMock()
        page.wait_for_selector = AsyncMock()
        engine = ActionEngine(page)

        result = await engine.wait_for_content("article")
        assert result.action_type == ActionType.WAIT
        assert result.status == ActionResultStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_wait_for_content_failure(self):
        page = MagicMock()
        page.wait_for_selector = AsyncMock(side_effect=Exception("Not found"))
        engine = ActionEngine(page)

        result = await engine.wait_for_content(".missing")
        assert result.status == ActionResultStatus.FAILED

    @pytest.mark.asyncio
    async def test_like_button_not_found(self):
        page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.count = AsyncMock(return_value=0)
        page.locator = MagicMock(return_value=mock_locator)
        engine = ActionEngine(page)
        engine.behavior = MagicMock()

        result = await engine.like()
        assert result.status == ActionResultStatus.SKIPPED
        assert "not found" in result.message

    @pytest.mark.asyncio
    async def test_like_success(self):
        page = MagicMock()
        mock_btn = MagicMock()
        mock_btn.count = AsyncMock(return_value=1)
        page.locator = MagicMock(return_value=mock_btn)
        engine = ActionEngine(page)
        engine.behavior = MagicMock()
        engine.behavior.scroll_to_element = AsyncMock()
        engine.behavior.click = AsyncMock()

        result = await engine.like()
        assert result.status == ActionResultStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_click_element_not_found(self):
        page = MagicMock()
        mock_el = MagicMock()
        mock_el.count = AsyncMock(return_value=0)
        page.locator = MagicMock(return_value=mock_el)
        engine = ActionEngine(page)
        engine.behavior = MagicMock()

        result = await engine.click_element(".missing")
        assert result.status == ActionResultStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_click_element_success(self):
        page = MagicMock()
        mock_el = MagicMock()
        mock_el.count = AsyncMock(return_value=1)
        page.locator = MagicMock(return_value=mock_el)
        engine = ActionEngine(page)
        engine.behavior = MagicMock()
        engine.behavior.scroll_to_element = AsyncMock()
        engine.behavior.click = AsyncMock()

        result = await engine.click_element(".btn")
        assert result.status == ActionResultStatus.SUCCESS
        assert result.target == ".btn"

    @pytest.mark.asyncio
    async def test_type_in_field_not_found(self):
        page = MagicMock()
        mock_field = MagicMock()
        mock_field.count = AsyncMock(return_value=0)
        page.locator = MagicMock(return_value=mock_field)
        engine = ActionEngine(page)
        engine.behavior = MagicMock()

        result = await engine.type_in_field(".input", "text")
        assert result.status == ActionResultStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_type_in_field_success(self):
        page = MagicMock()
        mock_field = MagicMock()
        mock_field.count = AsyncMock(return_value=1)
        mock_field.fill = AsyncMock()
        page.locator = MagicMock(return_value=mock_field)
        engine = ActionEngine(page)
        engine.behavior = MagicMock()
        engine.behavior.click = AsyncMock()
        engine.behavior.type_like_human = AsyncMock()

        result = await engine.type_in_field(".input", "hello")
        assert result.status == ActionResultStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_follow_not_found(self):
        page = MagicMock()
        mock_btn = MagicMock()
        mock_btn.count = AsyncMock(return_value=0)
        page.locator = MagicMock(return_value=mock_btn)
        engine = ActionEngine(page)
        engine.behavior = MagicMock()

        result = await engine.follow()
        assert result.status == ActionResultStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_follow_success(self):
        page = MagicMock()
        mock_btn = MagicMock()
        mock_btn.count = AsyncMock(return_value=1)
        page.locator = MagicMock(return_value=mock_btn)
        engine = ActionEngine(page)
        engine.behavior = MagicMock()
        engine.behavior.scroll_to_element = AsyncMock()
        engine.behavior.click = AsyncMock()

        result = await engine.follow()
        assert result.status == ActionResultStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_repost_not_found(self):
        page = MagicMock()
        mock_btn = MagicMock()
        mock_btn.count = AsyncMock(return_value=0)
        page.locator = MagicMock(return_value=mock_btn)
        engine = ActionEngine(page)
        engine.behavior = MagicMock()

        result = await engine.repost()
        assert result.status == ActionResultStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_comment_input_not_found(self):
        page = MagicMock()
        mock_input = MagicMock()
        mock_input.count = AsyncMock(return_value=0)
        page.locator = MagicMock(return_value=mock_input)
        engine = ActionEngine(page)
        engine.behavior = MagicMock()

        result = await engine.comment("Nice post!")
        assert result.status == ActionResultStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_view_content(self):
        page = MagicMock()
        engine = ActionEngine(page)
        engine.behavior = MagicMock()
        engine.behavior.read_page = AsyncMock()

        result = await engine.view_content(duration_seconds=0.1)
        assert result.action_type == ActionType.VIEW
        assert result.status == ActionResultStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_scroll_and_read(self):
        page = MagicMock()
        engine = ActionEngine(page)
        engine.behavior = MagicMock()
        engine.behavior.read_page = AsyncMock()

        result = await engine.scroll_and_read(pages=1.0)
        assert result.action_type == ActionType.SCROLL
        assert result.status == ActionResultStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_execute_chain_empty(self):
        page = MagicMock()
        engine = ActionEngine(page)
        results = await engine.execute_chain([])
        assert results == []

    @pytest.mark.asyncio
    async def test_execute_chain_navigate(self):
        page = MagicMock()
        page.goto = AsyncMock()
        engine = ActionEngine(page)
        engine.behavior = MagicMock()
        engine.behavior.wait_between_actions = AsyncMock()

        steps = [ActionStep(action_type="navigate", params={"url": "https://example.com"})]
        results = await engine.execute_chain(steps)
        assert len(results) == 1
        assert results[0].status == ActionResultStatus.SUCCESS
