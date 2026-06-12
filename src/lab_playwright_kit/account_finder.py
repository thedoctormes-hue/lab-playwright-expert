"""
AccountFinder — рекурсивный поиск аккаунтов по найденным профилям.

Вдохновлён Maigret:
  - Рекурсивный поиск: извлекает ссылки на другие аккаунты из профилей
  - Пермутация ников: генерирует вариации для расширенного поиска
  - Проверка наличия: HTTP запросы + presence/absence строки
  - Ранжирование: по популярности платформы

Использование:
    >>> finder = AccountFinder(registry)
    >>> results = await finder.search("octocat", platforms=["github", "twitter"])
    >>> for r in results:
    ...     print(f"{r.platform}: {r.url} ({r.status})")
"""
from __future__ import annotations

import asyncio
import itertools
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx
from loguru import logger

from .platform_registry import CheckType, PlatformProfile, PlatformRegistry


@dataclass
class FoundAccount:
    """Найденный аккаунт.

    Attributes:
        platform: Имя платформы
        username: Имя пользователя
        url: URL профиля
        status: Статус (claimed, available, unknown)
        confidence: Уверенность (0.0-1.0)
        source: Откуда найден (search, recursive, permute)
        tags: Теги платформы
        metadata: Дополнительные данные
    """
    platform: str = ""
    username: str = ""
    url: str = ""
    status: str = "unknown"
    confidence: float = 0.0
    source: str = "search"
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "username": self.username,
            "url": self.url,
            "status": self.status,
            "confidence": self.confidence,
            "source": self.source,
            "tags": self.tags,
        }


@dataclass
class SearchReport:
    """Отчёт о поиске аккаунтов.

    Attributes:
        query: Исзапрос (username)
        found: Список найденных аккаунтов
        checked: Количество проверенных платформ
        elapsed_seconds: Время выполнения
    """
    query: str = ""
    found: list[FoundAccount] = field(default_factory=list)
    checked: int = 0
    elapsed_seconds: float = 0.0

    @property
    def total_found(self) -> int:
        return len([a for a in self.found if a.status == "claimed"])

    def by_platform(self, platform: str) -> list[FoundAccount]:
        return [a for a in self.found if a.platform == platform]

    def by_tag(self, tag: str) -> list[FoundAccount]:
        return [a for a in self.found if tag in a.tags]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "total_found": self.total_found,
            "checked": self.checked,
            "elapsed_seconds": self.elapsed_seconds,
            "accounts": [a.to_dict() for a in self.found],
        }


class UsernamePermuter:
    """Генератор вариаций ников.

    Стратегии:
    - Добавление точек/подчёркиваний: user.name, user_name
    - Добавление цифр: user1, user2, user123
    - Усечение: us, use (для коротких ников)
    - Регистр: User, USER
    """

    @staticmethod
    def permute(username: str, max_variants: int = 20) -> list[str]:
        """Генерировать вариации username.

        Args:
            username: Исходный ник
            max_variants: Максимум вариаций

        Returns:
            Список уникальных вариаций (включая оригинал)
        """
        variants = {username}

        # Замена точек/подчёркиваний
        if "." in username:
            variants.add(username.replace(".", "_"))
            variants.add(username.replace(".", ""))
        if "_" in username:
            variants.add(username.replace("_", "."))
            variants.add(username.replace("_", ""))

        # Добавление цифр
        for i in range(1, 10):
            variants.add(f"{username}{i}")

        # Усечение (для ников длиннее 3 символов)
        if len(username) > 3:
            variants.add(username[:3])
            variants.add(username[:4])

        # Регистр
        variants.add(username.lower())
        variants.add(username.upper())
        variants.add(username.capitalize())

        # Ограничить
        result = list(variants)[:max_variants]
        return result


class AccountFinder:
    """Рекурсивный поиск аккаунтов.

    Использует PlatformRegistry для проверки наличия аккаунтов
    на множестве платформ одновременно.

    Использование:
        >>> registry = PlatformRegistry()
        >>> registry.load_defaults()
        >>> finder = AccountFinder(registry)
        >>> report = await finder.search("octocat", top_n=20)
        >>> print(f"Found {report.total_found} accounts")
    """

    def __init__(
        self,
        registry: PlatformRegistry | None = None,
        max_concurrent: int = 10,
        timeout: float = 10.0,
        user_agent: str = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    ):
        self.registry = registry or PlatformRegistry()
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self.user_agent = user_agent
        self._permuter = UsernamePermuter()

    async def search(
        self,
        username: str,
        platforms: list[str] | None = None,
        top_n: int = 50,
        tags: list[str] | None = None,
        permute: bool = False,
    ) -> SearchReport:
        """Поиск аккаунта по username.

        Args:
            username: Имя пользователя для поиска
            platforms: Список платформ (None = все)
            top_n: Максимум платформ для проверки
            tags: Фильтр по тегам
            permute: Искать вариации ника

        Returns:
            SearchReport с результатами
        """
        import time
        start = time.time()

        # Определить платформы для проверки
        if platforms:
            profiles = []
            for name in platforms:
                p = self.registry.get(name)
                if p and not p.disabled:
                    profiles.append(p)
        elif tags:
            profiles = self.registry.filter_by_tags(tags)
        else:
            profiles = self.registry.top(top_n)

        # Определить варианты ников
        usernames = [username]
        if permute:
            usernames = self._permuter.permute(username)

        # Проверить все комбинации
        all_results: list[FoundAccount] = []
        checked = 0

        for uname in usernames:
            tasks = []
            for profile in profiles:
                tasks.append(self._check_platform(uname, profile))

            # Запустить с ограничением конкурентности
            semaphore = asyncio.Semaphore(self.max_concurrent)

            async def bounded_check(task_coro):
                async with semaphore:
                    return await task_coro

            results = await asyncio.gather(
                *[bounded_check(t) for t in tasks],
                return_exceptions=True,
            )

            for result in results:
                if isinstance(result, Exception):
                    continue
                if result:
                    checked += 1
                    if result.status == "claimed":
                        all_results.append(result)

        elapsed = time.time() - start
        logger.info(
            f"Search '{username}': {len(all_results)} found, "
            f"{checked} checked, {elapsed:.1f}s"
        )

        return SearchReport(
            query=username,
            found=all_results,
            checked=checked,
            elapsed_seconds=elapsed,
        )

    async def _check_platform(
        self,
        username: str,
        profile: PlatformProfile,
    ) -> FoundAccount | None:
        """Проверить наличие аккаунта на платформе.

        Args:
            username: Имя пользователя
            profile: Профиль платформы

        Returns:
            FoundAccount если аккаунт найден, None если ошибка
        """
        url = profile.url_template.format(username=username)
        result = FoundAccount(
            platform=profile.name,
            username=username,
            url=url,
            tags=profile.tags,
        )

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": self.user_agent},
            ) as client:
                if profile.check_type == CheckType.STATUS_CODE:
                    return await self._check_by_status(client, url, profile, result)
                elif profile.check_type == CheckType.RESPONSE_URL:
                    return await self._check_by_url(client, url, profile, result)
                else:
                    return await self._check_by_message(client, url, profile, result)

        except httpx.TimeoutException:
            result.status = "timeout"
            logger.debug(f"Timeout: {profile.name}/{username}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                result.status = "available"
            else:
                result.status = "error"
                result.metadata["http_status"] = e.response.status_code
        except Exception as e:
            result.status = "error"
            result.metadata["error"] = str(e)[:100]

        return result

    async def _check_by_status(
        self,
        client: httpx.AsyncClient,
        url: str,
        profile: PlatformProfile,
        result: FoundAccount,
    ) -> FoundAccount:
        """Проверка по HTTP статус-коду."""
        response = await client.get(url)
        if response.status_code == 200:
            result.status = "claimed"
            result.confidence = 0.8
        elif response.status_code in (404, 410):
            result.status = "available"
        else:
            result.status = "unknown"
            result.metadata["http_status"] = response.status_code
        return result

    async def _check_by_url(
        self,
        client: httpx.AsyncClient,
        url: str,
        profile: PlatformProfile,
        result: FoundAccount,
    ) -> FoundAccount:
        """Проверка по URL после редиректа."""
        response = await client.get(url)
        final_url = str(response.url)

        # Если URL изменился — вероятно редирект на 404
        if final_url != url and ("404" in final_url or "not-found" in final_url):
            result.status = "available"
        else:
            result.status = "claimed"
            result.confidence = 0.7
        return result

    async def _check_by_message(
        self,
        client: httpx.AsyncClient,
        url: str,
        profile: PlatformProfile,
        result: FoundAccount,
    ) -> FoundAccount:
        """Проверка по подстрокам в HTML (body + title)."""
        response = await client.get(url)
        html = response.text

        # Извлечь title для дополнительной проверки
        title = ""
        if "<title>" in html:
            t_start = html.find("<title>") + 7
            t_end = html.find("</title>", t_start)
            if t_end > t_start:
                title = html[t_start:t_end]

        # Область поиска: title + первые 2000 символов body
        search_text = f"{title} {html[:2000]}".lower()

        # Проверить absence строки (приоритет — если нашли, точно нет)
        for absence in profile.absence_strs:
            if absence.lower() in search_text:
                result.status = "available"
                return result

        # Проверить presence строки
        for presence in profile.presense_strs:
            if presence.lower() in search_text:
                result.status = "claimed"
                result.confidence = 0.9
                return result

        # Если 200 но нет presence строк — неизвестно
        if response.status_code == 200:
            result.status = "unknown"
            result.confidence = 0.3
        else:
            result.status = "available"

        return result

    async def extract_accounts_from_page(
        self,
        page_content: str,
        source_platform: str = "",
    ) -> list[dict[str, str]]:
        """Извлечь ссылки на другие аккаунты из HTML страницы.

        Ищет URL-паттерны известных платформ в тексте страницы.

        Args:
            page_content: HTML или текст страницы
            source_platform: Исходная платформа (для исключения)

        Returns:
            Список {"platform": ..., "username": ..., "url": ...}
        """
        found = []

        for profile in self.registry.all():
            if profile.name == source_platform:
                continue

            # Искать URL профиля в контенте
            pattern = re.escape(profile.url_template).replace(
                r"\{username\}", r"([a-zA-Z0-9_.-]+)"
            )
            matches = re.findall(pattern, page_content)

            for username in set(matches):
                if username and username != profile.username_unclaimed:
                    found.append({
                        "platform": profile.name,
                        "username": username,
                        "url": profile.url_template.format(username=username),
                    })

        return found

    async def recursive_search(
        self,
        username: str,
        max_depth: int = 2,
        top_n: int = 20,
    ) -> SearchReport:
        """Рекурсивный поиск: найти аккаунты → извлечь ссылки → проверить их.

        Args:
            username: Начальный username
            max_depth: Глубина рекурсии (1 = только прямой поиск)
            top_n: Максимум платформ на каждом уровне

        Returns:
            SearchReport со всеми найденными аккаунтами
        """
        all_accounts: list[FoundAccount] = []
        checked_usernames = {username}
        current_level = [username]

        for depth in range(max_depth):
            logger.info(f"Recursive search depth {depth + 1}: {len(current_level)} usernames")

            next_level = []
            for uname in current_level:
                report = await self.search(uname, top_n=top_n)
                all_accounts.extend(report.found)

                # Собрать новые username для следующего уровня
                for account in report.found:
                    if account.username not in checked_usernames:
                        checked_usernames.add(account.username)
                        next_level.append(account.username)

            if not next_level:
                break
            current_level = next_level

        return SearchReport(
            query=username,
            found=all_accounts,
            checked=len(checked_usernames),
        )
