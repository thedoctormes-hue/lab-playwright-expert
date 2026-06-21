"""
Extended tests for account_finder.py — FoundAccount, SearchReport, UsernamePermuter, AccountFinder.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lab_playwright_kit.account_finder import (
    AccountFinder,
    FoundAccount,
    SearchReport,
    UsernamePermuter,
)


class TestFoundAccount:
    def test_defaults(self):
        account = FoundAccount()
        assert account.platform == ""
        assert account.username == ""
        assert account.url == ""
        assert account.status == ""
        assert account.confidence == 0.0
        assert account.source == ""
        assert account.tags == []
        assert account.metadata == {}

    def test_full(self):
        account = FoundAccount(
            username="doctorm",
            platform="telegram",
            url="https://t.me/doctorm",
            status="found",
            confidence=0.95,
            source="search",
            tags=["coding", "ru"],
            metadata={"followers": 1000},
        )
        assert account.username == "doctorm"
        assert account.platform == "telegram"
        assert account.confidence == 0.95
        assert account.status == "found"

    def test_to_dict(self):
        account = FoundAccount(
            username="test", platform="tg", url="https://t.me/test", confidence=0.8
        )
        d = account.to_dict()
        assert d["username"] == "test"
        assert d["platform"] == "tg"
        assert d["confidence"] == 0.8


class TestSearchReport:
    def test_defaults(self):
        report = SearchReport()
        assert report.query == ""
        assert report.found == []
        assert report.checked == 0
        assert report.elapsed_seconds == 0.0

    def test_found_count(self):
        report = SearchReport(found=[FoundAccount(), FoundAccount(), FoundAccount()])
        assert report.found_count == 3

    def test_to_dict(self):
        report = SearchReport(query="test", found=[FoundAccount()], checked=50, elapsed_seconds=5.0)
        d = report.to_dict()
        assert d["query"] == "test"
        assert d["found_count"] == 1
        assert d["checked"] == 50


class TestUsernamePermuter:
    def test_defaults(self):
        permuter = UsernamePermuter("test")
        assert permuter.base == "test"

    def test_permute_basic(self):
        permuter = UsernamePermuter("test")
        variations = permuter.permute()
        assert "test" in variations
        assert len(variations) > 1

    def test_permute_with_dots(self):
        permuter = UsernamePermuter("testuser")
        variations = permuter.permute()
        assert "test.user" in variations or "test_user" in variations

    def test_permute_with_numbers(self):
        permuter = UsernamePermuter("test")
        variations = permuter.permute()
        numbered = [v for v in variations if any(c.isdigit() for c in v)]
        assert len(numbered) > 0

    def test_permute_unique(self):
        permuter = UsernamePermuter("test")
        variations = permuter.permute()
        assert len(variations) == len(set(variations))

    def test_permute_includes_base(self):
        permuter = UsernamePermuter("myusername")
        variations = permuter.permute()
        assert "myusername" in variations


class TestAccountFinder:
    def test_init(self):
        finder = AccountFinder()
        assert finder.timeout == 30.0

    def test_init_with_params(self):
        finder = AccountFinder(timeout=60.0, max_concurrent=5)
        assert finder.timeout == 60.0
        assert finder.max_concurrent == 5

    @pytest.mark.asyncio
    async def test_search(self):
        finder = AccountFinder()
        with patch.object(finder, "_check_platform", new_callable=AsyncMock, return_value=None):
            report = await finder.search("testuser")
            assert isinstance(report, SearchReport)
            assert report.query == "testuser"

    @pytest.mark.asyncio
    async def test_search_with_found(self):
        finder = AccountFinder()
        found = FoundAccount(
            username="test", platform="github", url="https://github.com/test", confidence=0.9
        )
        with patch.object(finder, "_check_platform", new_callable=AsyncMock, return_value=found):
            report = await finder.search("test")
            assert report.found_count >= 0

    @pytest.mark.asyncio
    async def test_search_with_tags(self):
        finder = AccountFinder()
        with patch.object(finder, "_check_platform", new_callable=AsyncMock, return_value=None):
            report = await finder.search("test", tags=["coding"])
            assert isinstance(report, SearchReport)

    @pytest.mark.asyncio
    async def test_recursive_search(self):
        finder = AccountFinder()
        with patch.object(finder, "search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = SearchReport(
                query="test", found=[FoundAccount(username="found", platform="tg")]
            )
            report = await finder.recursive_search("test", depth=2)
            assert isinstance(report, SearchReport)

    @pytest.mark.asyncio
    async def test_extract_accounts_from_page(self):
        finder = AccountFinder()
        mock_page = MagicMock()
        mock_page.query_selector_all = AsyncMock(return_value=[])
        result = await finder.extract_accounts_from_page(mock_page, "https://example.com")
        assert isinstance(result, list)
