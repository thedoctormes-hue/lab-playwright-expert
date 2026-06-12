"""
ProfileAnalyzer — AI-анализ найденных профилей.

Вдохновлён Maigret AI-анализом:
  - Извлечение структурированных данных из профилей
  - Определение типа личности (разработчик, дизайнер, блогер)
  - Выявление связей между аккаунтами
  - Оценка достоверности профиля

Использование:
    >>> analyzer = ProfileAnalyzer()
    >>> analysis = await analyzer.analyze(profile_data)
    >>> print(analysis.person_type, analysis.confidence)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass
class ProfileData:
    """Данные профиля.

    Attributes:
        platform: Платформа
        username: Имя пользователя
        url: URL профиля
        display_name: Отображаемое имя
        bio: Биография/описание
        avatar_url: URL аватара
        location: Местоположение
        links: Ссылки на другие ресурсы
        raw_html: Сырой HTML страницы
        metadata: Дополнительные данные
    """
    platform: str = ""
    username: str = ""
    url: str = ""
    display_name: str = ""
    bio: str = ""
    avatar_url: str = ""
    location: str = ""
    links: list[str] = field(default_factory=list)
    raw_html: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProfileAnalysis:
    """Результат AI-анализа профиля.

    Attributes:
        person_type: Тип личности (developer, designer, blogger, etc.)
        confidence: Уверенность (0.0-1.0)
        interests: Интересы
        skills: Навыки
        languages: Языки
        country: Предполагаемая страна
        is_bot: Вероятность что это бот
        is_verified: Верифицирован ли аккаунт
        connections: Связи с другими аккаунтами
        summary: Краткое описание
        risk_score: Оценка риска (0-100)
    """
    person_type: str = "unknown"
    confidence: float = 0.0
    interests: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    country: str = ""
    is_bot: bool = False
    is_verified: bool = False
    connections: list[dict[str, str]] = field(default_factory=list)
    summary: str = ""
    risk_score: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "person_type": self.person_type,
            "confidence": self.confidence,
            "interests": self.interests,
            "skills": self.skills,
            "languages": self.languages,
            "country": self.country,
            "is_bot": self.is_bot,
            "is_verified": self.is_verified,
            "connections_count": len(self.connections),
            "summary": self.summary,
            "risk_score": self.risk_score,
        }


class ProfileAnalyzer:
    """AI-анализатор профилей.

    Использует LLM для анализа данных профилей.
    Поддерживает OpenAI-совместимые API (OpenRouter, etc.).

    Использование:
        >>> analyzer = ProfileAnalyzer(
        ...     api_url="https://openrouter.ai/api/v1",
        ...     api_key="sk-...",
        ...     model="google/gemini-2.5-flash"
        ... )
        >>> analysis = await analyzer.analyze(profile_data)
    """

    def __init__(
        self,
        api_url: str = "",
        api_key: str = "",
        model: str = "google/gemini-2.5-flash",
        timeout: float = 30.0,
    ):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._enabled = bool(api_url and api_key)

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def analyze(self, profile: ProfileData) -> ProfileAnalysis:
        """Анализировать профиль.

        Args:
            profile: Данные профиля

        Returns:
            ProfileAnalysis с результатами
        """
        if not self._enabled:
            return self._heuristic_analyze(profile)

        return await self._llm_analyze(profile)

    async def analyze_batch(
        self,
        profiles: list[ProfileData],
    ) -> list[ProfileAnalysis]:
        """Анализировать несколько профилей.

        Args:
            profiles: Список профилей

        Returns:
            Список анализов
        """
        import asyncio
        tasks = [self.analyze(p) for p in profiles]
        return await asyncio.gather(*tasks)

    async def _llm_analyze(self, profile: ProfileData) -> ProfileAnalysis:
        """Анализ через LLM."""
        import httpx

        prompt = self._build_prompt(profile)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are an OSINT analyst. Analyze the profile and return JSON only.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "response_format": {"type": "json_object"},
                        "max_tokens": 1000,
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    return self._parse_llm_response(content, profile)
                else:
                    logger.warning(f"LLM API error: {response.status_code}")

        except Exception as e:
            logger.error(f"LLM analysis error: {e}")

        return self._heuristic_analyze(profile)

    def _heuristic_analyze(self, profile: ProfileData) -> ProfileAnalysis:
        """Эвристический анализ (без LLM).

        Использует ключевые слова и паттерны для определения типа профиля.
        """
        analysis = ProfileAnalysis()
        bio_lower = profile.bio.lower()
        text = f"{profile.display_name} {profile.bio} {profile.platform} {profile.location}".lower()

        # Определить тип личности
        type_keywords = {
            "developer": ["developer", "engineer", "programmer", "coding", "code", "dev", "разработчик", "программист"],
            "designer": ["designer", "design", "ui", "ux", "creative", "дизайнер"],
            "blogger": ["blogger", "writer", "author", "blog", "блогер", "автор"],
            "entrepreneur": ["founder", "ceo", "startup", "entrepreneur", "основатель"],
            "researcher": ["researcher", "phd", "professor", "science", "исследователь"],
            "marketing": ["marketing", "growth", "seo", "smm", "маркетинг"],
        }

        for ptype, keywords in type_keywords.items():
            if any(kw in text for kw in keywords):
                analysis.person_type = ptype
                analysis.confidence = 0.6
                break

        # Определить интересы
        interest_keywords = {
            "python": ["python"],
            "javascript": ["javascript", "js", "node"],
            "ai": ["ai", "machine learning", "ml", "deep learning", "нейросети"],
            "blockchain": ["blockchain", "crypto", "bitcoin", "web3"],
            "gaming": ["gaming", "game", "gamer", "игры"],
            "music": ["music", "musician", "producer", "музыка"],
            "photo": ["photo", "photographer", "фото"],
            "travel": ["travel", "nomad", "путешествия"],
        }

        for interest, keywords in interest_keywords.items():
            if any(kw in text for kw in keywords):
                analysis.interests.append(interest)

        # Определить языки
        lang_patterns = {
            "en": [r"\benglish\b", r"\ben\b"],
            "ru": [r"\bрусский\b", r"\bru\b"],
            "de": [r"\bdeutsch\b", r"\bger\b"],
            "fr": [r"\bfrançais\b", r"\bfr\b"],
            "es": [r"\bespañol\b", r"\bes\b"],
        }

        for lang, patterns in lang_patterns.items():
            for pattern in patterns:
                import re
                if re.search(pattern, bio_lower):
                    analysis.languages.append(lang)
                    break

        # Определить страну
        country_patterns = {
            "ru": ["russia", "moscow", "spb", "россия", "москва", "петербург"],
            "us": ["usa", "united states", "new york", "california", "сша"],
            "ua": ["ukraine", "kyiv", "украина", "киев"],
            "de": ["germany", "berlin", "германия", "берлин"],
            "gb": ["uk", "london", "britain", "англия", "лондон"],
        }

        for country, patterns in country_patterns.items():
            if any(p in text for p in patterns):
                analysis.country = country
                break

        # Проверить на бота
        bot_indicators = [
            profile.bio == "",
            len(profile.bio) < 10,
            profile.avatar_url == "",
            "bot" in profile.username.lower(),
        ]
        if sum(bot_indicators) >= 3:
            analysis.is_bot = True
            analysis.risk_score = 70

        # Верификация
        if profile.metadata.get("verified"):
            analysis.is_verified = True

        # Краткое описание
        parts = [f"Type: {analysis.person_type}"]
        if analysis.interests:
            parts.append(f"Interests: {', '.join(analysis.interests[:3])}")
        if analysis.country:
            parts.append(f"Country: {analysis.country}")
        analysis.summary = ". ".join(parts)

        return analysis

    def _build_prompt(self, profile: ProfileData) -> str:
        """Построить промпт для LLM."""
        return f"""Analyze this social media profile and return JSON:

Platform: {profile.platform}
Username: {profile.username}
Display Name: {profile.display_name}
Bio: {profile.bio}
Location: {profile.location}
Links: {', '.join(profile.links[:5])}

Return JSON with these fields:
- person_type: (developer/designer/blogger/entrepreneur/researcher/marketing/unknown)
- confidence: (0.0-1.0)
- interests: (list of strings)
- skills: (list of strings)
- languages: (list: en/ru/de/fr/es)
- country: (2-letter code or empty)
- is_bot: (boolean)
- is_verified: (boolean)
- summary: (one sentence)
- risk_score: (0-100)
"""

    def _parse_llm_response(
        self,
        content: str,
        profile: ProfileData,
    ) -> ProfileAnalysis:
        """Распарсить ответ LLM."""
        try:
            data = json.loads(content)
            return ProfileAnalysis(
                person_type=data.get("person_type", "unknown"),
                confidence=float(data.get("confidence", 0.5)),
                interests=data.get("interests", []),
                skills=data.get("skills", []),
                languages=data.get("languages", []),
                country=data.get("country", ""),
                is_bot=data.get("is_bot", False),
                is_verified=data.get("is_verified", False),
                summary=data.get("summary", ""),
                risk_score=int(data.get("risk_score", 0)),
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return self._heuristic_analyze(profile)
