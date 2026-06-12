"""
Кросспостинг: публикация контента на внешние площадки через Playwright.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.metrics import CP_COOKIES_AGE, CP_ERRORS, CP_LATENCY, CP_POSTS, LatencyTimer
from lab_playwright_kit.stealth import StealthConfig, apply_stealth
from lab_playwright_kit.vpn_proxy import VPNProxyManager


@dataclass
class PostContent:
    """Контент для публикации."""
    title: str
    body: str
    tags: list[str]
    image_path: str | None = None


@dataclass
class PlatformConfig:
    """Конфигурация площадки."""
    name: str
    url: str
    login_url: str
    cookies_file: str | None = None
    selectors: dict[str, str] | None = None


# Предустановленные площадки
PLATFORMS = {
    "habr": PlatformConfig(
        name="Habr",
        url="https://habr.com",
        login_url="https://habr.com/auth/login/",
        cookies_file="/root/LabDoctorM/projects/lab-playwright-expert/config/habr_cookies.json",
        selectors={
            "title": "input[name='title']",
            "body": "div[data-test-id='editor-body']",
            "publish": "button[data-test-id='publish']",
            "draft": "button[data-test-id='saveDraft']",
        },
    ),
    "vc_ru": PlatformConfig(
        name="VC.ru",
        url="https://vc.ru",
        login_url="https://vc.ru/login",
        cookies_file="/root/LabDoctorM/projects/lab-playwright-expert/config/vc_cookies.json",
    ),
}


class CrossPoster:
    """Кросспостинг на внешние площадки."""

    def __init__(
        self,
        headless: bool = True,
        stealth: bool = True,
        profile_dir: str | None = None,
        proxy: str | None = None,
    ):
        self.headless = headless
        self.stealth_enabled = stealth
        self.profile_dir = profile_dir
        self.proxy_name = proxy
        self._proxy_manager = VPNProxyManager()
        self._proxy_config: dict | None = None
        if proxy and proxy != "direct":
            p = self._proxy_manager.get(proxy)
            if p:
                self._proxy_config = p.to_playwright_format()
            else:
                logger.warning(f"Proxy '{proxy}' not found, using direct connection")

    async def post(
        self,
        platform: PlatformConfig,
        content: PostContent,
        as_draft: bool = True,
    ) -> dict:
        """Опубликовать контент на площадку.

        Args:
            platform: Конфигурация площадки
            content: Контент
            as_draft: Сохранить как черновик

        Returns:
            Результат: {"success": bool, "url": str, "error": str}
        """
        result = {"success": False, "url": "", "error": ""}
        platform_key = platform.name.lower().replace(" ", "_").replace(".", "_")

        # Отслеживаем возраст куки
        if platform.cookies_file and Path(platform.cookies_file).exists():
            import os as _os
            age_seconds = time.time() - _os.path.getmtime(platform.cookies_file)
            CP_COOKIES_AGE.labels(platform=platform_key).set(age_seconds / 3600)

        with LatencyTimer(CP_LATENCY, labels={"platform": platform_key}):
            async with BrowserManager(
                headless=self.headless,
                profile_dir=self.profile_dir,
                proxy=self._proxy_config,
            ) as browser:
                page = await browser.new_page()

                if self.stealth_enabled:
                    await apply_stealth(page, StealthConfig.full())

                # Загрузить куки если есть
                if platform.cookies_file and Path(platform.cookies_file).exists():
                    cookies = json.loads(Path(platform.cookies_file).read_text())
                    await browser.context.add_cookies(cookies)
                    logger.info(f"Loaded cookies for {platform.name}")

                try:
                    # Перейти на страницу логина
                    await page.goto(platform.login_url)
                    await page.wait_for_load_state("networkidle")

                    # Проверить авторизацию
                    is_logged_in = await self._check_login(page, platform)

                    if not is_logged_in:
                        result["error"] = "NOT_AUTHENTICATED"
                        logger.error(f"Not authenticated on {platform.name}")
                        CP_POSTS.labels(platform=platform_key, status="auth_fail").inc()
                        CP_ERRORS.labels(platform=platform_key, error_type="auth").inc()
                        return result

                    # Навигация к редактору
                    post_url = await self._navigate_to_editor(page, platform)
                    if not post_url:
                        result["error"] = "EDITOR_NOT_FOUND"
                        CP_POSTS.labels(platform=platform_key, status="error").inc()
                        CP_ERRORS.labels(platform=platform_key, error_type="navigation").inc()
                        return result

                    # Заполнить контент
                    await self._fill_content(page, platform, content)

                    # Сохранить/опубликовать
                    if as_draft:
                        await self._save_draft(page, platform)
                    else:
                        await self._publish(page, platform)

                    result["success"] = True
                    result["url"] = page.url
                    CP_POSTS.labels(platform=platform_key, status="success").inc()
                    logger.info(f"Posted to {platform.name}: {page.url}")

                except Exception as e:
                    result["error"] = str(e)
                    error_type = "timeout" if "timeout" in str(e).lower() else "publish"
                    CP_ERRORS.labels(platform=platform_key, error_type=error_type).inc()
                    CP_POSTS.labels(platform=platform_key, status="error").inc()
                    logger.error(f"Crosspost failed on {platform.name}: {e}")

                    # Скриншот ошибки
                    try:
                        await page.screenshot(
                            path=f"/tmp/crosspost_error_{platform.name}.png"
                        )
                    except Exception:
                        pass

        return result

    async def _check_login(self, page, platform: PlatformConfig) -> bool:
        """Проверить авторизацию на площадке."""
        # Базовая проверка — нет ли формы логина
        # Переопределяется для конкретных площадок
        return True

    async def _navigate_to_editor(self, page, platform: PlatformConfig) -> str | None:
        """Перейти к редактору публикации."""
        # Переопределяется для конкретных площадок
        return page.url

    async def _fill_content(
        self, page, platform: PlatformConfig, content: PostContent
    ) -> None:
        """Заполнить контент в редакторе."""
        selectors = platform.selectors or {}

        title_sel = selectors.get("title", "input[name='title'], h1[contenteditable]")
        body_sel = selectors.get("body", "[contenteditable='true']")

        if title_sel:
            title_el = page.locator(title_sel).first
            await title_el.click()
            await title_el.fill(content.title)

        if body_sel:
            body_el = page.locator(body_sel).first
            await body_el.click()
            await body_el.fill(content.body)

    async def _save_draft(self, page, platform: PlatformConfig) -> None:
        """Сохранить как черновик."""
        selectors = platform.selectors or {}
        draft_sel = selectors.get("draft", "button:has-text('Черновик'), button:has-text('Draft')")
        if draft_sel:
            await page.click(draft_sel)

    async def _publish(self, page, platform: PlatformConfig) -> None:
        """Опубликовать."""
        selectors = platform.selectors or {}
        publish_sel = selectors.get("publish", "button:has-text('Опубликовать'), button:has-text('Publish')")
        if publish_sel:
            await page.click(publish_sel)

    # ── P2: Публичные методы для пошагового кросспостинга ──────────────────

    async def load_cookies(self, platform: PlatformConfig) -> list[dict]:
        """Загрузить куки из зашифрованного хранилища.

        Читает cookies из файла, указанного в platform.cookies_file.
        Если файл отсутствует — возвращает пустой список.

        Args:
            platform: Конфигурация площадки с путём к файлу кук

        Returns:
            Список кук в формате Playwright (list[dict])
        """
        if not platform.cookies_file:
            logger.warning(f"No cookies_file configured for {platform.name}")
            return []

        cookies_path = Path(platform.cookies_file)
        if not cookies_path.exists():
            logger.warning(f"Cookies file not found: {cookies_path}")
            return []

        cookies = json.loads(cookies_path.read_text())
        logger.info(
            f"Loaded {len(cookies)} cookies for {platform.name} "
            f"from {cookies_path}"
        )
        return cookies

    async def navigate_to_editor(
        self,
        page,
        platform: PlatformConfig,
    ) -> str:
        """Навигация к редактору публикации.

        Для каждой платформы использует свои селекторы и URL.
        Поддерживает Habr и VC.ru (заглушки для будущих).

        Args:
            page: Playwright Page
            platform: Конфигурация площадки

        Returns:
            URL редактора

        Raises:
            RuntimeError: Если навигация к редактору не удалась
        """
        platform_key = platform.name.lower().replace(" ", "_").replace(".", "_")

        if platform_key == "habr":
            return await self._navigate_to_editor_habr(page, platform)
        elif platform_key in ("vc_ru", "vcru"):
            return await self._navigate_to_editor_vcru(page, platform)
        else:
            # Универсальная навигация
            url = await self._navigate_to_editor(page, platform)
            if not url:
                raise RuntimeError(
                    f"Failed to navigate to editor on {platform.name}"
                )
            return url

    async def fill_article(
        self,
        page,
        platform: PlatformConfig,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> None:
        """Заполнить форму статьи в редакторе.

        Заголовок, тело и теги. Использует селекторы из platform.selectors.

        Args:
            page: Playwright Page
            platform: Конфигурация площадки
            title: Заголовок статьи
            content: Текст статьи (HTML или plain text)
            tags: Список тегов (опционально)
        """
        selectors = platform.selectors or {}
        platform.name.lower().replace(" ", "_").replace(".", "_")

        # Заголовок
        title_sel = selectors.get(
            "title",
            "input[name='title'], h1[contenteditable], "
            "textarea[name='title'], #title",
        )
        if title_sel:
            title_el = page.locator(title_sel).first
            await title_el.click()
            await title_el.fill(title)
            logger.debug(f"Filled title on {platform.name}")

        # Тело
        body_sel = selectors.get(
            "body",
            "[contenteditable='true'], #body, .editor-body, "
            "textarea[name='body']",
        )
        if body_sel:
            body_el = page.locator(body_sel).first
            await body_el.click()
            await body_el.fill(content)
            logger.debug(f"Filled body on {platform.name}")

        # Теги
        if tags:
            tags_sel = selectors.get(
                "tags",
                "input[name='tags'], input[placeholder*='тег'], "
                "input[placeholder*='tag'], .tags-input",
            )
            if tags_sel:
                tags_el = page.locator(tags_sel).first
                for tag in tags:
                    await tags_el.fill(tag)
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(0.3)
                logger.debug(f"Filled {len(tags)} tags on {platform.name}")

        logger.info(f"Article filled on {platform.name}: '{title[:50]}...'")

    async def publish(
        self,
        page,
        platform: PlatformConfig,
        as_draft: bool = True,
    ) -> bool:
        """Опубликовать или сохранить как черновик.

        Args:
            page: Playwright Page
            platform: Конфигурация площадки
            as_draft: True — сохранить как черновик, False — опубликовать

        Returns:
            True если публикация/сохранение успешно
        """
        selectors = platform.selectors or {}

        if as_draft:
            draft_sel = selectors.get(
                "draft",
                "button:has-text('Черновик'), button:has-text('Draft'), "
                "button:has-text('Сохранить'), button[data-test-id='saveDraft']",
            )
            if draft_sel:
                await page.click(draft_sel)
                logger.info(f"Draft saved on {platform.name}")
                return True
            else:
                logger.warning(f"Draft selector not found for {platform.name}")
                return False
        else:
            publish_sel = selectors.get(
                "publish",
                "button:has-text('Опубликовать'), button:has-text('Publish'), "
                "button:has-text('Отправить'), button[data-test-id='publish']",
            )
            if publish_sel:
                await page.click(publish_sel)
                logger.info(f"Published on {platform.name}")
                return True
            else:
                logger.warning(
                    f"Publish selector not found for {platform.name}"
                )
                return False

    # ── P2: Платформенно-специфичные навигаторы ────────────────────────────

    async def _navigate_to_editor_habr(
        self,
        page,
        platform: PlatformConfig,
    ) -> str:
        """Навигация к редактору Habr.

        Переходит на https://habr.com/ru/articles/new/
        """
        editor_url = f"{platform.url}/ru/articles/new/"
        await page.goto(editor_url)
        await page.wait_for_load_state("domcontentloaded")
        logger.info(f"Habr editor: {page.url}")
        return page.url

    async def _navigate_to_editor_vcru(
        self,
        page,
        platform: PlatformConfig,
    ) -> str:
        """Навигация к редактору VC.ru.

        Переходит на https://vc.ru/new
        """
        editor_url = f"{platform.url}/new"
        await page.goto(editor_url)
        await page.wait_for_load_state("domcontentloaded")
        logger.info(f"VC.ru editor: {page.url}")
        return page.url

    async def save_cookies(self, platform: PlatformConfig) -> None:
        """Сохранить куки текущей сессии (для ручной авторизации)."""
        async with BrowserManager(headless=False) as browser:
            page = await browser.new_page()
            await page.goto(platform.login_url)
            logger.info(f"Login to {platform.name} in the browser, then press Enter...")
            await asyncio.sleep(60)  # Время на ручной логин

            cookies = await browser.context.cookies()
            if platform.cookies_file:
                Path(platform.cookies_file).parent.mkdir(parents=True, exist_ok=True)
                Path(platform.cookies_file).write_text(json.dumps(cookies, indent=2))
                logger.info(f"Cookies saved: {platform.cookies_file}")
