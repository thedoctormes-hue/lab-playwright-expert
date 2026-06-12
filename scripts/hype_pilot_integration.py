#!/usr/bin/env python3
"""
Hype Pilot Integration — интеграция TaskTemplate с контент-пайплайном.

Связывает:
- TaskTemplate (AuthTask, CrossPostTask, ContentPublishTask)
- Hype Pilot ORQ (оркестратор)
- Browser Publisher (browser_publish.py)
- Data API (data_api.py)

Использование:
    python3 hype_pilot_integration.py --action publish --platform habr --title "..." --content "..."
    python3 hype_pilot_integration.py --action login --platform habr
    python3 hype_pilot_integration.py --action crosspost --platforms habr,vc_ru --title "..." --content "..."
    python3 hype_pilot_integration.py --action monitor --url "https://habr.com/ru/articles/123"
    python3 hype_pilot_integration.py --action collect --urls url1 url2 url3 --niche news
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# Добавить lab_playwright_kit в path
KIT_PATH = Path("/root/LabDoctorM/projects/lab-playwright-expert/src")
sys.path.insert(0, str(KIT_PATH))

from loguru import logger

from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.task_template import (
    AuthTask,
    ContentPublishTask,
    CrossPostTask,
    DataCollectionTask,
    MonitoringTask,
    TaskContext,
    TaskStatus,
)
from lab_playwright_kit.health_monitor import HealthCheck, HealthMonitor, HealthStatus

# Пути
HYPE_PILOT_DIR = Path("/root/LabDoctorM/projects/hype-pilot")
COOKIES_DIR = HYPE_PILOT_DIR / "data" / ".browser_cookies"
COOKIES_DIR.mkdir(parents=True, exist_ok=True)

BROWSER_PUBLISH = HYPE_PILOT_DIR / "browser" / "publish.py"


# ─── Hype Pilot Publisher ────────────────────────────────────────────────────

class HypePilotPublisher:
    """Публикация контента через Hype Pilot pipeline."""

    def __init__(self, headless: bool = True):
        self._headless = headless
        self._health = HealthMonitor()

    async def login(self, platform: str) -> TaskContext:
        """Авторизация на платформе через AuthTask."""
        logger.info(f"[Hype Pilot] Авторизация на {platform}...")

        async with BrowserManager(
            headless=False,
            timeout=120000,
        ) as browser:
            auth = AuthTask(browser)

            platform_urls = {
                "habr": "https://habr.com/ru/auth/",
                "vc_ru": "https://vc.ru/auth",
                "tenchat": "https://tenchat.ru/login",
            }

            url = platform_urls.get(platform, "")

            # Открываем браузер и ждём ручной авторизации
            ctx = await auth.login(
                login_url=url,
                username_selector="input[name='email'], input[name='login'], input[type='email']",
                password_selector="input[name='password'], input[type='password']",
                submit_selector="button[type='submit'], .auth-form__button",
            )

            if ctx.status == TaskStatus.COMPLETED:
                cookies = auth.get_cookies()
                cookie_file = COOKIES_DIR / f"{platform}_cookies.json"
                cookie_file.write_text(json.dumps(cookies, indent=2))
                logger.info(f"[Hype Pilot] ✅ Cookies сохранены: {cookie_file}")

            return ctx

    async def publish(
        self,
        platform: str,
        title: str,
        content: str,
    ) -> TaskContext:
        """Опубликовать контент на платформе."""
        logger.info(f"[Hype Pilot] Публикация на {platform}: {title[:50]}...")

        async with BrowserManager(
            headless=self._headless,
            timeout=60000,
        ) as browser:
            task = ContentPublishTask(browser, platform=platform)
            ctx = await task.publish(
                url="",
                title=title,
                content=content,
            )

            self._health._record_check(HealthCheck(
                name=f"publish_{platform}",
                status=HealthStatus.OK if ctx.status == TaskStatus.COMPLETED else HealthStatus.FAIL,
                metadata=ctx.to_dict(),
            ))

            return ctx

    async def crosspost(
        self,
        title: str,
        content: str,
        platforms: list[str] | None = None,
    ) -> list[TaskContext]:
        """Кросспостинг на несколько платформ."""
        platforms = platforms or ["telegraph"]
        logger.info(f"[Hype Pilot] Кросспостинг: {platforms}")

        async with BrowserManager(
            headless=self._headless,
            timeout=120000,
        ) as browser:
            task = CrossPostTask(browser)
            return await task.crosspost(
                title=title,
                content=content,
                platforms=platforms,
            )

    async def collect_data(
        self,
        urls: list[str],
        niche: str = "generic",
    ) -> list[TaskContext]:
        """Сбор данных с URL."""
        logger.info(f"[Hype Pilot] Сбор данных: {len(urls)} URL, ниша: {niche}")

        async with BrowserManager(
            headless=self._headless,
            timeout=60000,
        ) as browser:
            task = DataCollectionTask(browser, niche=niche)
            return await task.collect(urls, niche=niche)

    async def monitor(
        self,
        url: str,
        selector: str = "body",
    ) -> TaskContext:
        """Мониторинг изменений."""
        logger.info(f"[Hype Pilot] Мониторинг: {url}")

        async with BrowserManager(
            headless=self._headless,
            timeout=60000,
        ) as browser:
            task = MonitoringTask(browser)
            return await task.check_once(url, selector)

    async def close(self):
        pass


# ─── CLI wrapper ──────────────────────────────────────────────────────────────

def run_browser_publish(platform: str, title: str, content: str) -> str:
    """Запустить browser_publish.py как subprocess."""
    cmd = [
        sys.executable, str(BROWSER_PUBLISH),
        "--platform", platform,
        "--title", title,
        "--content", content,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode == 0:
        return result.stdout.strip()
    else:
        logger.error(f"browser_publish failed: {result.stderr}")
        return ""


def run_browser_login(platform: str) -> bool:
    """Запустить browser_publish.py --login как subprocess."""
    cmd = [
        sys.executable, str(BROWSER_PUBLISH),
        "--platform", platform,
        "--login",
    ]
    result = subprocess.run(cmd, timeout=300)
    return result.returncode == 0


async def main_async(args):
    publisher = HypePilotPublisher(headless=not args.visible)

    if args.action == "login":
        if not args.platform:
            logger.error("--platform обязателен для login")
            sys.exit(1)
        ctx = await publisher.login(args.platform)
        print(f"Auth: {ctx.status.value}")

    elif args.action == "publish":
        if not args.platform or not args.content:
            logger.error("--platform и --content обязательны")
            sys.exit(1)

        # Сначала пробуем напрямую через browser_publish.py
        url = run_browser_publish(args.platform, args.title, args.content)
        if url:
            print(f"Published: {url}")
        else:
            # Fallback на TaskTemplate
            logger.info("Fallback на TaskTemplate...")
            ctx = await publisher.publish(args.platform, args.title, args.content)
            print(f"Status: {ctx.status.value}")

    elif args.action == "crosspost":
        if not args.content:
            logger.error("--content обязателен")
            sys.exit(1)
        platforms = args.platforms.split(",") if args.platforms else ["telegraph"]
        results = await publisher.crosspost(args.title, args.content, platforms)
        for r in results:
            print(f"{r.metadata.get('platform', '?')}: {r.status.value}")

    elif args.action == "collect":
        if not args.urls:
            logger.error("--urls обязателен")
            sys.exit(1)
        results = await publisher.collect_data(args.urls, args.niche or "generic")
        for r in results:
            print(f"{r.metadata.get('url', '?')}: {r.status.value}")

    elif args.action == "monitor":
        if not args.url:
            logger.error("--url обязателен")
            sys.exit(1)
        ctx = await publisher.monitor(args.url, args.selector or "body")
        print(f"Monitor: {ctx.status.value}")
        if ctx.results:
            meta = ctx.results[0].metadata
            print(f"Changed: {meta.get('changed', '?')}")

    elif args.action == "health":
        report = publisher._health.get_report()
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))

    else:
        logger.error(f"Неизвестное действие: {args.action}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Hype Pilot Integration — TaskTemplate + Browser Publisher"
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=["login", "publish", "crosspost", "collect", "monitor", "health"],
        help="Действие",
    )
    parser.add_argument("--platform", help="Платформа (habr, vc_ru, tenchat)")
    parser.add_argument("--platforms", help="Платформы через запятую для crosspost")
    parser.add_argument("--title", default="", help="Заголовок")
    parser.add_argument("--content", default="", help="Контент")
    parser.add_argument("--urls", nargs="+", help="URL для сбора данных")
    parser.add_argument("--niche", default="generic", help="Ниша для парсинга")
    parser.add_argument("--url", help="URL для мониторинга")
    parser.add_argument("--selector", default="body", help="CSS-селектор для мониторинга")
    parser.add_argument("--visible", action="store_true", help="Показать браузер (не headless)")

    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
