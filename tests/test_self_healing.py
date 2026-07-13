"""
Тесты для SelfHealingParser — автоисправление селекторов.

Проверяет: self-healing flow, retry логика, fallback,
кэширование, валидация результатов.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lab_playwright_kit.llm_parse import (
    LLMConfig,
    LLMParser,
    ParseCache,
    SelfHealingParser,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_mock_page(url: str = "https://example.com", content: str = "<body>test</body>") -> AsyncMock:
    """Создать mock Playwright page."""
    page = AsyncMock()
    page.url = url
    page.evaluate = AsyncMock(return_value=content)
    page.title = AsyncMock(return_value="Test Page")
    return page


def make_valid_llm_response(data: dict[str, Any]) -> dict:
    """Сформировать ответ как от LLM API."""
    import json

    content = json.dumps(data, ensure_ascii=False)
    return {
        "choices": [
            {"message": {"content": content}}
        ]
    }


# ─── Tests ───────────────────────────────────────────────────────────────────

class TestSelfHealingParser:
    """Тесты SelfHealingParser."""

    @pytest.fixture
    def llm_parser(self) -> LLMParser:
        config = LLMConfig(api_key="fake-key", api_url="http://fake-llm.test")
        return LLMParser(config)

    @pytest.fixture
    def healing_parser(self, llm_parser: LLMParser) -> SelfHealingParser:
        return SelfHealingParser(llm_parser, max_retries=3)

    @pytest.mark.asyncio
    async def test_extract_with_retry_success_first_attempt(
        self, healing_parser: SelfHealingParser
    ):
        """Успех с первой попытки — результат кэшируется."""
        page = make_mock_page()
        valid_data = {"prices": [100, 200], "found": True}

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=MagicMock(
                status_code=200,
                json=MagicMock(return_value=make_valid_llm_response(valid_data)),
                text="ok",
            ))
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await healing_parser.extract_with_retry(
                page, "извлечь цены"
            )

        assert result["prices"] == [100, 200]
        assert healing_parser.cache.size >= 1  # Закэшировано

    @pytest.mark.asyncio
    async def test_extract_with_retry_uses_cache(
        self, healing_parser: SelfHealingParser
    ):
        """Повторный вызов с тем же query — берёт из кэша."""
        page = make_mock_page()
        valid_data = {"cars": ["BMW", "Audi"], "found": True}

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=MagicMock(
                status_code=200,
                json=MagicMock(return_value=make_valid_llm_response(valid_data)),
                text="ok",
            ))
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            # Первый вызов — LLM API
            result1 = await healing_parser.extract_with_retry(page, "извлечь машины")
            # Второй вызов — кэш
            result2 = await healing_parser.extract_with_retry(page, "извлечь машины")

        assert result1 == result2
        # LLM вызван только один раз (второй из кэша)
        assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_extract_with_retry_fallback_invalid_result(
        self, healing_parser: SelfHealingParser
    ):
        """LLM вернул found=false — должен быть retry."""
        page = make_mock_page()
        empty_result = {"found": False, "reason": "not found"}
        valid_data = {"data": "value", "found": True}

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(
                    status_code=200,
                    json=MagicMock(return_value=make_valid_llm_response(empty_result)),
                    text="ok",
                )
            return MagicMock(
                status_code=200,
                json=MagicMock(return_value=make_valid_llm_response(valid_data)),
                text="ok",
            )

        # Patch _fix_selector to return None (no fix)
        healing_parser._fix_selector = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await healing_parser.extract_with_retry(
                page, "query", max_retries=2
            )

        # Должен вернуть валидный результат со 2-й попытки
        assert result.get("data") == "value"

    @pytest.mark.asyncio
    async def test_extract_with_retry_all_failed(
        self, healing_parser: SelfHealingParser
    ):
        """Все попытки провалены — возвращает лучший из плохих."""
        page = make_mock_page()

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=MagicMock(
                status_code=500,
                text="Server Error",
            ))
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await healing_parser.extract_with_retry(
                page, "query", max_retries=2
            )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_fix_selector_found_new(
        self, healing_parser: SelfHealingParser
    ):
        """_fix_selector находит новый селектор."""
        page = make_mock_page()

        new_selector = ".new-price-class"
        fix_response = {"selector": new_selector, "reason": "found by text match"}

        # Patch extract in llm_parser to return selectors and snapshot
        healing_parser.llm.list_selectors = AsyncMock(return_value=[
            {"selector": ".link", "tag": "a", "text": "Price", "class": "link", "id": ""},
        ])
        healing_parser.llm.snapshot = AsyncMock(return_value="<html><body>$100</body></html>")

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=MagicMock(
                status_code=200,
                json=MagicMock(return_value=make_valid_llm_response(fix_response)),
                text="ok",
            ))
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await healing_parser._fix_selector(
                page, ".old-broken-selector", "цены"
            )

        assert result == new_selector

    @pytest.mark.asyncio
    async def test_fix_selector_none_found(
        self, healing_parser: SelfHealingParser
    ):
        """_fix_selector возвращает None когда не может найти."""
        page = make_mock_page()

        fix_response = {"selector": None, "reason": "no matching element"}

        healing_parser.llm.list_selectors = AsyncMock(return_value=[])
        healing_parser.llm.snapshot = AsyncMock(return_value="<html></html>")

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=MagicMock(
                status_code=200,
                json=MagicMock(return_value=make_valid_llm_response(fix_response)),
                text="ok",
            ))
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await healing_parser._fix_selector(
                page, ".broken", "query"
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_fix_selector_llm_error(
        self, healing_parser: SelfHealingParser
    ):
        """_fix_selector обрабатывает ошибку LLM API."""
        page = make_mock_page()

        healing_parser.llm.list_selectors = AsyncMock(return_value=[])
        healing_parser.llm.snapshot = AsyncMock(return_value="<html></html>")

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=MagicMock(
                status_code=429,
                text="Rate limited",
            ))
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await healing_parser._fix_selector(
                page, ".broken", "query"
            )

        assert result is None

    def test_is_valid_result_valid(self):
        """_is_valid_result — валидные результаты проходят."""
        assert SelfHealingParser._is_valid_result({"data": "value"}) is True
        assert SelfHealingParser._is_valid_result({"prices": [1, 2], "count": 2}) is True

    def test_is_valid_result_invalid(self):
        """_is_valid_result — невалидные результаты отклоняются."""
        assert SelfHealingParser._is_valid_result({}) is False
        assert SelfHealingParser._is_valid_result({"error": "fail"}) is False
        assert SelfHealingParser._is_valid_result({"found": False}) is False
        assert SelfHealingParser._is_valid_result({"raw": "plain text"}) is False

    def test_selector_cache(self):
        """Кэш селекторов работает корректно."""
        llm = LLMParser(LLMConfig(api_key="test"))
        parser = SelfHealingParser(llm)

        parser._selector_cache["query1"] = ".new-selector"
        assert parser.get_selector_cache() == {"query1": ".new-selector"}

        count = parser.clear_selector_cache()
        assert count == 1
        assert parser.get_selector_cache() == {}
