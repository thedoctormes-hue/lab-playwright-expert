"""
Extended tests for profile_analyzer.py — ProfileData, ProfileAnalysis, ProfileAnalyzer.
Covers: dataclasses, analysis logic.
"""

from unittest.mock import AsyncMock, patch

import pytest

from lab_playwright_kit.profile_analyzer import (
    ProfileAnalysis,
    ProfileAnalyzer,
    ProfileData,
)


class TestProfileData:
    def test_defaults(self):
        data = ProfileData()
        assert data.url == ""
        assert data.username == ""
        assert data.platform == ""
        assert data.display_name == ""
        assert data.bio == ""
        assert data.followers == 0
        assert data.following == 0
        assert data.posts_count == 0
        assert data.verified is False
        assert data.profile_pic == ""
        assert data.external_url == ""
        assert data.raw_data == {}

    def test_full(self):
        data = ProfileData(
            url="https://t.me/doctorm",
            username="doctorm",
            platform="telegram",
            display_name="Doctor M",
            bio="Lab researcher",
            followers=1000,
            following=100,
            posts_count=50,
            verified=True,
            profile_pic="https://t.me/pic.jpg",
            external_url="https://example.com",
        )
        assert data.username == "doctorm"
        assert data.verified is True
        assert data.followers == 1000

    def test_to_dict(self):
        data = ProfileData(username="test", platform="tg", followers=500)
        d = data.to_dict()
        assert d["username"] == "test"
        assert d["platform"] == "tg"
        assert d["followers"] == 500


class TestProfileAnalysis:
    def test_defaults(self):
        analysis = ProfileAnalysis()
        assert analysis.profile is None
        assert analysis.risk_score == 0
        assert analysis.risk_level == "low"
        assert analysis.tags == []
        assert analysis.insights == []
        assert analysis.similar_accounts == []
        assert analysis.timestamp == ""

    def test_risk_levels(self):
        for level in ("low", "medium", "high", "critical"):
            analysis = ProfileAnalysis(risk_level=level)
            assert analysis.risk_level == level

    def test_is_suspicious(self):
        assert ProfileAnalysis(risk_level="high").is_suspicious is True
        assert ProfileAnalysis(risk_level="critical").is_suspicious is True
        assert ProfileAnalysis(risk_level="low").is_suspicious is False
        assert ProfileAnalysis(risk_level="medium").is_suspicious is False

    def test_to_dict(self):
        analysis = ProfileAnalysis(risk_score=75, risk_level="high", tags=["bot", "spam"])
        d = analysis.to_dict()
        assert d["risk_score"] == 75
        assert d["risk_level"] == "high"
        assert d["tags"] == ["bot", "spam"]


class TestProfileAnalyzer:
    def test_init(self):
        analyzer = ProfileAnalyzer()
        assert analyzer.enabled() is True

    def test_init_with_params(self):
        analyzer = ProfileAnalyzer(timeout=60.0)
        assert analyzer.timeout == 60.0

    @pytest.mark.asyncio
    async def test_analyze_returns_analysis(self):
        analyzer = ProfileAnalyzer()
        data = ProfileData(username="test", platform="tg")
        with patch.object(analyzer, "_heuristic_analyze") as mock_heuristic:
            mock_heuristic.return_value = ProfileAnalysis(risk_score=10, risk_level="low")
            result = await analyzer.analyze(data)
            assert isinstance(result, ProfileAnalysis)

    @pytest.mark.asyncio
    async def test_analyze_with_llm(self):
        analyzer = ProfileAnalyzer(api_url="https://openrouter.ai/api/v1", api_key="sk-test")
        assert analyzer.enabled is True
        data = ProfileData(username="test", platform="tg")
        with patch.object(analyzer, "_llm_analyze", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = ProfileAnalysis(risk_score=20, risk_level="low")
            result = await analyzer.analyze(data)
            assert isinstance(result, ProfileAnalysis)

    @pytest.mark.asyncio
    async def test_analyze_batch(self):
        analyzer = ProfileAnalyzer()
        profiles = [
            ProfileData(username="u1", platform="tg"),
            ProfileData(username="u2", platform="ig"),
        ]
        with patch.object(analyzer, "analyze", new_callable=AsyncMock) as mock_analyze:
            mock_analyze.return_value = ProfileAnalysis(risk_score=10, risk_level="low")
            results = await analyzer.analyze_batch(profiles)
            assert len(results) == 2

    def test_heuristic_analysis_low_risk(self):
        analyzer = ProfileAnalyzer()
        data = ProfileData(
            username="realuser",
            platform="telegram",
            followers=1000,
            following=100,
            posts_count=50,
            verified=True,
        )
        analysis = analyzer._heuristic_analyze(data)
        assert analysis.risk_level in ("low", "medium")

    def test_heuristic_analysis_high_risk(self):
        analyzer = ProfileAnalyzer()
        data = ProfileData(
            username="bot12345",
            platform="telegram",
            followers=0,
            following=5000,
            posts_count=0,
            verified=False,
        )
        analysis = analyzer._heuristic_analyze(data)
        assert analysis.risk_score > 0

    def test_build_prompt(self):
        analyzer = ProfileAnalyzer()
        data = ProfileData(username="test", platform="tg", followers=100)
        prompt = analyzer._build_prompt(data)
        assert "test" in prompt
        assert "tg" in prompt or "telegram" in prompt

    def test_parse_llm_response_valid(self):
        analyzer = ProfileAnalyzer()
        response = '{"risk_score": 50, "risk_level": "medium", "tags": ["new_account"]}'
        result = analyzer._parse_llm_response(response)
        assert result.risk_score == 50
        assert result.risk_level == "medium"

    def test_parse_llm_response_invalid(self):
        analyzer = ProfileAnalyzer()
        result = analyzer._parse_llm_response("not json")
        assert result.risk_score == 0
        assert result.risk_level == "low"
