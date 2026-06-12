"""
Tests for PlatformRegistry — реестр платформ.

Проверяет загрузку, фильтрацию, ранжирование и совместимость с Maigret-форматом.
"""
import pytest

from lab_playwright_kit.platform_registry import (
    CheckType,
    PlatformProfile,
    PlatformRegistry,
)


class TestPlatformProfile:
    """Тесты PlatformProfile."""

    def test_url_for(self):
        p = PlatformProfile(
            name="GitHub",
            url_template="https://github.com/{username}",
        )
        assert p.url_for("octocat") == "https://github.com/octocat"

    def test_to_dict(self):
        p = PlatformProfile(
            name="GitHub",
            url_main="https://github.com",
            url_template="https://github.com/{username}",
            check_type=CheckType.MESSAGE,
            tags=["coding", "us"],
            alexa_rank=76,
        )
        d = p.to_dict()
        assert d["name"] == "GitHub"
        assert d["check_type"] == "message"
        assert d["tags"] == ["coding", "us"]
        assert d["alexa_rank"] == 76

    def test_default_values(self):
        p = PlatformProfile()
        assert p.disabled is False
        assert p.check_type == CheckType.MESSAGE
        assert p.alexa_rank == 999999
        assert p.tags == []


class TestPlatformRegistry:
    """Тесты PlatformRegistry."""

    def test_load_defaults(self):
        reg = PlatformRegistry()
        reg.load_defaults()
        assert reg.count() >= 50

    def test_get(self):
        reg = PlatformRegistry()
        reg.load_defaults()
        p = reg.get("github")
        assert p is not None
        assert p.name == "GitHub"

    def test_get_case_insensitive(self):
        reg = PlatformRegistry()
        reg.load_defaults()
        assert reg.get("GitHub") is not None
        assert reg.get("github") is not None
        assert reg.get("GITHUB") is not None

    def test_get_nonexistent(self):
        reg = PlatformRegistry()
        reg.load_defaults()
        assert reg.get("nonexistent_platform_xyz") is None

    def test_filter_by_tag(self):
        reg = PlatformRegistry()
        reg.load_defaults()
        social = reg.filter_by_tag("social")
        assert len(social) > 0
        for p in social:
            assert "social" in p.tags

    def test_filter_by_tags_any(self):
        reg = PlatformRegistry()
        reg.load_defaults()
        result = reg.filter_by_tags(["social", "coding"])
        assert len(result) > 0

    def test_filter_by_tags_all(self):
        reg = PlatformRegistry()
        reg.load_defaults()
        result = reg.filter_by_tags(["social", "ru"], match_all=True)
        for p in result:
            assert "social" in p.tags
            assert "ru" in p.tags

    def test_top(self):
        reg = PlatformRegistry()
        reg.load_defaults()
        top5 = reg.top(5)
        assert len(top5) == 5
        # Проверить порядок ранжирования
        for i in range(len(top5) - 1):
            assert top5[i].alexa_rank <= top5[i + 1].alexa_rank

    def test_top_50(self):
        reg = PlatformRegistry()
        reg.load_defaults()
        top50 = reg.top(50)
        assert len(top50) <= 50

    def test_all(self):
        reg = PlatformRegistry()
        reg.load_defaults()
        all_platforms = reg.all()
        assert len(all_platforms) == reg.count()

    def test_register(self):
        reg = PlatformRegistry()
        reg.register(PlatformProfile(name="TestPlatform", url_template="https://test.com/{username}"))
        assert reg.get("testplatform") is not None

    def test_disabled_not_in_all(self):
        reg = PlatformRegistry()
        reg.register(PlatformProfile(name="Active", url_template="https://active.com/{username}"))
        reg.register(PlatformProfile(name="Disabled", url_template="https://disabled.com/{username}", disabled=True))
        assert len(reg.all()) == 1

    def test_russian_platforms(self):
        reg = PlatformRegistry()
        reg.load_defaults()
        ru = reg.filter_by_tag("ru")
        assert len(ru) >= 5  # VK, OK, Habr, VC.ru, DTF, Pikabu, etc.

    def test_coding_platforms(self):
        reg = PlatformRegistry()
        reg.load_defaults()
        coding = reg.filter_by_tag("coding")
        assert len(coding) >= 5  # GitHub, GitLab, StackOverflow, etc.


class TestMaigretCompatibility:
    """Тесты совместимости с Maigret-форматом."""

    def test_load_from_dict(self):
        reg = PlatformRegistry()
        maigret_data = {
            "GitHub": {
                "urlMain": "https://github.com",
                "url": "https://github.com/{username}",
                "usernameClaimed": "torvalds",
                "usernameUnclaimed": "noonewouldeverusethis7",
                "checkType": "message",
                "presenseStrs": ["p-nickname"],
                "absenceStrs": ["404"],
                "tags": ["coding", "us"],
                "alexaRank": 76,
            },
            "Reddit": {
                "urlMain": "https://www.reddit.com",
                "url": "https://www.reddit.com/user/{username}",
                "checkType": "status_code",
                "tags": ["news", "us"],
                "alexaRank": 18,
            },
        }
        reg.load_from_dict(maigret_data)
        assert reg.count() == 2
        assert reg.get("github") is not None
        assert reg.get("reddit") is not None

    def test_load_from_dict_preserves_check_type(self):
        reg = PlatformRegistry()
        reg.load_from_dict({
            "Test": {
                "url": "https://test.com/{username}",
                "checkType": "status_code",
            }
        })
        p = reg.get("test")
        assert p.check_type == CheckType.STATUS_CODE


class TestCheckType:
    """Тесты CheckType enum."""

    def test_values(self):
        assert CheckType.MESSAGE.value == "message"
        assert CheckType.STATUS_CODE.value == "status_code"
        assert CheckType.RESPONSE_URL.value == "response_url"

    def test_from_string(self):
        assert CheckType("message") == CheckType.MESSAGE
        assert CheckType("status_code") == CheckType.STATUS_CODE
