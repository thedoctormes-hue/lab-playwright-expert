"""
Tests for LLM-Powered Browser Agent.
Covers: AgentMemory, AgentAction, MockLLM, _parse_llm_decision, BrowserAgent config.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys
from pathlib import Path
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from scripts.llm_browser_agent import (
    AgentAction,
    AgentActionType,
    AgentMemory,
    MockLLM,
    BrowserAgent,
    _parse_llm_decision,
    AGENT_SYSTEM_PROMPT,
    AGENT_USER_PROMPT_TEMPLATE,
    DEFAULT_MODEL,
    DEFAULT_MAX_STEPS,
    MAX_SNAPSHOT_LENGTH,
    MAX_HISTORY_LENGTH,
)


# ═══════════════════════════════════════════════════════════════════════════════
# AgentAction
# ═══════════════════════════════════════════════════════════════════════════════

class TestAgentAction:
    """Tests for AgentAction dataclass."""

    def test_creation(self):
        """Создание действия агента."""
        action = AgentAction(
            step=1,
            action_type="navigate",
            params={"url": "https://example.com"},
            reasoning="Test navigation",
        )
        assert action.step == 1
        assert action.action_type == "navigate"
        assert action.params["url"] == "https://example.com"
        assert action.reasoning == "Test navigation"
        assert action.result == ""
        assert action.duration_ms == 0

    def test_default_timestamp(self):
        """Timestamp генерируется автоматически."""
        action = AgentAction(step=1, action_type="click", params={"selector": "button"})
        assert action.timestamp != ""

    def test_all_action_types(self):
        """Все типы действий через enum."""
        assert AgentActionType.NAVIGATE.value == "navigate"
        assert AgentActionType.CLICK.value == "click"
        assert AgentActionType.TYPE.value == "type"
        assert AgentActionType.SCROLL.value == "scroll"
        assert AgentActionType.EXTRACT.value == "extract"
        assert AgentActionType.SCREENSHOT.value == "screenshot"
        assert AgentActionType.WAIT.value == "wait"
        assert AgentActionType.DONE.value == "done"


# ═══════════════════════════════════════════════════════════════════════════════
# AgentMemory
# ═══════════════════════════════════════════════════════════════════════════════

class TestAgentMemory:
    """Tests for AgentMemory."""

    def test_default_creation(self):
        """Создание памяти с дефолтными значениями."""
        mem = AgentMemory()
        assert mem.goal == ""
        assert mem.start_url == ""
        assert mem.current_url == ""
        assert mem.visited_urls == []
        assert mem.actions == []
        assert mem.extracted_data == []
        assert mem.page_titles == []
        assert mem.errors == []
        assert mem.screenshots == []

    def test_creation_with_goal(self):
        """Создание памяти с целью."""
        mem = AgentMemory(goal="Find AI news", start_url="https://news.ycombinator.com")
        assert mem.goal == "Find AI news"
        assert mem.start_url == "https://news.ycombinator.com"

    def test_add_action(self):
        """Добавление действия."""
        mem = AgentMemory()
        action = AgentAction(step=1, action_type="navigate", params={"url": "https://example.com"})
        mem.add_action(action)
        assert len(mem.actions) == 1

    def test_add_navigation_action_tracks_url(self):
        """Навигация отслеживает URL."""
        mem = AgentMemory()
        action = AgentAction(
            step=1,
            action_type=AgentActionType.NAVIGATE,
            params={"url": "https://example.com"},
        )
        mem.add_action(action)
        assert "https://example.com" in mem.visited_urls
        assert mem.current_url == "https://example.com"

    def test_add_duplicate_navigation_not_double_counted(self):
        """Дублирующая навигация не добавляет URL дважды."""
        mem = AgentMemory()
        url = "https://example.com"
        mem.add_action(AgentAction(
            step=1, action_type=AgentActionType.NAVIGATE, params={"url": url}
        ))
        mem.add_action(AgentAction(
            step=2, action_type=AgentActionType.NAVIGATE, params={"url": url}
        ))
        assert mem.visited_urls.count(url) == 1

    def test_add_extracted(self):
        """Добавление извлечённых данных."""
        mem = AgentMemory()
        mem.add_extracted({"title": "Test", "headings": ["H1", "H2"]})
        assert len(mem.extracted_data) == 1
        assert mem.extracted_data[0]["title"] == "Test"

    def test_add_screenshot(self):
        """Добавление скриншота."""
        mem = AgentMemory()
        mem.add_screenshot("/tmp/screenshot_001.png")
        assert len(mem.screenshots) == 1
        assert mem.screenshots[0] == "/tmp/screenshot_001.png"

    def test_add_error(self):
        """Добавление ошибки."""
        mem = AgentMemory()
        mem.add_error("Timeout on step 3")
        assert len(mem.errors) == 1
        assert mem.errors[0] == "Timeout on step 3"

    def test_get_history_summary_empty(self):
        """История действий — пустая."""
        mem = AgentMemory()
        summary = mem.get_history_summary()
        assert summary == "  (no actions yet)"

    def test_get_history_summary_with_actions(self):
        """История действий — с действиями."""
        mem = AgentMemory()
        mem.add_action(AgentAction(
            step=1, action_type="navigate", params={"url": "https://example.com"},
            result="OK",
        ))
        mem.add_action(AgentAction(
            step=2, action_type="extract", params={"schema": {}},
            result="Extracted 3 fields",
        ))
        summary = mem.get_history_summary()
        assert "Step 1" in summary
        assert "navigate" in summary
        assert "Step 2" in summary
        assert "extract" in summary

    def test_get_history_summary_error_marker(self):
        """История действий — маркер ошибки."""
        mem = AgentMemory()
        mem.add_action(AgentAction(
            step=1, action_type="click", params={"selector": "button"},
            result="ERROR: Element not found",
        ))
        summary = mem.get_history_summary()
        assert "✗" in summary

    def test_get_history_summary_success_marker(self):
        """История действий — маркер успеха."""
        mem = AgentMemory()
        mem.add_action(AgentAction(
            step=1, action_type="click", params={"selector": "button"},
            result="Clicked successfully",
        ))
        summary = mem.get_history_summary()
        assert "✓" in summary

    def test_get_history_summary_max_length(self):
        """История действий — ограничение по длине."""
        mem = AgentMemory()
        for i in range(20):
            mem.add_action(AgentAction(
                step=i + 1, action_type="click", params={"selector": f"btn{i}"},
                result="OK",
            ))
        summary = mem.get_history_summary()
        # Должны быть только последние MAX_HISTORY_LENGTH действий
        lines = [l for l in summary.split("\n") if l.strip()]
        assert len(lines) <= MAX_HISTORY_LENGTH

    def test_to_dict(self):
        """Сериализация в dict."""
        mem = AgentMemory(goal="test", start_url="https://example.com")
        mem.add_action(AgentAction(
            step=1, action_type="navigate", params={"url": "https://example.com"},
            result="OK",
        ))
        mem.add_extracted({"title": "Test"})
        mem.add_error("Some error")
        mem.add_screenshot("/tmp/ss.png")

        d = mem.to_dict()
        assert d["goal"] == "test"
        assert d["start_url"] == "https://example.com"
        assert len(d["actions"]) == 1
        assert len(d["extracted_data"]) == 1
        assert len(d["errors"]) == 1
        assert len(d["screenshots"]) == 1

    def test_to_dict_action_fields(self):
        """Поля action в to_dict."""
        mem = AgentMemory()
        mem.add_action(AgentAction(
            step=5, action_type="click", params={"selector": "button"},
            reasoning="Need to click", result="Clicked", duration_ms=150.0,
        ))

        d = mem.to_dict()
        action_d = d["actions"][0]
        assert action_d["step"] == 5
        assert action_d["action_type"] == "click"
        assert action_d["params"]["selector"] == "button"
        assert action_d["reasoning"] == "Need to click"
        assert action_d["result"] == "Clicked"
        assert action_d["duration_ms"] == 150.0
        assert "timestamp" in action_d


# ═══════════════════════════════════════════════════════════════════════════════
# _parse_llm_decision
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseLLMDecision:
    """Tests for _parse_llm_decision function."""

    def test_valid_json(self):
        """Парсинг валидного JSON."""
        raw = '{"action": "navigate", "params": {"url": "https://example.com"}, "reasoning": "test"}'
        result = _parse_llm_decision(raw)
        assert result["action"] == "navigate"
        assert result["params"]["url"] == "https://example.com"
        assert result["reasoning"] == "test"

    def test_json_with_markdown(self):
        """Парсинг JSON внутри markdown."""
        raw = '```json\n{"action": "click", "params": {"selector": "button"}, "reasoning": "click btn"}\n```'
        result = _parse_llm_decision(raw)
        assert result["action"] == "click"
        assert result["params"]["selector"] == "button"

    def test_json_with_surrounding_text(self):
        """Парсинг JSON с окружающим текстом."""
        raw = 'I think the best action is: {"action": "done", "params": {"result": "finished"}, "reasoning": "complete"} Thanks!'
        result = _parse_llm_decision(raw)
        assert result["action"] == "done"
        assert result["params"]["result"] == "finished"

    def test_invalid_json_fallback(self):
        """Невалидный JSON — fallback."""
        raw = "This is not JSON at all"
        result = _parse_llm_decision(raw)
        assert result["action"] == "done"
        assert result["reasoning"] == "parse_fallback"
        assert result["params"]["result"] == raw

    def test_empty_string_fallback(self):
        """Пустая строка — fallback."""
        result = _parse_llm_decision("")
        assert result["action"] == "done"
        assert result["reasoning"] == "parse_fallback"

    def test_partial_json_fallback(self):
        """Неполный JSON — fallback."""
        raw = '{"action": "navigate", "params": {"url":'
        result = _parse_llm_decision(raw)
        assert result["action"] == "done"
        assert result["reasoning"] == "parse_fallback"

    def test_extract_action(self):
        """Парсинг extract действия."""
        raw = '{"action": "extract", "params": {"schema": {"title": "h1"}}, "reasoning": "extract data"}'
        result = _parse_llm_decision(raw)
        assert result["action"] == "extract"
        assert result["params"]["schema"]["title"] == "h1"

    def test_done_action(self):
        """Парсинг done действия."""
        raw = '{"action": "done", "params": {"result": "Task complete"}, "reasoning": "finished"}'
        result = _parse_llm_decision(raw)
        assert result["action"] == "done"
        assert result["params"]["result"] == "Task complete"


# ═══════════════════════════════════════════════════════════════════════════════
# MockLLM
# ═══════════════════════════════════════════════════════════════════════════════

class TestMockLLM:
    """Tests for MockLLM."""

    def test_creation(self):
        """Создание MockLLM."""
        llm = MockLLM()
        assert llm._call_count == 0

    @pytest.mark.asyncio
    async def test_extraction_goal_first_step(self):
        """Цель извлечения данных — первый шаг."""
        llm = MockLLM()
        result = await llm.decide(
            goal="Extract all titles and dates",
            url="https://example.com",
            title="Example",
            snapshot="- heading: Test",
            history="",
            step=1,
            max_steps=10,
        )
        assert result["action"] == "extract"
        assert "schema" in result["params"]

    @pytest.mark.asyncio
    async def test_extraction_goal_second_step(self):
        """Цель извлечения данных — после второго шага завершает."""
        llm = MockLLM()
        result = await llm.decide(
            goal="Extract all titles",
            url="https://example.com",
            title="Example",
            snapshot="- heading: Test",
            history="",
            step=3,
            max_steps=10,
        )
        assert result["action"] == "done"

    @pytest.mark.asyncio
    async def test_navigation_goal(self):
        """Цель навигации."""
        llm = MockLLM()
        result = await llm.decide(
            goal="Navigate to example.com",
            url="https://example.com",
            title="Example",
            snapshot="",
            history="",
            step=1,
            max_steps=10,
        )
        assert result["action"] == "done"
        assert "Navigation" in result["params"]["result"]

    @pytest.mark.asyncio
    async def test_default_goal_first_step(self):
        """Дефолтная цель — первый шаг извлекает."""
        llm = MockLLM()
        result = await llm.decide(
            goal="Browse the page",
            url="https://example.com",
            title="Example",
            snapshot="",
            history="",
            step=1,
            max_steps=10,
        )
        assert result["action"] == "extract"

    @pytest.mark.asyncio
    async def test_default_goal_second_step(self):
        """Дефолтная цель — второй шаг завершает."""
        llm = MockLLM()
        result = await llm.decide(
            goal="Browse the page",
            url="https://example.com",
            title="Example",
            snapshot="",
            history="",
            step=2,
            max_steps=10,
        )
        assert result["action"] == "done"

    @pytest.mark.asyncio
    async def test_call_count_increments(self):
        """Счётчик вызовов увеличивается."""
        llm = MockLLM()
        assert llm._call_count == 0
        await llm.decide("test", "", "", "", "", 1, 10)
        assert llm._call_count == 1
        await llm.decide("test", "", "", "", "", 2, 10)
        assert llm._call_count == 2

    @pytest.mark.asyncio
    async def test_russian_extraction_keywords(self):
        """Русские ключевые слова извлечения."""
        llm = MockLLM()
        for keyword in ["извлечь", "найти", "собрать"]:
            result = await llm.decide(
                goal=f"{keyword} данные",
                url="https://example.com",
                title="Test",
                snapshot="",
                history="",
                step=1,
                max_steps=10,
            )
            assert result["action"] == "extract", f"Failed for keyword: {keyword}"

    @pytest.mark.asyncio
    async def test_russian_navigation_keywords(self):
        """Русские ключевые слова навигации."""
        llm = MockLLM()
        for keyword in ["перейти", "открыть", "зайти"]:
            result = await llm.decide(
                goal=f"{keyword} на сайт",
                url="https://example.com",
                title="Test",
                snapshot="",
                history="",
                step=1,
                max_steps=10,
            )
            assert result["action"] == "done", f"Failed for keyword: {keyword}"


# ═══════════════════════════════════════════════════════════════════════════════
# BrowserAgent Configuration
# ═══════════════════════════════════════════════════════════════════════════════

class TestBrowserAgentConfig:
    """Tests for BrowserAgent configuration and initialization."""

    def test_default_creation(self):
        """Создание агента с дефолтными параметрами."""
        agent = BrowserAgent(goal="Test goal")
        assert agent.goal == "Test goal"
        assert agent.start_url == ""
        assert agent.max_steps == DEFAULT_MAX_STEPS
        assert agent.model == DEFAULT_MODEL
        assert agent.output_file == ""
        assert agent.verbose is False
        assert agent.stealth_enabled is True
        assert agent.headless is True
        assert agent.mock_mode is False
        assert agent.behavior_profile == "casual_reader"

    def test_custom_creation(self):
        """Создание агента с кастомными параметрами."""
        agent = BrowserAgent(
            goal="Find news",
            start_url="https://news.ycombinator.com",
            max_steps=15,
            model="gpt-4",
            api_key="test-key",
            output_file="/tmp/result.json",
            verbose=True,
            stealth=False,
            headless=False,
            mock=True,
            behavior_profile="power_user",
        )
        assert agent.goal == "Find news"
        assert agent.start_url == "https://news.ycombinator.com"
        assert agent.max_steps == 15
        assert agent.model == "gpt-4"
        assert agent.output_file == "/tmp/result.json"
        assert agent.verbose is True
        assert agent.stealth_enabled is False
        assert agent.headless is False
        assert agent.mock_mode is True
        assert agent.behavior_profile == "power_user"

    def test_memory_initialized(self):
        """Память агента инициализирована."""
        agent = BrowserAgent(goal="Test", start_url="https://example.com")
        assert agent.memory.goal == "Test"
        assert agent.memory.start_url == "https://example.com"

    def test_fingerprint_generated(self):
        """Fingerprint генерируется при создании."""
        agent = BrowserAgent(goal="Test")
        assert agent.fingerprint is not None
        assert agent.fingerprint.profile_id.startswith("agent_")

    def test_stealth_config(self):
        """Stealth config создаётся."""
        agent = BrowserAgent(goal="Test", stealth=True)
        assert agent.stealth_config is not None
        assert agent.stealth_config.enabled is True

    def test_stealth_disabled_config(self):
        """Stealth отключен — используется minimal config."""
        agent = BrowserAgent(goal="Test", stealth=False)
        assert agent.stealth_config is not None
        # minimal() still has enabled=True but with minimal protections
        assert agent.stealth_config.mask_webdriver is True
        assert agent.stealth_config.mask_plugins is False
        assert agent.stealth_config.fake_webgl is False

    def test_mock_llm_created(self):
        """MockLLM создаётся в mock-режиме."""
        agent = BrowserAgent(goal="Test", mock=True)
        assert agent.mock_llm is not None

    def test_mock_llm_not_created(self):
        """MockLLM не создаётся без mock-режима."""
        agent = BrowserAgent(goal="Test", mock=False)
        assert agent.mock_llm is None

    def test_llm_config(self):
        """LLM config создаётся."""
        agent = BrowserAgent(goal="Test", api_key="key123", model="custom-model")
        assert agent.llm_config.api_key == "key123"
        assert agent.llm_config.model == "custom-model"

    def test_build_result_structure(self):
        """Структура результата _build_result."""
        agent = BrowserAgent(goal="Test goal")
        agent.memory.add_action(AgentAction(
            step=1, action_type="navigate", params={"url": "https://example.com"},
            result="OK",
        ))
        agent.memory.add_extracted({"title": "Test"})

        result = agent._build_result(total_time=1.5)

        assert result["goal"] == "Test goal"
        assert result["status"] == "completed"
        assert result["total_time_seconds"] == 1.5
        assert result["total_steps"] == 1
        assert len(result["extracted_data"]) == 1
        assert "agent_config" in result
        assert "action_history" in result

    def test_build_result_incomplete(self):
        """Результат без данных — incomplete."""
        agent = BrowserAgent(goal="Test")
        result = agent._build_result(total_time=0.5)
        assert result["status"] == "incomplete"

    def test_build_result_config_fields(self):
        """Поля agent_config в результате."""
        agent = BrowserAgent(
            goal="Test", model="gpt-4", max_steps=20,
            mock=True, stealth=False, headless=False,
        )
        result = agent._build_result(0.0)
        config = result["agent_config"]
        assert config["model"] == "gpt-4"
        assert config["max_steps"] == 20
        assert config["mock_mode"] is True
        assert config["stealth"] is False
        assert config["headless"] is False

    def test_save_result(self):
        """Сохранение результата в файл."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            agent = BrowserAgent(goal="Test", output_file=path)
            result = {"goal": "Test", "status": "completed"}
            agent._save_result(result)

            with open(path) as f:
                saved = json.load(f)
            assert saved["goal"] == "Test"
        finally:
            os.unlink(path)

    def test_save_result_creates_directories(self):
        """Сохранение результата создаёт директории."""
        import shutil
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "subdir", "result.json")

        try:
            agent = BrowserAgent(goal="Test", output_file=path)
            agent._save_result({"goal": "Test"})
            assert os.path.exists(path)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Prompt Templates
# ═══════════════════════════════════════════════════════════════════════════════

class TestPromptTemplates:
    """Tests for LLM prompt templates."""

    def test_system_prompt_contains_actions(self):
        """Системный промпт содержит все действия."""
        assert "navigate" in AGENT_SYSTEM_PROMPT
        assert "click" in AGENT_SYSTEM_PROMPT
        assert "type" in AGENT_SYSTEM_PROMPT
        assert "scroll" in AGENT_SYSTEM_PROMPT
        assert "extract" in AGENT_SYSTEM_PROMPT
        assert "done" in AGENT_SYSTEM_PROMPT

    def test_system_prompt_contains_rules(self):
        """Системный промпт содержит правила."""
        assert "JSON" in AGENT_SYSTEM_PROMPT
        assert "max_steps" in AGENT_SYSTEM_PROMPT

    def test_user_prompt_template_format(self):
        """Шаблон пользовательского промпта форматируется."""
        prompt = AGENT_USER_PROMPT_TEMPLATE.format(
            goal="Test goal",
            url="https://example.com",
            title="Test Title",
            snapshot="- heading: Test",
            history="  (no actions yet)",
            step=1,
            max_steps=10,
        )
        assert "Test goal" in prompt
        assert "https://example.com" in prompt
        assert "Test Title" in prompt
        assert "1/10" in prompt

    def test_user_prompt_template_with_long_snapshot(self):
        """Шаблон с длинным snapshot обрезается."""
        long_snapshot = "x" * 10000
        prompt = AGENT_USER_PROMPT_TEMPLATE.format(
            goal="Test",
            url="https://example.com",
            title="Test",
            snapshot=long_snapshot,
            history="",
            step=1,
            max_steps=10,
        )
        assert len(prompt) < len(long_snapshot) + 1000  # snapshot truncated


# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

class TestConstants:
    """Tests for module constants."""

    def test_default_model(self):
        assert DEFAULT_MODEL == "google/gemini-2.5-flash"

    def test_default_max_steps(self):
        assert DEFAULT_MAX_STEPS == 20

    def test_max_snapshot_length(self):
        assert MAX_SNAPSHOT_LENGTH == 6000

    def test_max_history_length(self):
        assert MAX_HISTORY_LENGTH == 10
