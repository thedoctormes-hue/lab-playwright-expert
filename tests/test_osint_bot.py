"""
Tests for OSINT Telegram Bot — поиск аккаунтов по username.

Run: pytest tests/test_osint_bot.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lab_playwright_kit.osint_bot import (
    BotState,
    create_bot,
)


# ─── BotState ────────────────────────────────────────────────────────────────


class TestBotState:
    def test_default_init(self):
        s = BotState()
        assert s.total_searches == 0
        assert s.total_found == 0
        assert s.registry is not None
        assert s.finder is not None

    def test_start_time_is_set(self):
        import time

        before = time.time()
        s = BotState()
        after = time.time()
        assert before <= s.start_time <= after


# ─── create_bot ─────────────────────────────────────────────────────────────


class TestCreateBot:
    def test_returns_bot_and_dp(self):
        with (
            patch("lab_playwright_kit.osint_bot.Bot"),
            patch("lab_playwright_kit.osint_bot.Dispatcher"),
        ):
            bot, dp = create_bot("123456:ABC-DEF")
            assert bot is not None
            assert dp is not None

    def test_bot_token(self):
        with (
            patch("lab_playwright_kit.osint_bot.Bot") as MockBot,
            patch("lab_playwright_kit.osint_bot.Dispatcher"),
        ):
            MockBot.return_value = MagicMock(token="123456:ABC-DEF")
            bot, _ = create_bot("123456:ABC-DEF")
            MockBot.assert_called_once_with(token="123456:ABC-DEF")


# ─── Command Handlers (unit via mocks) ─────────────────────────────────────


class TestCmdStart:
    """Тесты обработчика /start."""

    @pytest.mark.anyio
    async def test_start_sends_help_message(self):
        from lab_playwright_kit.osint_bot import cmd_start

        mock_message = AsyncMock()
        mock_message.text = "/start"
        mock_message.answer = AsyncMock()

        await cmd_start(mock_message)

        mock_message.answer.assert_called_once()
        text = mock_message.answer.call_args[0][0]
        assert "OSINT Finder Bot" in text
        assert "/find" in text


class TestCmdFindParsing:
    """Тесты парсинга аргументов в /find."""

    @pytest.mark.anyio
    async def test_find_no_args_warns(self):
        from lab_playwright_kit.osint_bot import cmd_find

        mock_message = AsyncMock()
        mock_message.text = "/find"
        mock_message.answer = AsyncMock()

        await cmd_find(mock_message)

        mock_message.answer.assert_called_once()
        text = mock_message.answer.call_args[0][0]
        assert "Укажи ник" in text

    @pytest.mark.anyio
    async def test_find_with_username(self):
        """Проверка username передаётся в поиск."""
        from lab_playwright_kit.osint_bot import cmd_find

        mock_message = AsyncMock()
        mock_message.text = "/find testuser"
        mock_message.answer = AsyncMock()
        mock_message.answer.return_value = AsyncMock(edit_text=AsyncMock())

        # Мокаем state.finder.search
        import lab_playwright_kit.osint_bot as bot_module

        mock_report = MagicMock()
        mock_report.found = []
        mock_report.checked = 50
        mock_report.total_found = 0
        mock_report.elapsed_seconds = 1.5
        bot_module.state.finder.search = AsyncMock(return_value=mock_report)

        await cmd_find(mock_message)

        bot_module.state.finder.search.assert_called_once()
        call_kwargs = bot_module.state.finder.search.call_args.kwargs
        assert call_kwargs.get("permute") is False

    @pytest.mark.anyio
    async def test_find_with_tags(self):
        """--tags парсится и передаётся."""
        from lab_playwright_kit.osint_bot import cmd_find

        mock_message = AsyncMock()
        mock_message.text = "/find testuser --tags coding,social"
        mock_message.answer = AsyncMock()
        mock_message.answer.return_value = AsyncMock(edit_text=AsyncMock())

        import lab_playwright_kit.osint_bot as bot_module

        mock_report = MagicMock()
        mock_report.found = []
        mock_report.checked = 10
        mock_report.total_found = 0
        mock_report.elapsed_seconds = 0.5
        bot_module.state.finder.search = AsyncMock(return_value=mock_report)

        await cmd_find(mock_message)

        call_kwargs = bot_module.state.finder.search.call_args.kwargs
        assert call_kwargs.get("tags") == ["coding", "social"]

    @pytest.mark.anyio
    async def test_find_found_results(self):
        """Результаты поиска форматируются корректно."""
        from lab_playwright_kit.osint_bot import cmd_find

        mock_message = AsyncMock()
        mock_message.text = "/find testuser"
        mock_message.answer = AsyncMock()
        status_msg = AsyncMock()
        status_msg.edit_text = AsyncMock()
        mock_message.answer.return_value = status_msg

        import lab_playwright_kit.osint_bot as bot_module

        mock_account = MagicMock()
        mock_account.platform = "GitHub"
        mock_account.url = "https://github.com/testuser"
        mock_account.username = "testuser"
        mock_account.confidence = 0.95
        mock_account.tags = ["coding"]
        mock_report = MagicMock()
        mock_report.found = [mock_account]
        mock_report.checked = 50
        mock_report.total_found = 1
        mock_report.elapsed_seconds = 2.0
        bot_module.state.finder.search = AsyncMock(return_value=mock_report)

        await cmd_find(mock_message)

        status_msg.edit_text.assert_called_once()
        text = status_msg.edit_text.call_args[0][0]
        assert "Найдено" in text
        assert "GitHub" in text

    @pytest.mark.anyio
    async def test_find_not_found(self):
        """Нет результатов — сообщение об этом."""
        from lab_playwright_kit.osint_bot import cmd_find

        mock_message = AsyncMock()
        mock_message.text = "/find nonexistent_user_xyz"
        mock_message.answer = AsyncMock()
        status_msg = AsyncMock()
        status_msg.edit_text = AsyncMock()
        mock_message.answer.return_value = status_msg

        import lab_playwright_kit.osint_bot as bot_module

        mock_report = MagicMock()
        mock_report.found = []
        mock_report.checked = 50
        mock_report.total_found = 0
        mock_report.elapsed_seconds = 3.0
        bot_module.state.finder.search = AsyncMock(return_value=mock_report)

        await cmd_find(mock_message)

        text = status_msg.edit_text.call_args[0][0]
        assert "не найден" in text

    @pytest.mark.anyio
    async def test_find_exception_handling(self):
        """Ошибка при поиске — сообщение об ошибке."""
        from lab_playwright_kit.osint_bot import cmd_find

        mock_message = AsyncMock()
        mock_message.text = "/find testuser"
        mock_message.answer = AsyncMock()
        status_msg = AsyncMock()
        status_msg.edit_text = AsyncMock()
        mock_message.answer.return_value = status_msg

        import lab_playwright_kit.osint_bot as bot_module

        bot_module.state.finder.search = AsyncMock(side_effect=Exception("network error"))

        await cmd_find(mock_message)

        text = status_msg.edit_text.call_args[0][0]
        assert "Ошибка" in text


class TestCmdPlatforms:
    """Тесты обработчика /platforms."""

    @pytest.mark.anyio
    async def test_platforms_sends_list(self):
        from lab_playwright_kit.osint_bot import cmd_platforms

        mock_message = AsyncMock()
        mock_message.answer = AsyncMock()

        # Мокаем registry
        import lab_playwright_kit.osint_bot as bot_module

        mock_platform = MagicMock()
        mock_platform.name = "TestPlatform"
        mock_platform.disabled = False
        mock_platform.tags = ["social"]
        bot_module.state.registry.all = MagicMock(return_value=[mock_platform])

        await cmd_platforms(mock_message)

        mock_message.answer.assert_called_once()
        text = mock_message.answer.call_args[0][0]
        assert "Платформы" in text
        assert "social" in text


class TestCmdStats:
    """Тесты обработчика /stats."""

    @pytest.mark.anyio
    async def test_stats_sends_report(self):
        from lab_playwright_kit.osint_bot import cmd_stats

        mock_message = AsyncMock()
        mock_message.answer = AsyncMock()

        import lab_playwright_kit.osint_bot as bot_module

        bot_module.state.total_searches = 5
        bot_module.state.total_found = 12
        bot_module.state.registry.count = MagicMock(return_value=50)

        await cmd_stats(mock_message)

        mock_message.answer.assert_called_once()
        text = mock_message.answer.call_args[0][0]
        assert "5" in text  # searches
        assert "12" in text  # found
        assert "50" in text  # platforms
