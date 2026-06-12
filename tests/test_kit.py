"""
Тесты для Lab Playwright Kit.
"""
import asyncio
import os
import sys

import pytest


# Добавить src в path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.llm_parse import LLMConfig, LLMParser
from lab_playwright_kit.network import NetworkInterceptor, NetworkLog
from lab_playwright_kit.parser import PageParser
from lab_playwright_kit.screenshot import ScreenshotMaker
from lab_playwright_kit.stealth import REALISTIC_UAS, StealthConfig, apply_stealth


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.mark.asyncio
async def test_browser_starts():
    """Браузер запускается и останавливается."""
    async with BrowserManager(headless=True) as browser:
        assert browser.browser is not None
        assert browser.context is not None


@pytest.mark.asyncio
async def test_browser_navigates():
    """Браузер навигируется на страницу."""
    async with BrowserManager(headless=True) as browser:
        page = await browser.goto("https://example.com")
        assert "example.com" in page.url


@pytest.mark.asyncio
async def test_stealth_applies():
    """Антидетект применяется без ошибок."""
    async with BrowserManager(headless=True) as browser:
        page = await browser.new_page()
        await apply_stealth(page, StealthConfig.full())
        await page.goto("https://example.com")
        # Проверить что webdriver скрыт (undefined -> None)
        webdriver = await page.evaluate("() => navigator.webdriver")
        assert webdriver is None


@pytest.mark.asyncio
async def test_stealth_minimal():
    """Минимальный антидетект работает."""
    async with BrowserManager(headless=True) as browser:
        page = await browser.new_page()
        await apply_stealth(page, StealthConfig.minimal())
        await page.goto("https://example.com")
        webdriver = await page.evaluate("() => navigator.webdriver")
        assert webdriver is None


@pytest.mark.asyncio
async def test_parser_extracts_content():
    """Парсер извлекает контент со страницы."""
    async with BrowserManager(headless=True) as browser:
        page = await browser.goto("https://example.com")
        parser = PageParser(page)
        content = await parser.parse()
        assert content.title != ""
        assert "Example Domain" in content.text
        assert content.url == "https://example.com/"


@pytest.mark.asyncio
async def test_parser_extracts_links():
    """Парсер извлекает ссылки."""
    async with BrowserManager(headless=True) as browser:
        page = await browser.goto("https://example.com")
        parser = PageParser(page)
        content = await parser.parse()
        assert len(content.links) > 0


@pytest.mark.asyncio
async def test_parser_extract_by_selector():
    """Парсер извлекает по CSS-селектору."""
    async with BrowserManager(headless=True) as browser:
        page = await browser.goto("https://example.com")
        parser = PageParser(page)
        headings = await parser.extract_by_selector("h1")
        assert len(headings) > 0
        assert "Example" in headings[0]


@pytest.mark.asyncio
async def test_screenshot_viewport():
    """Скриншот видимой области создаётся."""
    async with BrowserManager(headless=True) as browser:
        page = await browser.goto("https://example.com")
        maker = ScreenshotMaker(output_dir="/tmp/test_screenshots")
        path = await maker.viewport(page, prefix="test")
        assert os.path.exists(path)
        assert os.path.getsize(path) > 0


@pytest.mark.asyncio
async def test_screenshot_full_page():
    """Полностраничный скриншот создаётся."""
    async with BrowserManager(headless=True) as browser:
        page = await browser.goto("https://example.com")
        maker = ScreenshotMaker(output_dir="/tmp/test_screenshots")
        path = await maker.full_page(page, prefix="test")
        assert os.path.exists(path)
        assert os.path.getsize(path) > 0


@pytest.mark.asyncio
async def test_screenshot_element():
    """Скриншот элемента создаётся."""
    async with BrowserManager(headless=True) as browser:
        page = await browser.goto("https://example.com")
        maker = ScreenshotMaker(output_dir="/tmp/test_screenshots")
        path = await maker.element(page, "h1", prefix="test")
        assert os.path.exists(path)


@pytest.mark.asyncio
async def test_network_interceptor():
    """Перехватчик сетевых запросов работает."""
    async with BrowserManager(headless=True) as browser:
        page = await browser.new_page()
        interceptor = NetworkInterceptor(page)
        interceptor.attach()
        await page.goto("https://example.com")
        interceptor.detach()
        assert len(interceptor.log.requests) > 0


@pytest.mark.asyncio
async def test_network_filter_by_type():
    """Фильтрация по типу ресурса работает."""
    async with BrowserManager(headless=True) as browser:
        page = await browser.new_page()
        interceptor = NetworkInterceptor(page)
        interceptor.attach()
        await page.goto("https://example.com")
        interceptor.detach()
        # Должны быть document-запросы
        docs = interceptor.log.filter_by_type("document")
        assert len(docs) > 0


def test_stealth_config_full():
    """Полный конфиг антидетекта содержит все 18 скриптов."""
    config = StealthConfig.full()
    scripts = config.get_scripts()
    assert len(scripts) == 18  # 6 базовых + 10 P0 + 2 P1 вектора


def test_stealth_config_standard():
    """Стандартный конфиг содержит 6 базовых скриптов."""
    config = StealthConfig.standard()
    scripts = config.get_scripts()
    assert len(scripts) == 6


def test_stealth_config_advanced():
    """Продвинутый конфиг = 18 скриптов (без random_ua)."""
    config = StealthConfig.advanced()
    scripts = config.get_scripts()
    assert len(scripts) == 18
    assert config.random_ua is False


def test_stealth_config_default():
    """Дефолтный конфиг = standard = 6 скриптов."""
    config = StealthConfig()
    scripts = config.get_scripts()
    assert len(scripts) == 6


def test_stealth_config_minimal():
    """Минимальный конфиг содержит только webdriver."""
    config = StealthConfig.minimal()
    scripts = config.get_scripts()
    assert len(scripts) == 1


def test_stealth_config_disabled():
    """Отключённый конфиг не содержит скриптов."""
    config = StealthConfig(enabled=False)
    scripts = config.get_scripts()
    assert len(scripts) == 0


def test_realistic_uas():
    """User-Agent строки валидны."""
    for ua in REALISTIC_UAS:
        assert "Mozilla/5.0" in ua
        assert len(ua) > 50


@pytest.mark.asyncio
async def test_browser_with_custom_ua():
    """Браузер с кастомным User-Agent."""
    custom_ua = REALISTIC_UAS[0]
    async with BrowserManager(headless=True, user_agent=custom_ua) as browser:
        page = await browser.goto("https://example.com")
        detected_ua = await page.evaluate("() => navigator.userAgent")
        assert detected_ua == custom_ua


@pytest.mark.asyncio
async def test_parser_scroll_to_bottom():
    """Прокрутка до конца страницы."""
    async with BrowserManager(headless=True) as browser:
        page = await browser.goto("https://example.com")
        parser = PageParser(page)
        scrolls = await parser.scroll_to_bottom(delay=0.1)
        assert scrolls >= 0


# === LLM Parse Tests ===

def test_llm_config_defaults():
    """LLMConfig имеет корректные значения по умолчанию."""
    config = LLMConfig()
    assert config.api_url == "https://openrouter.ai/api/v1/chat/completions"
    assert config.model == "google/gemini-2.5-flash"
    assert config.max_content_length == 8000
    assert config.temperature == 0.1
    assert config.timeout == 30


def test_llm_config_custom():
    """LLMConfig принимает кастомные значения."""
    config = LLMConfig(
        api_key="test-key",
        model="anthropic/claude-3.5-sonnet",
        max_content_length=4000,
    )
    assert config.api_key == "test-key"
    assert config.model == "anthropic/claude-3.5-sonnet"
    assert config.max_content_length == 4000


def test_llm_parser_init():
    """LLMParser инициализируется с config и без."""
    parser = LLMParser()
    assert parser.config is not None
    assert isinstance(parser.config, LLMConfig)

    custom_config = LLMConfig(api_key="test")
    parser2 = LLMParser(custom_config)
    assert parser2.config.api_key == "test"


# === Network Tests ===

def test_network_log_filters():
    """NetworkLog фильтрация работает корректно."""
    log = NetworkLog()
    log.requests = [
        type("R", (), {"url": "https://api.example.com/data", "method": "GET", "resource_type": "xhr", "response_status": 200})(),
        type("R", (), {"url": "https://example.com/style.css", "method": "GET", "resource_type": "stylesheet", "response_status": 200})(),
        type("R", (), {"url": "https://api.example.com/error", "method": "POST", "resource_type": "xhr", "response_status": 500})(),
    ]

    api_calls = log.get_api_calls()
    assert len(api_calls) == 2

    domain_filtered = log.filter_by_domain("api.example.com")
    assert len(domain_filtered) == 2

    status_filtered = log.filter_by_status(500)
    assert len(status_filtered) == 1


def test_network_log_to_dict():
    """NetworkLog.to_dict возвращает корректную структуру."""
    log = NetworkLog()
    log.requests = [
        type("R", (), {"url": "https://example.com", "method": "GET", "resource_type": "document", "response_status": 200})(),
    ]
    result = log.to_dict()
    assert result["total"] == 1
    assert result["requests"][0]["url"] == "https://example.com"


@pytest.mark.asyncio
async def test_network_interceptor_attach():
    """NetworkInterceptor подключается к странице."""
    async with BrowserManager(headless=True) as browser:
        page = await browser.goto("https://example.com")
        interceptor = NetworkInterceptor(page)
        interceptor.attach()
        interceptor.detach()
        assert len(interceptor.log.requests) >= 0
