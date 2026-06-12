"""
Тесты для LLM Parse модуля.

Покрывает:
  - LLMConfig — конфигурация
  - LLMParser — базовые проверки
  - EXTRACTION_PROMPT_TEMPLATE — шаблон промпта
"""
import pytest

from lab_playwright_kit.llm_parse import LLMConfig, LLMParser, EXTRACTION_PROMPT_TEMPLATE


# ─── LLMConfig ───────────────────────────────────────────────────────────────

class TestLLMConfig:
    def test_default_config(self):
        config = LLMConfig()
        assert config.api_url == "https://openrouter.ai/api/v1/chat/completions"
        assert config.model == "google/gemini-2.5-flash"
        assert config.max_content_length == 8000
        assert config.temperature == 0.1
        assert config.timeout == 30
        assert config.api_key == ""

    def test_custom_config(self):
        config = LLMConfig(
            api_url="https://custom.api/v1",
            api_key="test-key",
            model="custom/model",
            max_content_length=4000,
            temperature=0.5,
            timeout=60,
        )
        assert config.api_url == "https://custom.api/v1"
        assert config.api_key == "test-key"
        assert config.model == "custom/model"
        assert config.max_content_length == 4000
        assert config.temperature == 0.5
        assert config.timeout == 60


# ─── LLMParser ───────────────────────────────────────────────────────────────

class TestLLMParser:
    def test_default_init(self):
        parser = LLMParser()
        assert parser.config is not None
        assert isinstance(parser.config, LLMConfig)

    def test_custom_config_init(self):
        config = LLMConfig(model="custom/model")
        parser = LLMParser(config=config)
        assert parser.config.model == "custom/model"

    def test_config_defaults(self):
        parser = LLMParser()
        assert parser.config.api_url == "https://openrouter.ai/api/v1/chat/completions"
        assert parser.config.model == "google/gemini-2.5-flash"


# ─── EXTRACTION_PROMPT_TEMPLATE ──────────────────────────────────────────────

class TestExtractionPromptTemplate:
    def test_template_is_string(self):
        assert isinstance(EXTRACTION_PROMPT_TEMPLATE, str)

    def test_template_has_url_placeholder(self):
        assert "{url}" in EXTRACTION_PROMPT_TEMPLATE

    def test_template_has_query_placeholder(self):
        assert "{query}" in EXTRACTION_PROMPT_TEMPLATE

    def test_template_has_content_placeholder(self):
        assert "{content}" in EXTRACTION_PROMPT_TEMPLATE

    def test_template_has_schema_placeholder(self):
        assert "{schema}" in EXTRACTION_PROMPT_TEMPLATE

    def test_template_mentions_json(self):
        assert "JSON" in EXTRACTION_PROMPT_TEMPLATE

    def test_template_format_with_values(self):
        result = EXTRACTION_PROMPT_TEMPLATE.replace("{url}", "https://example.com").replace("{query}", "extract title").replace("{content}", "page content").replace("{schema}", '{"title": "string"}')
        assert "https://example.com" in result
        assert "extract title" in result
        assert "page content" in result
        assert "string" in result
