"""
Парсинг страниц: извлечение данных из DOM.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from loguru import logger
from playwright.async_api import Locator, Page


@dataclass
class ParsedContent:
    """Результат парсинга страницы."""

    url: str
    title: str
    text: str
    links: list[dict[str, str]]
    images: list[str]
    meta: dict[str, str]
    structured: dict[str, Any]

    @property
    def domain(self) -> str:
        from urllib.parse import urlparse
        return urlparse(self.url).netloc

    def summary(self, max_length: int = 500) -> str:
        """Краткое содержимое."""
        return self.text[:max_length] + "..." if len(self.text) > max_length else self.text


class PageParser:
    """Парсер веб-страниц через Playwright."""

    def __init__(self, page: Page):
        self.page = page

    async def parse(self) -> ParsedContent:
        """Полный парсинг текущей страницы."""
        url = self.page.url
        title = await self.page.title()

        # Извлечь текст
        text = await self.page.evaluate("() => document.body.innerText")

        # Ссылки
        links = await self.page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]')).map(a => ({
                text: a.innerText.trim(),
                href: a.href
            })).filter(l => l.href && l.text)
        """)

        # Изображения
        images = await self.page.evaluate("""
            () => Array.from(document.querySelectorAll('img[src]'))
                .map(img => img.src)
                .filter(src => src && !src.startsWith('data:'))
        """)

        # Мета-теги
        meta = await self.page.evaluate("""
            () => {
                const result = {};
                document.querySelectorAll('meta[name], meta[property]').forEach(m => {
                    const key = m.getAttribute('name') || m.getAttribute('property');
                    const val = m.getAttribute('content');
                    if (key && val) result[key] = val;
                });
                return result;
            }
        """)

        # Структурированные данные
        structured = await self._parse_structured()

        content = ParsedContent(
            url=url,
            title=title,
            text=text,
            links=links,
            images=images,
            meta=meta,
            structured=structured,
        )

        logger.info(f"Parsed: {url} — {len(text)} chars, {len(links)} links")
        return content

    async def _parse_structured(self) -> dict[str, Any]:
        """Извлечь структурированные данные (JSON-LD, OpenGraph)."""
        data = {}

        # JSON-LD
        json_ld = await self.page.evaluate("""
            () => {
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                return Array.from(scripts).map(s => {
                    try { return JSON.parse(s.textContent); } catch { return null; }
                }).filter(Boolean);
            }
        """)
        if json_ld:
            data["json_ld"] = json_ld

        # OpenGraph уже в meta
        og_data = {}
        for key, value in (await self.page.evaluate("""
            () => {
                const result = {};
                document.querySelectorAll('meta[property^="og:"]').forEach(m => {
                    result[m.getAttribute('property')] = m.getAttribute('content');
                });
                return result;
            }
        """)).items():
            og_data[key] = value
        if og_data:
            data["opengraph"] = og_data

        return data

    async def extract_by_selector(self, selector: str) -> list[str]:
        """Извлечь текст по CSS-селектору."""
        locator: Locator = self.page.locator(selector)
        count = await locator.count()
        results = []
        for i in range(count):
            text = await locator.nth(i).inner_text()
            results.append(text.strip())
        return results

    async def extract_table(
        self,
        selector: str = "table",
        as_dict: bool = False,
    ) -> list[list[str]] | list[dict[str, str]]:
        """Извлечь таблицу из HTML.

        Два режима:
        - as_dict=False (по умолчанию): list[list[str]] — список строк
        - as_dict=True: list[dict[str, str]] — список словарей,
          где ключи из заголовков таблицы

        Args:
            selector: CSS-селектор таблицы
            as_dict: Вернуть как список словарей

        Returns:
            Данные таблицы в выбранном формате
        """
        if not as_dict:
            return await self.page.evaluate(f"""
                () => {{
                    const table = document.querySelector('{selector}');
                    if (!table) return [];
                    return Array.from(table.querySelectorAll('tr')).map(tr =>
                        Array.from(tr.querySelectorAll('td, th')).map(
                            cell => cell.innerText.trim()
                        )
                    );
                }}
            """)

        # list[dict] — заголовки как ключи
        return await self.page.evaluate(f"""
            () => {{
                const table = document.querySelector('{selector}');
                if (!table) return [];

                const rows = Array.from(table.querySelectorAll('tr'));
                if (rows.length === 0) return [];

                // Заголовки из первой строки
                const headers = Array.from(
                    rows[0].querySelectorAll('th, td')
                ).map(cell => cell.innerText.trim());

                // Данные из остальных строк
                const data = [];
                for (let i = 1; i < rows.length; i++) {{
                    const cells = Array.from(
                        rows[i].querySelectorAll('td, th')
                    ).map(cell => cell.innerText.trim());

                    const row: Record<string, string> = {{}};
                    headers.forEach((header, idx) => {{
                        row[header] = cells[idx] || '';
                    }});
                    data.push(row);
                }}
                return data;
            }}
        """)

    async def extract_emails(self) -> list[str]:
        """Найти email-адреса на странице."""
        text = await self.page.evaluate("() => document.body.innerText")
        pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        return list(set(re.findall(pattern, text)))

    async def extract_phones(self) -> list[str]:
        """Найти телефоны на странице."""
        text = await self.page.evaluate("() => document.body.innerText")
        pattern = r'[\+]?[78][\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}'
        return list(set(re.findall(pattern, text)))

    async def extract_structured(
        self,
        schema: dict[str, str],
    ) -> dict[str, list[str] | str | None]:
        """Извлечь структурированные данные по JSON-схеме.

        Схема — словарь {ключ: CSS-селектор}. Для каждого селектора
        извлекается текст первого совпавшего элемента (или список текстов
        если селектор содержит префикс "list:").

        Args:
            schema: Словарь вида:
                {
                    "title": "h1",
                    "description": "meta[name='description']@content",
                    "tags": "list:.tag",
                    "author": ".author-name",
                }

                Поддерживаемые модификаторы селектора:
                - "list:selector" — извлечь все совпадения (list[str])
                - "selector@attr" — извлечь атрибут (например, @href, @src)

        Returns:
            Словарь {ключ: извлечённое значение}

        Example:
            >>> schema = {
            ...     "title": "h1",
            ...     "links": "list:a[href]",
            ...     "image": "img.main@src",
            ... }
            >>> data = await parser.extract_structured(schema)
            >>> # {"title": "Example", "links": ["...", ...], "image": "..."}
        """
        result: dict[str, list[str] | str | None] = {}

        for key, raw_selector in schema.items():
            try:
                # Парсинг модификаторов
                is_list = raw_selector.startswith("list:")
                if is_list:
                    raw_selector = raw_selector[5:]

                # Парсинг атрибута (@attr)
                attr: str | None = None
                if "@" in raw_selector and not raw_selector.startswith("//"):
                    parts = raw_selector.rsplit("@", 1)
                    raw_selector = parts[0]
                    attr = parts[1]

                if is_list:
                    # Извлечь все совпадения
                    locator = self.page.locator(raw_selector)
                    count = await locator.count()
                    items: list[str] = []
                    for i in range(count):
                        if attr:
                            val = await locator.nth(i).get_attribute(attr)
                        else:
                            val = await locator.nth(i).inner_text()
                        if val:
                            items.append(val.strip())
                    result[key] = items
                else:
                    # Первое совпадение
                    locator = self.page.locator(raw_selector)
                    count = await locator.count()
                    if count == 0:
                        result[key] = None
                    elif attr:
                        result[key] = await locator.first.get_attribute(attr)
                    else:
                        text = await locator.first.inner_text()
                        result[key] = text.strip()

            except Exception as e:
                logger.warning(
                    f"extract_structured: failed for key '{key}' "
                    f"selector '{raw_selector}': {e}"
                )
                result[key] = None

        logger.info(
            f"extract_structured: extracted {len(result)} fields "
            f"({sum(1 for v in result.values() if v is not None)} non-null)"
        )
        return result

    async def wait_for_content(
        self,
        selector: str,
        timeout: int = 10000,
        state: str = "visible",
    ) -> bool:
        """Подождать появления элемента."""
        try:
            await self.page.wait_for_selector(selector, timeout=timeout, state=state)
            return True
        except Exception:
            logger.warning(f"Timeout waiting for: {selector}")
            return False

    async def scroll_to_bottom(self, delay: float = 0.5) -> int:
        """Прокрутить до конца страницы (для infinite scroll). Возвращает количество скроллов."""
        return await self.page.evaluate(f"""
            async () => {{
                let prevHeight = 0;
                let scrolls = 0;
                while (true) {{
                    window.scrollTo(0, document.body.scrollHeight);
                    await new Promise(r => setTimeout(r, {int(delay * 1000)}));
                    const newHeight = document.body.scrollHeight;
                    if (newHeight === prevHeight) break;
                    prevHeight = newHeight;
                    scrolls++;
                    if (scrolls > 100) break; // safety
                }}
                return scrolls;
            }}
        """)
