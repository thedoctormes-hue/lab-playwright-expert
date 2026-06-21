"""
Расширенные тесты для LLMParser.

Покрывает:
  - LLMConfig dataclass
  - LLMParser.__init__
  - LLMParser.config property
"""

from __future__ import annotations

from lab_playwright_kit.llm_parse import LLMConfig, LLMParser


# ─── LLMConfig ─────────────────────────────────────────────────────────────


class TestLLMConfig:
    def test_defaults(self):
        cfg = LLMConfig()
        assert cfg.api_url == "https://openrouter.ai/api/v1/chat/completions"
        assert cfg.api_key == ""
        assert cfg.model == "google/gemini-2.5-flash"
        assert cfg.max_content_length == 8000
        assert cfg.temperature == 0.1
        assert cfg.timeout == 30

    def test_custom(self):
        cfg = LLMConfig(
            api_url="https://custom.api/v1",
            api_key="sk-test",
            model="gpt-4",
            max_content_length=4000,
            temperature=0.5,
            timeout=60,
        )
        assert cfg.api_url == "https://custom.api/v1"
        assert cfg.api_key == "sk-test"
        assert cfg.model == "gpt-4"
        assert cfg.max_content_length == 4000
        assert cfg.temperature == 0.5
        assert cfg.timeout == 60


# ─── LLMParser ─────────────────────────────────────────────────────────────


class TestLLMParser:
    def test_default_init(self):
        parser = LLMParser()
        assert parser.config is not None
        assert isinstance(parser.config, LLMConfig)

    def test_custom_config(self):
        cfg = LLMConfig(model="gpt-4", api_key="test-key")
        parser = LLMParser(config=cfg)
        assert parser.config is cfg
        assert parser.config.model == "gpt-4"

    def test_config_defaults(self):
        parser = LLMParser()
        assert parser.config.api_url == "https://openrouter.ai/api/v1/chat/completions"
        assert parser.config.model == "google/gemini-2.5-flash"
