"""
Telegraph Publisher — публикация статей через Telegraph REST API.

Интегрирует lab-playwright-expert с telegra.ph для автоматической публикации.
Используется из HypeClient и автопостинг-конвейера (SPEC-001).

Telegraph API: https://telegra.ph/api

Пример:
    >>> from lab_playwright_kit.telegraph_publisher import TelegraphPublisher
    >>> pub = TelegraphPublisher(access_token="your_token")
    >>> result = await pub.publish("Заголовок", "<p>HTML контент</p>")
    >>> print(result.url)
    https://telegra.ph/Testovaya-statya-05-18
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import aiohttp
from loguru import logger

TELEGRAPH_API_BASE = "https://api.telegra.ph"


class TelegraphError(Exception):
    """Ошибка Telegraph API."""
    def __init__(self, message: str, error_code: str = ""):
        super().__init__(message)
        self.error_code = error_code


@dataclass
class TelegraphPage:
    """Результат публикации страницы."""
    path: str
    url: str
    title: str
    content: str = ""
    author_name: str = ""
    author_url: str = ""
    views: int = 0
    can_edit: bool = False
    created_at: str = ""


@dataclass
class PublishResult:
    """Результат публикации."""
    success: bool
    page: TelegraphPage | None = None
    error: str = ""
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "url": self.page.url if self.page else "",
            "path": self.page.path if self.page else "",
            "title": self.page.title if self.page else "",
            "error": self.error,
            "elapsed": round(self.elapsed_seconds, 2),
        }


@dataclass
class AccountInfo:
    """Информация об аккаунте Telegraph."""
    short_name: str = ""
    author_name: str = ""
    author_url: str = ""
    auth_url: str = ""
    page_count: int = 0


class TelegraphPublisher:
    """Клиент для публикации статей через Telegraph REST API.

    Поддерживает:
    - Создание и редактирование страниц
    - Получение списка страниц
    - Получение статистики просмотров
    - Автоматический retry при ошибках

    Использование:
        # С существующим токеном
        pub = TelegraphPublisher(access_token="your_token")
        result = await pub.publish("Title", "<p>Content</p>")

        # Создание нового аккаунта
        pub = TelegraphPublisher.create_account(short_name="MyLab", author="DoctorM&Ai")
        result = await pub.publish("Title", "<p>Content</p>")
    """

    def __init__(
        self,
        access_token: str = "",
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.access_token = access_token
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def connect(self):
        """Открыть HTTP-сессию."""
        if not self._session:
            self._session = aiohttp.ClientSession(timeout=self.timeout)

    async def close(self):
        """Закрыть HTTP-сессию."""
        if self._session:
            await self._session.close()
            self._session = None

    async def _request(self, method: str, **params: Any) -> dict:
        """Запрос к Telegraph API с retry."""
        if not self._session:
            raise RuntimeError("Not connected. Use 'async with' or call connect()")

        url = f"{TELEGRAPH_API_BASE}/{method}"
        if self.access_token:
            params["access_token"] = self.access_token

        for attempt in range(1, self.max_retries + 1):
            try:
                async with self._session.post(url, data=params) as resp:
                    data = await resp.json(content_type=None)
                    if not data.get("ok"):
                        error = data.get("error", "Unknown error")
                        logger.warning(f"Telegraph API error: {error}")
                        if attempt < self.max_retries:
                            await asyncio.sleep(self.retry_delay * attempt)
                            continue
                        raise TelegraphError(str(error))
                    return data["result"]
            except aiohttp.ClientError as e:
                logger.warning(f"Telegraph request failed (attempt {attempt}): {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay * attempt)
                else:
                    raise TelegraphError(f"Request failed: {e}")

        raise TelegraphError("Max retries exceeded")

    async def get_account_info(self) -> AccountInfo:
        """Получить информацию об аккаунте."""
        result = await self._request("getAccountInfo")
        return AccountInfo(
            short_name=result.get("short_name", ""),
            author_name=result.get("author_name", ""),
            author_url=result.get("author_url", ""),
            auth_url=result.get("auth_url", ""),
            page_count=result.get("page_count", 0),
        )

    async def create_page(
        self,
        title: str,
        content: list[dict] | str,
        author_name: str = "",
        author_url: str = "",
        return_content: bool = False,
    ) -> TelegraphPage:
        """Создать новую страницу.

        Args:
            title: Заголовок страницы (1-256 символов)
            content: Контент — либо JSON-список Node объектов, либо HTML строка
            author_name: Имя автора
            author_url: URL автора
            return_content: Вернуть контент в ответе

        Returns:
            TelegraphPage с данными созданной страницы
        """
        params: dict[str, Any] = {
            "title": title[:256],
            "return_content": str(return_content).lower(),
        }

        if author_name:
            params["author_name"] = author_name
        if author_url:
            params["author_url"] = author_url

        # Контент: если строка — конвертируем в JSON nodes
        if isinstance(content, str):
            params["content"] = self._html_to_nodes_json(content)
        else:
            params["content"] = json.dumps(content)

        result = await self._request("createPage", **params)
        return TelegraphPage(
            path=result.get("path", ""),
            url=result.get("url", ""),
            title=result.get("title", title),
            content="",
            author_name=result.get("author_name", author_name),
            author_url=result.get("author_url", author_url),
            views=result.get("views", 0),
            can_edit=result.get("can_edit", False),
        )

    async def edit_page(
        self,
        path: str,
        title: str,
        content: list[dict] | str,
        author_name: str = "",
        author_url: str = "",
        return_content: bool = False,
    ) -> TelegraphPage:
        """Редактировать существующую страницу.

        Args:
            path: Путь страницы (из create_page result)
            title: Новый заголовок
            content: Новый контент
            author_name: Имя автора
            author_url: URL автора
            return_content: Вернуть контент в ответе

        Returns:
            TelegraphPage с обновлёнными данными
        """
        params: dict[str, Any] = {
            "path": path,
            "title": title[:256],
            "return_content": str(return_content).lower(),
        }

        if author_name:
            params["author_name"] = author_name
        if author_url:
            params["author_url"] = author_url

        if isinstance(content, str):
            params["content"] = self._html_to_nodes_json(content)
        else:
            params["content"] = json.dumps(content)

        result = await self._request("editPage", **params)
        return TelegraphPage(
            path=result.get("path", path),
            url=result.get("url", ""),
            title=result.get("title", title),
            content="",
            author_name=result.get("author_name", author_name),
            author_url=result.get("author_url", author_url),
            views=result.get("views", 0),
            can_edit=result.get("can_edit", False),
        )

    async def get_page(self, path: str, return_content: bool = True) -> TelegraphPage:
        """Получить страницу по пути."""
        result = await self._request("getPage", path=path, return_content=str(return_content).lower())
        return TelegraphPage(
            path=result.get("path", path),
            url=result.get("url", ""),
            title=result.get("title", ""),
            content=json.dumps(result.get("content", [])) if return_content else "",
            author_name=result.get("author_name", ""),
            author_url=result.get("author_url", ""),
            views=result.get("views", 0),
            can_edit=result.get("can_edit", False),
        )

    async def get_page_list(self, offset: int = 0, limit: int = 50) -> list[TelegraphPage]:
        """Получить список страниц аккаунта."""
        result = await self._request("getPageList", offset=offset, limit=min(limit, 200))
        pages = result.get("pages", [])
        return [
            TelegraphPage(
                path=p.get("path", ""),
                url=p.get("url", ""),
                title=p.get("title", ""),
                content="",
                author_name=p.get("author_name", ""),
                author_url=p.get("author_url", ""),
                views=p.get("views", 0),
                can_edit=p.get("can_edit", False),
            )
            for p in pages
        ]

    async def get_views(self, path: str, year: int = 0, month: int = 0, day: int = 0, hour: int = 0) -> int:
        """Получить количество просмотров страницы."""
        params: dict[str, Any] = {"path": path}
        if year:
            params["year"] = year
        if month:
            params["month"] = month
        if day:
            params["day"] = day
        if hour:
            params["hour"] = hour

        result = await self._request("getViews", **params)
        return result.get("views", 0)

    async def publish(
        self,
        title: str,
        content: str,
        author_name: str = "",
        author_url: str = "",
    ) -> PublishResult:
        """Высокоуровневая публикация статьи.

        Конвертирует HTML в Telegraph Node format и публикует.

        Args:
            title: Заголовок статьи
            content: HTML или текст контента
            author_name: Имя автора
            author_url: URL автора

        Returns:
            PublishResult с результатом публикации
        """
        start = time.time()

        try:
            page = await self.create_page(
                title=title,
                content=content,
                author_name=author_name,
                author_url=author_url,
            )

            elapsed = time.time() - start
            logger.info(f"✅ Published to Telegraph: {page.url} ({elapsed:.1f}s)")

            return PublishResult(
                success=True,
                page=page,
                elapsed_seconds=elapsed,
            )

        except TelegraphError as e:
            elapsed = time.time() - start
            logger.error(f"❌ Telegraph publish failed: {e}")
            return PublishResult(
                success=False,
                error=str(e),
                elapsed_seconds=elapsed,
            )
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"❌ Telegraph publish error: {e}")
            return PublishResult(
                success=False,
                error=str(e),
                elapsed_seconds=elapsed,
            )

    @staticmethod
    def _html_to_nodes_json(html: str) -> str:
        """Конвертировать HTML строку в Telegraph Node JSON format.

        Простая конвертация: оборачивает текст в параграфы,
        поддерживает базовые теги: p, h3, h4, strong, em, a, ul, ol, li, img, blockquote.
        """
        import re

        nodes: list[dict] = []

        # Разбиваем по блочным элементам
        # Сначала извлекаем заголовки
        for match in re.finditer(r'<h([34])>(.*?)</h\1>', html, re.DOTALL):
            level = match.group(1)
            text = re.sub(r'<[^>]+>', '', match.group(2)).strip()
            if text:
                tag = "h3" if level == "3" else "h4"
                nodes.append({"tag": tag, "children": [text]})

        # Изображения
        for match in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html):
            src = match.group(1)
            nodes.append({"tag": "img", "attrs": {"src": src}})

        # Убираем все теги для извлечения текста
        text = re.sub(r'<[^>]+>', '', html).strip()
        if text:
            # Разбиваем на параграфы по двойному переводу строки
            paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
            for p in paragraphs:
                nodes.append({"tag": "p", "children": [p]})

        if not nodes:
            # Если ничего не распарсилось — оборачиваем весь текст в p
            clean = re.sub(r'<[^>]+>', '', html).strip()
            if clean:
                nodes.append({"tag": "p", "children": [clean]})

        return json.dumps(nodes, ensure_ascii=False)

    @staticmethod
    def html_to_nodes(html: str) -> list[dict]:
        """Конвертировать HTML в список Telegraph Node объектов.

        Поддерживает: p, h3, h4, strong, em, a, ul, ol, li, img, blockquote, br.
        """
        import re

        nodes: list[dict] = []

        # Заголовки h3
        for match in re.finditer(r'<h3>(.*?)</h3>', html, re.DOTALL):
            text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
            if text:
                nodes.append({"tag": "h3", "children": [text]})

        # Заголовки h4
        for match in re.finditer(r'<h4>(.*?)</h4>', html, re.DOTALL):
            text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
            if text:
                nodes.append({"tag": "h4", "children": [text]})

        # Изображения
        for match in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html):
            src = match.group(1)
            nodes.append({"tag": "img", "attrs": {"src": src}})

        # Цитаты
        for match in re.finditer(r'<blockquote>(.*?)</blockquote>', html, re.DOTALL):
            text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
            if text:
                nodes.append({"tag": "blockquote", "children": [text]})

        # Списки
        for match in re.finditer(r'<[ou]l>(.*?)</[ou]l>', html, re.DOTALL):
            tag = "ul" if match.group(0).startswith("<ul") else "ol"
            items = re.findall(r'<li>(.*?)</li>', match.group(1), re.DOTALL)
            children = []
            for item in items:
                text = re.sub(r'<[^>]+>', '', item).strip()
                if text:
                    children.append({"tag": "li", "children": [text]})
            if children:
                nodes.append({"tag": tag, "children": children})

        # Параграфы
        for match in re.finditer(r'<p>(.*?)</p>', html, re.DOTALL):
            text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
            if text:
                nodes.append({"tag": "p", "children": [text]})

        # Если ничего не распарсилось — весь текст в один p
        if not nodes:
            clean = re.sub(r'<[^>]+>', '', html).strip()
            if clean:
                nodes.append({"tag": "p", "children": [clean]})

        return nodes


# ─── Convenience Functions ───────────────────────────────────────────────────

async def quick_publish(
    title: str,
    content: str,
    access_token: str,
    author_name: str = "",
    author_url: str = "",
) -> PublishResult:
    """Быстрая публикация без явного создания клиента.

    Пример:
        result = await quick_publish("Title", "<p>Content</p>", "token")
        print(result.url)
    """
    async with TelegraphPublisher(access_token=access_token) as pub:
        return await pub.publish(title, content, author_name, author_url)


async def create_telegraph_account(
    short_name: str,
    author_name: str = "",
    author_url: str = "",
) -> tuple[str, TelegraphPublisher]:
    """Создать новый аккаунт Telegraph.

    Returns:
        (access_token, publisher) — токен и готовый клиент
    """
    pub = TelegraphPublisher()
    await pub.connect()

    result = await pub._request(
        "createAccount",
        short_name=short_name,
        author_name=author_name,
        author_url=author_url,
    )

    token = result.get("access_token", "")
    pub.access_token = token

    logger.info(f"✅ Created Telegraph account: {short_name} (token: {token[:8]}...)")
    return token, pub
