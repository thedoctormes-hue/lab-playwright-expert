"""
Tests for AccountFinder — рекурсивный поиск аккаунтов.

Проверяет пермутацию ников, проверку платформ, извлечение аккаунтов.
"""
import pytest

from lab_playwright_kit.account_finder import (
    AccountFinder,
    FoundAccount,
    SearchReport,
    UsernamePermuter,
)
from lab_playwright_kit.platform_registry import PlatformRegistry


class TestUsernamePermuter:
    """Тесты UsernamePermuter."""

    def test_basic_permutation(self):
        perm = UsernamePermuter()
        variants = perm.permute("testuser")
        assert "testuser" in variants
        assert len(variants) > 1

    def test_max_variants(self):
        perm = UsernamePermuter()
        variants = perm.permute("testuser", max_variants=5)
        assert len(variants) <= 5

    def test_dot_replacement(self):
        perm = UsernamePermuter()
        variants = perm.permute("user.name")
        assert "user_name" in variants
        assert "username" in variants

    def test_underscore_replacement(self):
        perm = UsernamePermuter()
        variants = perm.permute("user_name")
        assert "user.name" in variants
        assert "username" in variants

    def test_number_suffix(self):
        perm = UsernamePermuter()
        variants = perm.permute("user")
        assert "user1" in variants
        assert "user2" in variants

    def test_case_variations(self):
        perm = UsernamePermuter()
        variants = perm.permute("User")
        assert "user" in variants
        assert "USER" in variants
        assert "User" in variants

    def test_truncation(self):
        perm = UsernamePermuter()
        variants = perm.permute("testuser")
        assert "tes" in variants
        assert "test" in variants

    def test_short_username_no_truncation(self):
        perm = UsernamePermuter()
        variants = perm.permute("ab")
        # Не должно быть усечения для коротких
        assert "ab" in variants

    def test_unique_variants(self):
        perm = UsernamePermuter()
        variants = perm.permute("test_user.name")
        assert len(variants) == len(set(variants))


class TestFoundAccount:
    """Тесты FoundAccount."""

    def test_to_dict(self):
        account = FoundAccount(
            platform="GitHub",
            username="octocat",
            url="https://github.com/octocat",
            status="claimed",
            confidence=0.9,
            source="search",
            tags=["coding", "us"],
        )
        d = account.to_dict()
        assert d["platform"] == "GitHub"
        assert d["username"] == "octocat"
        assert d["status"] == "claimed"
        assert d["confidence"] == 0.9

    def test_default_values(self):
        account = FoundAccount()
        assert account.status == "unknown"
        assert account.confidence == 0.0
        assert account.source == "search"


class TestSearchReport:
    """Тесты SearchReport."""

    def test_total_found(self):
        report = SearchReport(
            query="test",
            found=[
                FoundAccount(platform="GitHub", status="claimed"),
                FoundAccount(platform="Twitter", status="claimed"),
                FoundAccount(platform="Reddit", status="available"),
            ],
        )
        assert report.total_found == 2

    def test_by_platform(self):
        report = SearchReport(
            query="test",
            found=[
                FoundAccount(platform="GitHub", username="test"),
                FoundAccount(platform="GitHub", username="test2"),
                FoundAccount(platform="Twitter", username="test"),
            ],
        )
        gh = report.by_platform("GitHub")
        assert len(gh) == 2

    def test_by_tag(self):
        report = SearchReport(
            query="test",
            found=[
                FoundAccount(platform="GitHub", tags=["coding"]),
                FoundAccount(platform="Twitter", tags=["social"]),
                FoundAccount(platform="Reddit", tags=["social", "news"]),
            ],
        )
        social = report.by_tag("social")
        assert len(social) == 2

    def test_to_dict(self):
        report = SearchReport(
            query="test",
            found=[FoundAccount(platform="GitHub", status="claimed")],
            checked=10,
            elapsed_seconds=1.5,
        )
        d = report.to_dict()
        assert d["query"] == "test"
        assert d["total_found"] == 1
        assert d["checked"] == 10


class TestAccountFinderInit:
    """Тесты инициализации AccountFinder."""

    def test_default_init(self):
        finder = AccountFinder()
        assert finder.max_concurrent == 10
        assert finder.timeout == 10.0

    def test_custom_init(self):
        finder = AccountFinder(max_concurrent=5, timeout=30.0)
        assert finder.max_concurrent == 5
        assert finder.timeout == 30.0

    def test_with_registry(self):
        reg = PlatformRegistry()
        reg.load_defaults()
        finder = AccountFinder(registry=reg)
        assert finder.registry.count() >= 50
