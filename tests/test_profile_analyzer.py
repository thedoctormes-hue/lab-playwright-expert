"""
Tests for ProfileAnalyzer — AI-анализ профилей.

Проверяет эвристический анализ и структуры данных.
"""
import pytest

from lab_playwright_kit.profile_analyzer import (
    ProfileAnalysis,
    ProfileAnalyzer,
    ProfileData,
)


class TestProfileData:
    """Тесты ProfileData."""

    def test_default_values(self):
        p = ProfileData()
        assert p.platform == ""
        assert p.username == ""
        assert p.tags == [] if hasattr(p, 'tags') else True


class TestProfileAnalysis:
    """Тесты ProfileAnalysis."""

    def test_to_dict(self):
        analysis = ProfileAnalysis(
            person_type="developer",
            confidence=0.8,
            interests=["python", "ai"],
            skills=["coding"],
            languages=["en", "ru"],
            country="us",
            is_bot=False,
            is_verified=True,
            summary="Test summary",
            risk_score=10,
        )
        d = analysis.to_dict()
        assert d["person_type"] == "developer"
        assert d["confidence"] == 0.8
        assert d["interests"] == ["python", "ai"]
        assert d["is_verified"] is True
        assert d["risk_score"] == 10

    def test_default_values(self):
        a = ProfileAnalysis()
        assert a.person_type == "unknown"
        assert a.confidence == 0.0
        assert a.is_bot is False
        assert a.risk_score == 0


class TestProfileAnalyzer:
    """Тесты ProfileAnalyzer."""

    def test_disabled_without_api(self):
        analyzer = ProfileAnalyzer()
        assert analyzer.enabled is False

    def test_enabled_with_api(self):
        analyzer = ProfileAnalyzer(
            api_url="https://openrouter.ai/api/v1",
            api_key="test-key",
        )
        assert analyzer.enabled is True

    @pytest.mark.asyncio
    async def test_heuristic_developer(self):
        analyzer = ProfileAnalyzer()
        profile = ProfileData(
            platform="github",
            username="test",
            display_name="Test Developer",
            bio="Python developer. Open source enthusiast. Building cool stuff.",
            location="Berlin",
        )
        analysis = await analyzer.analyze(profile)
        assert analysis.person_type == "developer"
        assert analysis.confidence > 0.5

    @pytest.mark.asyncio
    async def test_heuristic_designer(self):
        analyzer = ProfileAnalyzer()
        profile = ProfileData(
            platform="dribbble",
            username="designer",
            display_name="Creative Designer",
            bio="UI/UX designer. Creating beautiful interfaces.",
            location="New York",
        )
        analysis = await analyzer.analyze(profile)
        assert analysis.person_type == "designer"

    @pytest.mark.asyncio
    async def test_heuristic_blogger(self):
        analyzer = ProfileAnalyzer()
        profile = ProfileData(
            platform="medium",
            username="writer",
            display_name="Tech Writer",
            bio="Blogger and author. Writing about technology.",
            location="London",
        )
        analysis = await analyzer.analyze(profile)
        assert analysis.person_type == "blogger"

    @pytest.mark.asyncio
    async def test_heuristic_bot_detection(self):
        analyzer = ProfileAnalyzer()
        profile = ProfileData(
            platform="twitter",
            username="bot12345",
            display_name="",
            bio="",
            avatar_url="",
        )
        analysis = await analyzer.analyze(profile)
        assert analysis.is_bot is True
        assert analysis.risk_score > 50

    @pytest.mark.asyncio
    async def test_heuristic_country_ru(self):
        analyzer = ProfileAnalyzer()
        profile = ProfileData(
            platform="vk",
            username="user",
            display_name="Иван",
            bio="Живу в Москве. Люлю Россию.",
            location="Moscow, Russia",
        )
        analysis = await analyzer.analyze(profile)
        assert analysis.country == "ru"

    @pytest.mark.asyncio
    async def test_heuristic_country_us(self):
        analyzer = ProfileAnalyzer()
        profile = ProfileData(
            platform="twitter",
            username="user",
            display_name="John",
            bio="Living in New York. USA.",
            location="New York, USA",
        )
        analysis = await analyzer.analyze(profile)
        assert analysis.country == "us"

    @pytest.mark.asyncio
    async def test_heuristic_languages(self):
        analyzer = ProfileAnalyzer()
        profile = ProfileData(
            platform="github",
            username="user",
            display_name="User",
            bio="English and Русский speaker.",
        )
        analysis = await analyzer.analyze(profile)
        assert "en" in analysis.languages

    @pytest.mark.asyncio
    async def test_heuristic_interests_python(self):
        analyzer = ProfileAnalyzer()
        profile = ProfileData(
            platform="github",
            username="user",
            display_name="User",
            bio="Python developer. Love coding in Python.",
        )
        analysis = await analyzer.analyze(profile)
        assert "python" in analysis.interests

    @pytest.mark.asyncio
    async def test_heuristic_interests_ai(self):
        analyzer = ProfileAnalyzer()
        profile = ProfileData(
            platform="twitter",
            username="user",
            display_name="User",
            bio="AI researcher. Machine learning enthusiast.",
        )
        analysis = await analyzer.analyze(profile)
        assert "ai" in analysis.interests

    @pytest.mark.asyncio
    async def test_verified_metadata(self):
        analyzer = ProfileAnalyzer()
        profile = ProfileData(
            platform="twitter",
            username="verified_user",
            display_name="Verified",
            bio="Some bio.",
            metadata={"verified": True},
        )
        analysis = await analyzer.analyze(profile)
        assert analysis.is_verified is True

    @pytest.mark.asyncio
    async def test_unknown_type(self):
        analyzer = ProfileAnalyzer()
        profile = ProfileData(
            platform="unknown",
            username="user",
            display_name="User",
            bio="Just a regular person.",
        )
        analysis = await analyzer.analyze(profile)
        assert analysis.person_type == "unknown"

    @pytest.mark.asyncio
    async def test_summary_generated(self):
        analyzer = ProfileAnalyzer()
        profile = ProfileData(
            platform="github",
            username="dev",
            display_name="Developer",
            bio="Python developer.",
        )
        analysis = await analyzer.analyze(profile)
        assert analysis.summary != ""
        assert "developer" in analysis.summary.lower()
