"""
LLM-парсинг: браузер + языковая модель = интеллектуальный скрейпинг.

Модули:
- LLMParser: базовый извлечитель данных через LLM
- ParseCache: TTL-кэш результатов парсинга
- SelfHealingParser: парсер с автоисправлением селекторов
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
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


# ─── ParseCache ──────────────────────────────────────────────────────────────

class ParseCache:
    """Кэш результатов парсинга (TTL-based).

    Хранит результаты с временной меткой. При чтении проверяет TTL.
    Устаревшие записи автоматически удаляются при get().

    Пример:
        cache = ParseCache(ttl=3600)
        cache.set("key", {"data": "value"})
        result = cache.get("key")  # {"data": "value"}
        # Через TTL секунд — cache.get("key") вернёт None
    """

    def __init__(self, ttl: int = 3600):
        self._cache: dict[str, tuple[float, dict]] = {}
        self.ttl = ttl
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> dict | None:
        """Получить значение из кэша.

        Returns:
            Закэшированный dict или None если нет / истёк TTL.
        """
        if key not in self._cache:
            self._misses += 1
            return None

        ts, value = self._cache[key]
        if time.monotonic() - ts > self.ttl:
            # TTL истёк — удаляем
            del self._cache[key]
            self._misses += 1
            return None

        self._hits += 1
        return value

    def set(self, key: str, value: dict) -> None:
        """Сохранить значение в кэш."""
        self._cache[key] = (time.monotonic(), value)

    def clear(self) -> int:
        """Очистить кэш. Возвращает количество удалённых записей."""
        count = len(self._cache)
        self._cache.clear()
        return count

    def invalidate(self, key: str) -> bool:
        """Инвалидировать конкретную запись.

        Returns:
            True если запись была удалена.
        """
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    @property
    def size(self) -> int:
        """Текущий размер кэша."""
        return len(self._cache)

    @property
    def hit_rate(self) -> float:
        """Hit rate = hits / (hits + misses). 0.0 если нет данных."""
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total

    def stats(self) -> dict[str, Any]:
        """Статистика кэша."""
        return {
            "size": self.size,
            "ttl": self.ttl,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
        }

    @staticmethod
    def make_key(*parts: str) -> str:
        """Создать ключ кэша из частей."""
        raw = "|".join(parts)
        return hashlib.md5(raw.encode()).hexdigest()


# ─── SelfHealingParser ────────────────────────────────────────────────────────

class SelfHealingParser:
    """Парсер с автоисправлением селекторов при изменениях сайта.

    Оборачивает LLMParser. При неудачном извлечении данных:
    1. Проверяет кэш (если есть)
    2. Пытается найти альтернативный селектор через LLM
    3. Кэширует новый селектор
    4. Повторяет извлечение

    Использование:
        llm = LLMParser(LLMConfig(api_key="..."))
        parser = SelfHealingParser(llm)
        result = await parser.extract_with_retry(page, "все цены")
    """

    def __init__(
        self,
        llm_parser: LLMParser,
        cache: ParseCache | None = None,
        max_retries: int = 3,
    ):
        """
        Args:
            llm_parser: Базовый LLMParser
            cache: Опциональный кэш (создаётся с TTL=3600 если None)
            max_retries: Максимальное число попыток
        """
        self.llm = llm_parser
        self.cache = cache or ParseCache(ttl=3600)
        self.max_retries = max_retries
        self._selector_cache: dict[str, str] = {}  # query → selector

    async def extract_with_retry(
        self, page: Page, query: str, schema: dict[str, str] | None = None, max_retries: int | None = None,
    ) -> dict:
        """Извлечь данные с автоисправлением при неудаче.

        1. Проверяет кэш
        2. Вызывает LLMParser.extract
        3. Если результат пустой/ошибка — пытается исправить
        4. Повторяет до max_retries

        Args:
            page: Страница Playwright
            query: Что извлечь (естественный язык)
            schema: Ожидаемый формат (опционально)
            max_retries: Переопределение max_retries

        Returns:
            Результат извлечения (dict)
        """
        retries = max_retries or self.max_retries
        cache_key = ParseCache.make_key(page.url, query, json.dumps(schema or {}, ensure_ascii=False))

        # 1. Проверить кэш
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.info(f"[SELF-HEALING CACHE HIT] {page.url} query={query!r}")
            return cached

        last_result: dict = {}
        failed_selector = ""

        for attempt in range(1, retries + 1):
            logger.info(
                f"[SELF-HEALING] Attempt {attempt}/{retries} for "
                f"{page.url} query={query!r}"
            )

            try:
                result = await self.llm.extract(page, query, schema)

                # Проверяем результат
                if self._is_valid_result(result):
                    # Кэшируем и возвращаем
                    self.cache.set(cache_key, result)
                    return result

                # Неполный результат — пытаемся исправить
                last_result = result
                logger.warning(
                    f"[SELF-HEALING] Attempt {attempt}: incomplete result "
                    f"{list(result.keys())}"
                )

                # Попытка исправить селектор
                failed_selector = self._selector_cache.get(query, "")
                new_selector = await self._fix_selector(page, failed_selector, query)
                if new_selector:
                    self._selector_cache[query] = new_selector
                    logger.info(f"[SELF-HEALING] New selector: {new_selector}")

            except Exception as e:
                logger.error(f"[SELF-HEALING] Attempt {attempt} error: {e}")
                last_result = {"error": str(e), "attempt": attempt}

        # Все попытки исчерпаны — возвращаем лучший результат
        logger.warning(
            f"[SELF-HEALING] All {retries} attempts exhausted for "
            f"{page.url} query={query!r}"
        )
        self.cache.set(cache_key, last_result)
        return last_result

    async def _fix_selector(
        self, page: Page, failed_selector: str, context: str
    ) -> str | None:
        """Найти новый селектор через LLM, если старый сломался.
        
        Получает снимок DOM, отправляет LLM, и просит найти новый селектор
        для данных, которые нужно извлечь.

        Args:
            page: Страница Playwright
            failed_selector: Селектор, который не сработал
            context: Контекст — что мы пытаемся извлечь

        Returns:
            Новый селектор (CSS/XPath) или None
        """
        try:
            # Получаем селекторы и снимок
            selectors = await self.llm.list_selectors(page)
            snapshot = await self.llm.snapshot(page, max_length=3000)

            # Строим промпт для LLM
            fix_prompt = f"""Селектор "{failed_selector}" сломался (данных не найдено).
Текущий запрос: {context}

Селекторы на странице:
{json.dumps(selectors, ensure_ascii=False, indent=2)}

HTML-снимок:
{snapshot}

Найди новый CSS-селектор или XPath для искомых данных.
Ответь ТОЛЬКО в JSON: {{"selector": "...", "reason": "..."}}
Если не можешь найти — {{"selector": null, "reason": "..."}}"""

            # Вызов LLM
            async with httpx.AsyncClient(timeout=self.llm.config.timeout) as client:
                response = await client.post(
                    self.llm.config.api_url,
                    headers={
                        "Authorization": f"Bearer {self.llm.config.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.llm.config.model,
                        "messages": [
                            {"role": "system", "content": "Ты эксперт по CSS-селекторам. Отвечай только JSON."},
                            {"role": "user", "content": fix_prompt},
                        ],
                        "temperature": 0.1,
                    },
                )

            if response.status_code != 200:
                logger.error(f"[SELF-HEALING] LLM error: {response.status_code}")
                return None

            result = response.json()
            raw_content = result["choices"][0]["message"]["content"]

            # Парсим JSON из ответа
            json_start = raw_content.find("{")
            json_end = raw_content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(raw_content[json_start:json_end])
            else:
                logger.warning("[SELF-HEALING] No JSON in LLM response")
                return None

            selector = data.get("selector")
            reason = data.get("reason", "")

            if selector:
                logger.info(f"[SELF-HEALING] Found new selector: {selector} (reason: {reason})")
                return selector
            else:
                logger.warning(f"[SELF-HEALING] LLM could not find selector: {reason}")
                return None

        except Exception as e:
            logger.error(f"[SELF-HEALING] _fix_selector error: {e}")
            return None

    @staticmethod
    def _is_valid_result(result: dict) -> bool:
        """Проверить, валиден ли результат парсинга."""
        if not result:
            return False
        if result.get("error"):
            return False
        if result.get("found") is False:
            return False
        if len(result) == 1 and result.get("raw"):
            # Только raw текст — слабый результат
            return False
        return True

    def get_selector_cache(self) -> dict[str, str]:
        """Получить текущий кэш селекторов."""
        return dict(self._selector_cache)

    def clear_selector_cache(self) -> int:
        """Очистить кэш селекторов. Возвращает количество удалённых."""
        count = len(self._selector_cache)
        self._selector_cache.clear()
        return count

    async def list_selectors(self, page: Page) -> list[dict[str, str]]:
        """Извлечь все значимые селекторы со страницы.

        Используется SelfHealingParser для поиска новых селекторов.

        Returns:
            Список {"selector": ..., "tag": ..., "text": ..., "class": ..., "id": ...}
        """
        return await page.evaluate("""() => {
            const results = [];
            const seen = new Set();
            document.querySelectorAll('a, button, input, h1, h2, h3, [data-testid], [class]').forEach(el => {
                const tag = el.tagName.toLowerCase();
                let sel = tag;
                if (el.id) sel += '#' + el.id;
                if (el.className && typeof el.className === 'string') {
                    const cls = el.className.trim().split('\\s+').slice(0, 2).join('.');
                    if (cls) sel += '.' + cls;
                }
                if (el.getAttribute('data-testid')) {
                    sel += `[data-testid="${el.getAttribute('data-testid')}"]`;
                }
                if (!seen.has(sel) && sel.length > 3) {
                    seen.add(sel);
                    const text = (el.innerText || el.value || el.placeholder || '').trim().substring(0, 80);
                    results.push({
                        selector: sel,
                        tag: tag,
                        text: text,
                        class: typeof el.className === 'string' ? el.className.trim().substring(0, 60) : '',
                        id: el.id || '',
                    });
                }
            });
            return results.slice(0, 50);
        }""")

    async def snapshot(self, page: Page, max_length: int = 4000) -> str:
        """Получить снимок DOM-структуры для LLM-анализа.

        Возвращает упрощённую HTML-структуру (теги, классы, id, text).
        """
        raw_html = await page.evaluate("""() => {
            const clone = document.body.cloneNode(true);
            // Удаляем скрипты, стили, svg
            clone.querySelectorAll('script, style, svg, noscript').forEach(n => n.remove());
            // Упрощаем: оставляем только значимые теги
            const allowed = new Set(['a','button','input','select','textarea',
                'h1','h2','h3','h4','h5','h6','p','span','div','li','th','td','form','img','table','ul','ol']);
            const all = clone.querySelectorAll('*');
            all.forEach(el => {
                if (!allowed.has(el.tagName.toLowerCase())) {
                    el.replaceWith(...el.childNodes);
                }
            });
            return clone.innerHTML.substring(0, 15000);
        }""")
        return raw_html[:max_length]

