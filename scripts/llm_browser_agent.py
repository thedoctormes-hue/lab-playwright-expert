#!/usr/bin/env python3
"""
LLM-Powered Browser Agent — автономный браузерный агент на базе LLM.

Архитектура: Perception → Planning → Action → Memory (Agent Loop).

Использование:
    PYTHONPATH=src python3 scripts/llm_browser_agent.py \\
      --goal "Find the latest news about AI and extract titles and dates" \\
      --start-url https://news.ycombinator.com \\
      --max-steps 10 \\
      --output /tmp/agent_result.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

# ─── Imports from lab_playwright_kit ──────────────────────────────────────────
from loguru import logger

from lab_playwright_kit import (
    ARIASnapshot,
    BrowserManager,
    FingerprintManager,
    HumanBehaviorEngine,
    PageParser,
    ScreenshotMaker,
    StealthConfig,
)
from lab_playwright_kit.llm_parse import LLMConfig, LLMParser


# ─── Constants ────────────────────────────────────────────────────────────────

DEFAULT_MODEL = "google/gemini-2.5-flash"
DEFAULT_MAX_STEPS = 20
DEFAULT_TIMEOUT = 30000
MAX_SNAPSHOT_LENGTH = 6000  # chars sent to LLM
MAX_HISTORY_LENGTH = 10  # last N actions kept in memory

# ─── Agent Action Types ───────────────────────────────────────────────────────

class AgentActionType(str, Enum):
    """Типы действий, которые агент может выполнить."""
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    EXTRACT = "extract"
    SCREENSHOT = "screenshot"
    WAIT = "wait"
    DONE = "done"


# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class AgentAction:
    """Одно действие агента."""
    step: int
    action_type: str
    params: dict[str, Any]
    reasoning: str = ""
    result: str = ""
    duration_ms: float = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class AgentMemory:
    """Память агента — отслеживает контекст выполнения."""
    goal: str = ""
    start_url: str = ""
    current_url: str = ""
    visited_urls: list[str] = field(default_factory=list)
    actions: list[AgentAction] = field(default_factory=list)
    extracted_data: list[dict[str, Any]] = field(default_factory=list)
    page_titles: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)

    def add_action(self, action: AgentAction) -> None:
        self.actions.append(action)
        if action.action_type == AgentActionType.NAVIGATE:
            url = action.params.get("url", "")
            if url and url not in self.visited_urls:
                self.visited_urls.append(url)
                self.current_url = url

    def add_extracted(self, data: dict[str, Any]) -> None:
        self.extracted_data.append(data)

    def add_screenshot(self, path: str) -> None:
        self.screenshots.append(path)

    def add_error(self, error: str) -> None:
        self.errors.append(error)

    def get_history_summary(self) -> str:
        """Краткая сводка истории действий для LLM."""
        lines = []
        for a in self.actions[-MAX_HISTORY_LENGTH:]:
            status = "✓" if not a.result.startswith("ERROR") else "✗"
            lines.append(
                f"  Step {a.step}: [{status}] {a.action_type} "
                f"{a.params} → {a.result[:100]}"
            )
        return "\n".join(lines) if lines else "  (no actions yet)"

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "start_url": self.start_url,
            "current_url": self.current_url,
            "visited_urls": self.visited_urls,
            "actions": [
                {
                    "step": a.step,
                    "action_type": a.action_type,
                    "params": a.params,
                    "reasoning": a.reasoning,
                    "result": a.result,
                    "duration_ms": a.duration_ms,
                    "timestamp": a.timestamp,
                }
                for a in self.actions
            ],
            "extracted_data": self.extracted_data,
            "page_titles": self.page_titles,
            "errors": self.errors,
            "screenshots": self.screenshots,
        }


# ─── LLM Decision Parser ─────────────────────────────────────────────────────

# Системный промпт для агента
AGENT_SYSTEM_PROMPT = """Ты — автономный браузерный агент. Твоя задача — выполнить цель пользователя, взаимодействуя с веб-браузером.

ДОСТУПНЫЕ ДЕЙСТВИЯ:
1. navigate(url) — перейти на URL
2. click(selector) — кликнуть по элементу (CSS-селектор)
3. type(selector, text) — ввести текст в поле
4. scroll(direction, amount) — прокрутить (direction: up/down, amount: 1-5)
5. extract(schema) — извлечь структурированные данные (schema: JSON с полями)
6. screenshot() — сделать скриншот
7. wait(selector) — подождать появления элемента
8. done(result) — задача выполнена, вернуть результат

ПРАВИЛА:
- Отвечай ТОЛЬКО в формате JSON: {"action": "...", "params": {...}, "reasoning": "..."}
- Выбирай ОДНО действие за раз
- Если цель достигнута — используй done() с результатом
- Используй конкретные CSS-селекторы из ARIA snapshot
- Не делай больше {max_steps} шагов
- Если застрял — попробуй альтернативный подход
- Будь эффективен: не делай лишних действий
"""

AGENT_USER_PROMPT_TEMPLATE = """ЦЕЛЬ: {goal}

ТЕКУЩАЯ СТРАНИЦА:
- URL: {url}
- Заголовок: {title}

ARIA SNAPSHOT (элементы страницы):
{snapshot}

ИСТОРИЯ ДЕЙСТВИЙ:
{history}

ШАГ: {step}/{max_steps}

Какое действие выполнить следующим? Ответь JSON."""


def _parse_llm_decision(raw: str) -> dict[str, Any]:
    """Распарсить решение LLM из ответа."""
    # Попытаться найти JSON в ответе
    json_start = raw.find("{")
    json_end = raw.rfind("}") + 1

    if json_start >= 0 and json_end > json_start:
        try:
            return json.loads(raw[json_start:json_end])
        except json.JSONDecodeError:
            pass

    # Fallback: весь ответ как raw
    logger.warning(f"Could not parse LLM response as JSON: {raw[:200]}")
    return {"action": "done", "params": {"result": raw}, "reasoning": "parse_fallback"}


# ─── Mock LLM (для тестирования без API-ключа) ────────────────────────────────

class MockLLM:
    """Mock LLM для тестирования без API-ключа.

    Имитирует поведение агента на основе простых эвристик.
    """

    def __init__(self):
        self._call_count = 0

    async def decide(
        self,
        goal: str,
        url: str,
        title: str,
        snapshot: str,
        history: str,
        step: int,
        max_steps: int,
    ) -> dict[str, Any]:
        """Принять решение на основе эвристик."""
        self._call_count += 1
        logger.info(f"[MockLLM] Decision #{self._call_count} at step {step}")

        goal_lower = goal.lower()

        # Если есть цель извлечь данные — извлекаем
        if any(w in goal_lower for w in ["извлечь", "extract", "найти", "find", "собрать", "collect"]):
            if step <= 2:
                return {
                    "action": "extract",
                    "params": {
                        "schema": {
                            "title": "page title",
                            "headings": "list:h1, h2, h3",
                            "links": "list:a[href]",
                        }
                    },
                    "reasoning": "Goal requires data extraction, extracting page content",
                }
            else:
                return {
                    "action": "done",
                    "params": {"result": "Data extraction completed (mock)"},
                    "reasoning": "Extraction done, finishing",
                }

        # Если есть цель навигации
        if any(w in goal_lower for w in ["перейти", "navigate", "открыть", "open", "зайти"]):
            return {
                "action": "done",
                "params": {"result": f"Navigation to {url} completed (mock)"},
                "reasoning": "Navigation goal achieved",
            }

        # По умолчанию — извлечь данные и завершить
        if step == 1:
            return {
                "action": "extract",
                "params": {
                    "schema": {
                        "title": "page title",
                        "description": "meta[name='description']@content",
                    }
                },
                "reasoning": "First step: extracting basic page info",
            }
        else:
            return {
                "action": "done",
                "params": {"result": f"Goal completed (mock) at step {step}"},
                "reasoning": "Task complete",
            }


# ─── Browser Agent ────────────────────────────────────────────────────────────

class BrowserAgent:
    """LLM-Powered Browser Agent — автономный браузерный агент.

    Архитектура:
        Perception → Planning → Action → Memory (Agent Loop)

    Использование:
        >>> agent = BrowserAgent(goal="Find AI news", start_url="https://news.ycombinator.com")
        >>> result = await agent.run()
    """

    def __init__(
        self,
        goal: str,
        start_url: str = "",
        max_steps: int = DEFAULT_MAX_STEPS,
        model: str = DEFAULT_MODEL,
        api_key: str = "",
        output_file: str = "",
        verbose: bool = False,
        stealth: bool = True,
        headless: bool = True,
        mock: bool = False,
        behavior_profile: str = "casual_reader",
    ):
        self.goal = goal
        self.start_url = start_url
        self.max_steps = max_steps
        self.model = model
        self.output_file = output_file
        self.verbose = verbose
        self.stealth_enabled = stealth
        self.headless = headless
        self.mock_mode = mock
        self.behavior_profile = behavior_profile

        # ── Components ──
        self.memory = AgentMemory(goal=goal, start_url=start_url)
        self.llm_config = LLMConfig(
            api_key=api_key,
            model=model,
        )
        self.llm_parser = LLMParser(self.llm_config)
        self.mock_llm = MockLLM() if mock else None
        self.fingerprint = FingerprintManager.generate(
            profile_name=f"agent_{uuid.uuid4().hex[:8]}",
            os="windows",
            browser="chrome",
        )
        self.stealth_config = StealthConfig.standard() if stealth else StealthConfig.minimal()

        # ── Runtime state ──
        self._browser: BrowserManager | None = None
        self._page = None
        self._behavior: HumanBehaviorEngine | None = None
        self._parser: PageParser | None = None
        self._screenshot_maker: ScreenshotMaker | None = None

    # ─── Agent Loop ───────────────────────────────────────────────────────

    async def run(self) -> dict[str, Any]:
        """Запустить агент-луп."""
        logger.info("🚀 Browser Agent started")
        logger.info(f"   Goal: {self.goal}")
        logger.info(f"   Start URL: {self.start_url or '(none)'}")
        logger.info(f"   Max steps: {self.max_steps}")
        logger.info(f"   Model: {self.model}")
        logger.info(f"   Mock mode: {self.mock_mode}")
        logger.info(f"   Stealth: {self.stealth_enabled}")
        logger.info(f"   Fingerprint: {self.fingerprint.profile_id}")

        start_time = time.monotonic()

        try:
            # 1. Инициализация браузера
            await self._init_browser()

            # 2. Переход на стартовый URL (если указан)
            if self.start_url:
                await self._execute_action(
                    AgentAction(
                        step=0,
                        action_type=AgentActionType.NAVIGATE,
                        params={"url": self.start_url},
                        reasoning="Initial navigation",
                    )
                )

            # 3. Главный луп агента
            for step in range(1, self.max_steps + 1):
                logger.info(f"\n{'='*60}")
                logger.info(f"  STEP {step}/{self.max_steps}")
                logger.info(f"  URL: {self.memory.current_url}")
                logger.info(f"{'='*60}")

                # 3a. Perception: воспринять состояние страницы
                snapshot, title = await self._perceive()

                # 3b. Planning: LLM решает следующее действие
                decision = await self._think(snapshot, title, step)

                # 3c. Проверка завершения
                if decision.get("action") == "done":
                    result = decision.get("params", {}).get("result", "Completed")
                    action = AgentAction(
                        step=step,
                        action_type=AgentActionType.DONE,
                        params=decision.get("params", {}),
                        reasoning=decision.get("reasoning", ""),
                        result=str(result),
                    )
                    self.memory.add_action(action)
                    logger.info(f"✅ Goal achieved at step {step}: {result}")
                    break

                # 3d. Action: выполнить действие
                action = AgentAction(
                    step=step,
                    action_type=decision.get("action", "unknown"),
                    params=decision.get("params", {}),
                    reasoning=decision.get("reasoning", ""),
                )
                await self._execute_action(action)

                # 3e. Проверка достижения цели
                if await self._check_goal_achieved():
                    logger.info(f"✅ Goal achieved at step {step}")
                    break

            else:
                logger.warning(f"⚠️ Max steps ({self.max_steps}) reached without completing goal")

        except Exception as e:
            logger.error(f"❌ Agent error: {e}")
            self.memory.add_error(str(e))
            if self.verbose:
                import traceback
                traceback.print_exc()

        finally:
            await self._cleanup()

        # 4. Формирование результата
        total_time = time.monotonic() - start_time
        result = self._build_result(total_time)

        # 5. Сохранение результата
        if self.output_file:
            self._save_result(result)

        self._print_summary(result)
        return result

    # ─── Perception ────────────────────────────────────────────────────────

    async def _perceive(self) -> tuple[str, str]:
        """Воспринять состояние страницы: ARIA snapshot + заголовок."""
        logger.info("👁 Perceiving page...")

        # ARIA snapshot
        snapshot = ""
        try:
            snapshot = await ARIASnapshot.capture(self._page)
            snapshot = snapshot[:MAX_SNAPSHOT_LENGTH]
            logger.debug(f"ARIA snapshot: {len(snapshot)} chars")
        except Exception as e:
            logger.warning(f"ARIA snapshot failed: {e}")

        # Заголовок
        title = ""
        try:
            title = await self._page.title()
            self.memory.page_titles.append(title)
            logger.info(f"Page title: {title}")
        except Exception as e:
            logger.warning(f"Title extraction failed: {e}")

        return snapshot, title

    # ─── Planning (LLM) ───────────────────────────────────────────────────

    async def _think(self, snapshot: str, title: str, step: int) -> dict[str, Any]:
        """Отправить состояние страницы LLM и получить решение."""
        logger.info("🧠 Thinking...")

        if self.mock_mode and self.mock_llm:
            return await self.mock_llm.decide(
                goal=self.goal,
                url=self.memory.current_url,
                title=title,
                snapshot=snapshot,
                history=self.memory.get_history_summary(),
                step=step,
                max_steps=self.max_steps,
            )

        # Формируем промпт
        prompt = AGENT_USER_PROMPT_TEMPLATE.format(
            goal=self.goal,
            url=self.memory.current_url,
            title=title,
            snapshot=snapshot[:MAX_SNAPSHOT_LENGTH],
            history=self.memory.get_history_summary(),
            step=step,
            max_steps=self.max_steps,
        )

        # Вызов LLM
        try:
            async with self.llm_parser:
                pass  # LLMParser не имеет __aenter__, используем напрямую

            import httpx

            async with httpx.AsyncClient(timeout=self.llm_config.timeout) as client:
                response = await client.post(
                    self.llm_config.api_url,
                    headers={
                        "Authorization": f"Bearer {self.llm_config.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.llm_config.model,
                        "messages": [
                            {"role": "system", "content": AGENT_SYSTEM_PROMPT.format(max_steps=self.max_steps)},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.2,
                    },
                )

            if response.status_code != 200:
                logger.error(f"LLM API error: {response.status_code} — {response.text[:200]}")
                return {
                    "action": "done",
                    "params": {"result": f"LLM API error: {response.status_code}"},
                    "reasoning": "api_error_fallback",
                }

            result = response.json()
            raw_content = result["choices"][0]["message"]["content"]
            logger.debug(f"LLM response: {raw_content[:300]}")

            return _parse_llm_decision(raw_content)

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return {
                "action": "done",
                "params": {"result": f"LLM error: {e}"},
                "reasoning": "llm_error_fallback",
            }

    # ─── Action Execution ─────────────────────────────────────────────────

    async def _execute_action(self, action: AgentAction) -> None:
        """Выполнить действие агента."""
        start = time.monotonic()
        action_type = action.action_type
        params = action.params

        logger.info(f"⚡ Executing: {action_type} {params}")

        try:
            if action_type == AgentActionType.NAVIGATE:
                result = await self._action_navigate(**params)
            elif action_type == AgentActionType.CLICK:
                result = await self._action_click(**params)
            elif action_type == AgentActionType.TYPE:
                result = await self._action_type(**params)
            elif action_type == AgentActionType.SCROLL:
                result = await self._action_scroll(**params)
            elif action_type == AgentActionType.EXTRACT:
                result = await self._action_extract(**params)
            elif action_type == AgentActionType.SCREENSHOT:
                result = await self._action_screenshot(**params)
            elif action_type == AgentActionType.WAIT:
                result = await self._action_wait(**params)
            elif action_type == AgentActionType.DONE:
                result = params.get("result", "Done")
            else:
                result = f"Unknown action: {action_type}"
                logger.warning(result)

            action.result = str(result)[:500]

        except Exception as e:
            action.result = f"ERROR: {e}"
            self.memory.add_error(f"Step {action.step}: {action_type} — {e}")
            logger.error(f"Action failed: {action_type} — {e}")

        action.duration_ms = (time.monotonic() - start) * 1000
        self.memory.add_action(action)

        logger.info(f"   Result: {action.result[:200]}")
        logger.info(f"   Duration: {action.duration_ms:.0f}ms")

    async def _action_navigate(self, url: str, **_) -> str:
        """Навигация на URL."""
        await self._page.goto(url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
        await self._behavior.wait_between_actions()
        self.memory.current_url = url
        if url not in self.memory.visited_urls:
            self.memory.visited_urls.append(url)
        title = await self._page.title()
        return f"Navigated to {url} — title: {title}"

    async def _action_click(self, selector: str, **_) -> str:
        """Клик по элементу с человечным поведением."""
        locator = self._page.locator(selector).first
        count = await locator.count()
        if count == 0:
            return f"Element not found: {selector}"

        await self._behavior.scroll_to_element(locator)
        await self._behavior.click(locator=locator)
        await self._behavior.wait_between_actions()
        return f"Clicked: {selector}"

    async def _action_type(self, selector: str, text: str, **_) -> str:
        """Ввод текста с человечным поведением."""
        locator = self._page.locator(selector).first
        count = await locator.count()
        if count == 0:
            return f"Input not found: {selector}"

        await self._behavior.click(locator=locator)
        await locator.fill("")
        await self._behavior.type_like_human(text, locator=locator)
        return f"Typed '{text[:50]}...' into {selector}"

    async def _action_scroll(self, direction: str = "down", amount: int = 1, **_) -> str:
        """Прокрутка страницы."""
        pages = float(amount) * 0.5
        if direction == "up":
            await self._behavior.scroll_up(pages=pages)
        else:
            await self._behavior.scroll_down(pages=pages)
        return f"Scrolled {direction} {amount} pages"

    async def _action_extract(self, schema: dict[str, Any] | None = None, **_) -> str:
        """Извлечение структурированных данных."""
        if schema is None:
            schema = {
                "title": "page title",
                "headings": "list:h1, h2, h3",
                "links": "list:a[href]",
            }

        data = await self._parser.extract_structured(schema)
        self.memory.add_extracted(data)

        # Также через LLM если не mock
        if not self.mock_mode and self.llm_config.api_key:
            try:
                llm_data = await self.llm_parser.extract(
                    self._page,
                    query=self.goal,
                    schema=schema,
                )
                self.memory.add_extracted({"llm_extracted": llm_data})
            except Exception as e:
                logger.warning(f"LLM extraction failed: {e}")

        non_null = sum(1 for v in data.values() if v is not None)
        return f"Extracted {non_null}/{len(schema)} fields: {list(data.keys())}"

    async def _action_screenshot(self, prefix: str = "agent", **_) -> str:
        """Скриншот страницы."""
        path = await self._screenshot_maker.full_page(self._page, prefix=prefix)
        self.memory.add_screenshot(path)
        return f"Screenshot saved: {path}"

    async def _action_wait(self, selector: str, timeout: int = 10000, **_) -> str:
        """Ожидание элемента."""
        try:
            await self._page.wait_for_selector(selector, timeout=timeout)
            return f"Element appeared: {selector}"
        except Exception:
            return f"Timeout waiting for: {selector}"

    # ─── Goal Check ────────────────────────────────────────────────────────

    async def _check_goal_achieved(self) -> bool:
        """Проверить, достигнута ли цель (эвристика)."""
        # Если есть извлечённые данные — цель вероятно достигнута
        if self.memory.extracted_data:
            return True
        # Если было много действий без ошибок — возможно цель достигнута
        if len(self.memory.actions) >= 3 and not self.memory.errors:
            last_action = self.memory.actions[-1]
            if last_action.action_type == AgentActionType.EXTRACT:
                return True
        return False

    # ─── Browser Lifecycle ─────────────────────────────────────────────────

    async def _init_browser(self) -> None:
        """Инициализировать браузер со stealth и fingerprint."""
        logger.info("🌐 Initializing browser...")

        # Настройки браузера
        browser_kwargs: dict[str, Any] = {
            "headless": self.headless,
            "timeout": DEFAULT_TIMEOUT,
        }

        # User-Agent из fingerprint
        if self.fingerprint.user_agent:
            browser_kwargs["user_agent"] = self.fingerprint.user_agent

        self._browser = BrowserManager(**browser_kwargs)
        await self._browser.start()

        self._page = await self._browser.new_page()

        # Применяем fingerprint
        await FingerprintManager.apply(self._page, self.fingerprint)

        # Применяем stealth скрипты
        if self.stealth_config.enabled:
            scripts = self.stealth_config.get_scripts()
            for script in scripts:
                try:
                    await self._page.add_init_script(script)
                except Exception as e:
                    logger.debug(f"Stealth script injection failed: {e}")
            logger.info(f"Stealth: {len(scripts)} scripts injected")

        # Инициализируем компоненты
        self._behavior = HumanBehaviorEngine(
            self._page,
            profile=self.behavior_profile,
        )
        self._parser = PageParser(self._page)
        self._screenshot_maker = ScreenshotMaker(
            output_dir="/tmp/agent_screenshots"
        )

        logger.info(f"✅ Browser initialized: {self.fingerprint.summary}")

    async def _cleanup(self) -> None:
        """Остановить браузер."""
        if self._browser:
            try:
                await self._browser.stop()
                logger.info("Browser stopped")
            except Exception as e:
                logger.warning(f"Browser cleanup error: {e}")

    # ─── Result Building ───────────────────────────────────────────────────

    def _build_result(self, total_time: float) -> dict[str, Any]:
        """Собрать итоговый результат."""
        return {
            "goal": self.goal,
            "status": "completed" if self.memory.extracted_data else "incomplete",
            "total_time_seconds": round(total_time, 2),
            "total_steps": len(self.memory.actions),
            "visited_urls": self.memory.visited_urls,
            "current_url": self.memory.current_url,
            "extracted_data": self.memory.extracted_data,
            "page_titles": self.memory.page_titles,
            "errors": self.memory.errors,
            "screenshots": self.memory.screenshots,
            "action_history": [
                {
                    "step": a.step,
                    "action": a.action_type,
                    "params": a.params,
                    "result": a.result[:200],
                    "duration_ms": round(a.duration_ms, 0),
                }
                for a in self.memory.actions
            ],
            "agent_config": {
                "model": self.model,
                "max_steps": self.max_steps,
                "mock_mode": self.mock_mode,
                "stealth": self.stealth_enabled,
                "headless": self.headless,
                "fingerprint": self.fingerprint.profile_id,
            },
        }

    def _save_result(self, result: dict[str, Any]) -> None:
        """Сохранить результат в файл."""
        path = Path(self.output_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 Result saved: {path}")

    def _print_summary(self, result: dict[str, Any]) -> None:
        """Вывести сводку в консоль."""
        print("\n" + "=" * 60)
        print("  🤖 BROWSER AGENT — RESULT")
        print("=" * 60)
        print(f"  Goal:     {result['goal']}")
        print(f"  Status:   {result['status']}")
        print(f"  Time:     {result['total_time_seconds']}s")
        print(f"  Steps:    {result['total_steps']}")
        print(f"  URLs:     {len(result['visited_urls'])}")
        print(f"  Errors:   {len(result['errors'])}")
        print(f"  Screenshots: {len(result['screenshots'])}")

        if result['extracted_data']:
            print(f"\n  📊 Extracted data ({len(result['extracted_data'])} chunks):")
            for i, chunk in enumerate(result['extracted_data'][:3]):
                for key, value in chunk.items():
                    val_str = str(value)[:80] if value else "null"
                    print(f"    [{i+1}] {key}: {val_str}")

        if result['errors']:
            print("\n  ⚠️ Errors:")
            for err in result['errors'][:5]:
                print(f"    — {err}")

        print("\n  Action history:")
        for a in result['action_history']:
            status = "✓" if not a['result'].startswith("ERROR") else "✗"
            print(f"    [{status}] Step {a['step']}: {a['action']} — {a['result'][:60]}")

        if self.output_file:
            print(f"\n  💾 Full result: {self.output_file}")
        print("=" * 60)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    """Парсинг аргументов командной строки."""
    parser = argparse.ArgumentParser(
        description="LLM-Powered Browser Agent — автономный браузерный агент",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  # Извлечь данные с новостного сайта
  PYTHONPATH=src python3 scripts/llm_browser_agent.py \\
    --goal "Find the latest news about AI and extract titles and dates" \\
    --start-url https://news.ycombinator.com \\
    --max-steps 10 \\
    --output /tmp/agent_result.json

  # Тестирование в mock-режиме (без API-ключа)
  PYTHONPATH=src python3 scripts/llm_browser_agent.py \\
    --goal "Extract page title and headings" \\
    --start-url https://example.com \\
    --mock --verbose

  # Без stealth (быстрее, но меньше маскировка)
  PYTHONPATH=src python3 scripts/llm_browser_agent.py \\
    --goal "Navigate to example.com and extract data" \\
    --start-url https://example.com \\
    --no-stealth
        """,
    )

    parser.add_argument(
        "--goal", "-g",
        required=True,
        help="Цель агента на естественном языке (обязательно)",
    )
    parser.add_argument(
        "--start-url", "-u",
        default="",
        help="Стартовый URL",
    )
    parser.add_argument(
        "--max-steps", "-m",
        type=int,
        default=DEFAULT_MAX_STEPS,
        help=f"Максимум шагов агента (по умолчанию: {DEFAULT_MAX_STEPS})",
    )
    parser.add_argument(
        "--output", "-o",
        default="",
        help="Файл для сохранения результата (JSON)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"LLM модель (по умолчанию: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="API ключ OpenRouter (или переменная окружения OPENROUTER_API_KEY)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Детальное логирование",
    )
    parser.add_argument(
        "--no-stealth",
        action="store_true",
        help="Отключить stealth/антидетект",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Показать окно браузера (не headless)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Mock-режим: симулировать LLM без API-ключа",
    )
    parser.add_argument(
        "--behavior-profile",
        default="casual_reader",
        choices=["casual_reader", "power_user", "researcher", "social_media"],
        help="Профиль человеческого поведения (по умолчанию: casual_reader)",
    )

    return parser.parse_args()


async def main() -> None:
    """Точка входа CLI."""
    args = parse_args()

    # Настройка логирования
    logger.remove()
    log_level = "DEBUG" if args.verbose else "INFO"
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=log_level,
    )

    # API ключ
    api_key = args.api_key or os.environ.get("OPENROUTER_API_KEY", "")

    # Если нет API-ключа и не mock — предупредить
    if not api_key and not args.mock:
        logger.warning("⚠️ No API key found. Use --mock for testing or set OPENROUTER_API_KEY.")
        logger.warning("   Switching to mock mode automatically.")
        args.mock = True

    # Создание и запуск агента
    agent = BrowserAgent(
        goal=args.goal,
        start_url=args.start_url,
        max_steps=args.max_steps,
        model=args.model,
        api_key=api_key,
        output_file=args.output,
        verbose=args.verbose,
        stealth=not args.no_stealth,
        headless=not args.no_headless,
        mock=args.mock,
        behavior_profile=args.behavior_profile,
    )

    result = await agent.run()

    # Exit code: 0 если успешно, 1 если ошибки
    sys.exit(0 if not result.get("errors") else 1)


if __name__ == "__main__":
    asyncio.run(main())
