"""
LLM-парсинг: браузер + языковая модель = интеллектуальный скрейпинг.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger
from playwright.async_api import Page


# Системный промпт для извлечения структурированных данных
EXTRACTION_PROMPT_TEMPLATE = """Ты — эксперт по извлечению данных из веб-страниц.
Проанализируй содержимое страницы и извлеки запрошенные данные.

URL: {url}
ЗАПРОС ПОЛЬЗОВАТЕЛЯ: {query}

СОДЕРЖИМОЕ СТРАНИЦЫ:
{content}

Ответь ТОЛЬКО в формате JSON. Никакого дополнительного текста.
Если данные не найдены, верни {"found": false, "reason": "причина"}.

Формат ответа:
{schema}
"""


@dataclass
class LLMConfig:
    """Конфигурация LLM для парсинга."""

    api_url: str = "https://openrouter.ai/api/v1/chat/completions"
    api_key: str = ""
    model: str = "google/gemini-2.5-flash"
    max_content_length: int = 8000
    temperature: float = 0.1
    timeout: int = 30


class LLMParser:
    """Интеллектуальный парсер: Playwright + LLM."""

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()

    async def extract(
        self,
        page: Page,
        query: str,
        schema: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Извлечь данные со страницы через LLM.

        Args:
            page: Страница Playwright
            query: Что извлечь (естественный язык)
            schema: Описание ожидаемого формата {поле: описание}

        Returns:
            Извлечённые данные
        """
        # Получить текст страницы
        content = await page.evaluate("() => document.body.innerText")
        content = content[: self.config.max_content_length]

        # Форматировать схему
        if schema:
            schema_str = json.dumps(schema, ensure_ascii=False, indent=2)
        else:
            schema_str = json.dumps({"data": "extracted data"}, ensure_ascii=False)

        prompt = EXTRACTION_PROMPT_TEMPLATE.replace("{url}", page.url).replace("{query}", query).replace("{content}", content[:self.config.max_content_length]).replace("{schema}", schema_str)

        # Вызов LLM
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            response = await client.post(
                self.config.api_url,
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.config.model,
                    "messages": [
                        {"role": "system", "content": "Отвечай только JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": self.config.temperature,
                },
            )

        if response.status_code != 200:
            logger.error(f"LLM API error: {response.status_code} — {response.text}")
            return {"error": response.text}

        result = response.json()
        raw_content = result["choices"][0]["message"]["content"]

        # Парсинг JSON из ответа
        try:
            # Попытаться найти JSON в ответе
            json_start = raw_content.find("{")
            json_end = raw_content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(raw_content[json_start:json_end])
            else:
                data = {"raw": raw_content}
        except json.JSONDecodeError:
            data = {"raw": raw_content}

        logger.info(f"LLM extracted from {page.url}: {list(data.keys())}")
        return data

    async def classify(self, page: Page, categories: list[str]) -> str:
        """Классифицировать страницу.

        Args:
            page: Страница Playwright
            categories: Список возможных категорий

        Returns:
            Выбранная категория
        """
        await page.title()
        content = await page.evaluate("() => document.body.innerText")
        content[:2000]

        result = await self.extract(
            page,
            query=f"Классифицируй эту страницу. Варианты: {', '.join(categories)}. Ответь только одним словом — названием категории.",
        )

        return result.get("data", result.get("category", "unknown"))

    async def summarize(self, page: Page, max_length: int = 300) -> str:
        """Кратко суммировать содержимое страницы."""
        content = await page.evaluate("() => document.body.innerText")
        content = content[: self.config.max_content_length]

        result = await self.extract(
            page,
            query=f"Суммируй содержимое этой страницы в {max_length} символов.",
        )

        return result.get("data", result.get("summary", ""))
