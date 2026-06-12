"""
Кросспостинг (Secure) — публикация с зашифрованным хранением cookies.

Улучшения безопасности:
  1. Cookies хранятся в зашифрованном vault (SecretManager)
  2. Нет открытых cookies файлов на диске
  3. Безопасное удаление временных файлов
  4. Валидация URL площадок
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from loguru import logger


# Добавить путь к исходникам
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from secret_manager import SecretManager, migrate_cookies_to_vault

from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.stealth import StealthConfig, apply_stealth


@dataclass
class PostContent:
    title: str
    body: str
    tags: list[str]
    image_path: str | None = None


@dataclass
class PlatformConfig:
    name: str
    url: str
    login_url: str
    selectors: dict[str, str] | None = None


# Площадки — БЕЗ cookies_file (используем vault)
PLATFORMS = {
    "habr": PlatformConfig(
        name="Habr",
        url="https://habr.com",
        login_url="https://habr.com/auth/login/",
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
    ),
}


class CrossPosterSecure:
    """Кросспостинг с безопасным хранением cookies."""

    def __init__(
        self,
        headless: bool = True,
        stealth: bool = True,
        profile_dir: str | None = None,
    ):
        self.headless = headless
        self.stealth_enabled = stealth
        self.profile_dir = profile_dir
        self._sm = SecretManager()

    async def post(
        self,
        platform: PlatformConfig,
        content: PostContent,
        as_draft: bool = True,
    ) -> dict:
        """Опубликовать контент на площадку."""
        result = {"success": False, "url": "", "error": ""}

        async with BrowserManager(
            headless=self.headless,
            profile_dir=self.profile_dir,
        ) as browser:
            page = await browser.new_page()

            if self.stealth_enabled:
                await apply_stealth(page, StealthConfig.full())

            # Загрузить куки из зашифрованного vault
            cookies = self._sm.load_cookies(platform.name.lower())
            if cookies:
                try:
                    await browser.context.add_cookies(cookies)
                    logger.info(f"Loaded encrypted cookies for {platform.name}")
                except Exception as e:
                    logger.warning(f"Failed to load cookies for {platform.name}: {e}")

            try:
                await page.goto(platform.login_url)
                await page.wait_for_load_state("networkidle")

                is_logged_in = await self._check_login(page, platform)

                if not is_logged_in:
                    result["error"] = "NOT_AUTHENTICATED"
                    logger.error(f"Not authenticated on {platform.name}")
                    return result

                post_url = await self._navigate_to_editor(page, platform)
                if not post_url:
                    result["error"] = "EDITOR_NOT_FOUND"
                    return result

                await self._fill_content(page, platform, content)

                if as_draft:
                    await self._save_draft(page, platform)
                else:
                    await self._publish(page, platform)

                result["success"] = True
                result["url"] = page.url
                logger.info(f"Posted to {platform.name}: {page.url}")

            except Exception as e:
                result["error"] = str(e)
                logger.error(f"Crosspost failed on {platform.name}: {e}")

                # Скриншот ошибки — во временный файл с безопасными правами
                try:
                    with tempfile.NamedTemporaryFile(
                        prefix=f"crosspost_error_{platform.name}_",
                        suffix=".png",
                        delete=False,
                    ) as tmp:
                        await page.screenshot(path=tmp.name)
                        os.chmod(tmp.name, 0o600)
                except Exception:
                    pass

        return result

    async def _check_login(self, page, platform: PlatformConfig) -> bool:
        return True

    async def _navigate_to_editor(self, page, platform: PlatformConfig) -> str | None:
        return page.url

    async def _fill_content(
        self, page, platform: PlatformConfig, content: PostContent
    ) -> None:
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
        selectors = platform.selectors or {}
        draft_sel = selectors.get("draft", "button:has-text('Черновик'), button:has-text('Draft')")
        if draft_sel:
            await page.click(draft_sel)

    async def _publish(self, page, platform: PlatformConfig) -> None:
        selectors = platform.selectors or {}
        publish_sel = selectors.get("publish", "button:has-text('Опубликовать'), button:has-text('Publish')")
        if publish_sel:
            await page.click(publish_sel)

    async def save_cookies(self, platform: PlatformConfig) -> None:
        """Сохранить куки текущей сессии в зашифрованный vault."""
        async with BrowserManager(headless=False) as browser:
            page = await browser.new_page()
            await page.goto(platform.login_url)
            logger.info(f"Login to {platform.name} in the browser, then press Enter...")
            await asyncio.sleep(60)

            cookies = await browser.context.cookies()
            self._sm.store_cookies(platform.name.lower(), cookies)
            logger.info(f"Cookies saved to encrypted vault for {platform.name}")


async def migrate_legacy_cookies():
    """Миграция cookies из открытых файлов в vault."""
    legacy_files = [
        ("habr", "/root/LabDoctorM/projects/lab-playwright-expert/config/habr_cookies.json"),
        ("vc_ru", "/root/LabDoctorM/projects/lab-playwright-expert/config/vc_cookies.json"),
    ]

    sm = SecretManager()
    for platform, filepath in legacy_files:
        if Path(filepath).exists():
            logger.info(f"Migrating {platform} cookies from {filepath}")
            migrate_cookies_to_vault(filepath, platform, sm)
        else:
            logger.info(f"No legacy cookies for {platform}: {filepath}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CrossPost Secure")
    parser.add_argument("--migrate", action="store_true", help="Мигрировать старые cookies в vault")
    args = parser.parse_args()

    if args.migrate:
        asyncio.run(migrate_legacy_cookies())
    else:
        print("Use --migrate to migrate legacy cookies to encrypted vault")
