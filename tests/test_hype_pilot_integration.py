"""
Тесты для Hype Pilot Integration.
"""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from lab_playwright_kit.task_template import TaskStatus


# ─── HypePilotPublisher ──────────────────────────────────────────────────────

class TestHypePilotPublisher:
    def test_creation(self):
        from scripts.hype_pilot_integration import HypePilotPublisher
        pub = HypePilotPublisher(headless=True)
        assert pub._headless is True

    def test_creation_visible(self):
        from scripts.hype_pilot_integration import HypePilotPublisher
        pub = HypePilotPublisher(headless=False)
        assert pub._headless is False

    @pytest.mark.asyncio
    async def test_login(self):
        from scripts.hype_pilot_integration import HypePilotPublisher

        pub = HypePilotPublisher()

        mock_ctx = MagicMock()
        mock_ctx.status = TaskStatus.COMPLETED
        mock_ctx.get_context = AsyncMock()
        mock_ctx.new_page = AsyncMock()

        with patch("scripts.hype_pilot_integration.BrowserManager") as MockBM:
            mock_bm = AsyncMock()
            mock_bm.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_bm.__aexit__ = AsyncMock(return_value=False)
            MockBM.return_value = mock_bm

            with patch("scripts.hype_pilot_integration.AuthTask") as MockAuth:
                mock_auth = AsyncMock()
                mock_auth.login = AsyncMock(return_value=MagicMock(status=TaskStatus.COMPLETED))
                mock_auth.get_cookies = MagicMock(return_value=[{"name": "test"}])
                MockAuth.return_value = mock_auth

                ctx = await pub.login("habr")
                assert ctx is not None

    @pytest.mark.asyncio
    async def test_publish(self):
        from scripts.hype_pilot_integration import HypePilotPublisher

        pub = HypePilotPublisher()

        with patch("scripts.hype_pilot_integration.BrowserManager") as MockBM:
            mock_ctx = MagicMock()
            mock_bm = AsyncMock()
            mock_bm.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_bm.__aexit__ = AsyncMock(return_value=False)
            MockBM.return_value = mock_bm

            with patch("scripts.hype_pilot_integration.ContentPublishTask") as MockTask:
                mock_task = AsyncMock()
                mock_task.publish = AsyncMock(return_value=MagicMock(status=TaskStatus.COMPLETED))
                MockTask.return_value = mock_task

                ctx = await pub.publish("habr", "Test Title", "Test Content")
                assert ctx is not None

    @pytest.mark.asyncio
    async def test_crosspost(self):
        from scripts.hype_pilot_integration import HypePilotPublisher

        pub = HypePilotPublisher()

        with patch("scripts.hype_pilot_integration.BrowserManager") as MockBM:
            mock_ctx = MagicMock()
            mock_bm = AsyncMock()
            mock_bm.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_bm.__aexit__ = AsyncMock(return_value=False)
            MockBM.return_value = mock_bm

            with patch("scripts.hype_pilot_integration.CrossPostTask") as MockTask:
                mock_task = AsyncMock()
                mock_task.crosspost = AsyncMock(return_value=[
                    MagicMock(status=TaskStatus.COMPLETED, metadata={"platform": "telegraph"}),
                ])
                MockTask.return_value = mock_task

                results = await pub.crosspost("Title", "Content", ["telegraph"])
                assert len(results) == 1

    @pytest.mark.asyncio
    async def test_collect_data(self):
        from scripts.hype_pilot_integration import HypePilotPublisher

        pub = HypePilotPublisher()

        with patch("scripts.hype_pilot_integration.BrowserManager") as MockBM:
            mock_ctx = MagicMock()
            mock_bm = AsyncMock()
            mock_bm.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_bm.__aexit__ = AsyncMock(return_value=False)
            MockBM.return_value = mock_bm

            with patch("scripts.hype_pilot_integration.DataCollectionTask") as MockTask:
                mock_task = AsyncMock()
                mock_task.collect = AsyncMock(return_value=[
                    MagicMock(status=TaskStatus.COMPLETED, metadata={"url": "https://example.com"}),
                ])
                MockTask.return_value = mock_task

                results = await pub.collect_data(["https://example.com"], "news")
                assert len(results) == 1

    @pytest.mark.asyncio
    async def test_monitor(self):
        from scripts.hype_pilot_integration import HypePilotPublisher

        pub = HypePilotPublisher()

        with patch("scripts.hype_pilot_integration.BrowserManager") as MockBM:
            mock_ctx = MagicMock()
            mock_bm = AsyncMock()
            mock_bm.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_bm.__aexit__ = AsyncMock(return_value=False)
            MockBM.return_value = mock_bm

            with patch("scripts.hype_pilot_integration.MonitoringTask") as MockTask:
                mock_task = AsyncMock()
                mock_task.check_once = AsyncMock(return_value=MagicMock(
                    status=TaskStatus.COMPLETED,
                    results=[MagicMock(metadata={"changed": False})],
                ))
                MockTask.return_value = mock_task

                ctx = await pub.monitor("https://example.com")
                assert ctx is not None


# ─── CLI helpers ──────────────────────────────────────────────────────────────

class TestCLIHelpers:
    def test_run_browser_publish_success(self):
        from scripts.hype_pilot_integration import run_browser_publish

        with patch("scripts.hype_pilot_integration.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="https://habr.com/ru/articles/123\n",
                stderr="",
            )
            url = run_browser_publish("habr", "Title", "Content")
            assert url == "https://habr.com/ru/articles/123"

    def test_run_browser_publish_failure(self):
        from scripts.hype_pilot_integration import run_browser_publish

        with patch("scripts.hype_pilot_integration.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Error",
            )
            url = run_browser_publish("habr", "Title", "Content")
            assert url == ""

    def test_run_browser_login_success(self):
        from scripts.hype_pilot_integration import run_browser_login

        with patch("scripts.hype_pilot_integration.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert run_browser_login("habr") is True

    def test_run_browser_login_failure(self):
        from scripts.hype_pilot_integration import run_browser_login

        with patch("scripts.hype_pilot_integration.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert run_browser_login("habr") is False
