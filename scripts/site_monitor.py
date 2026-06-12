#!/usr/bin/env python3
"""
Site Monitor v2 — визуальный мониторинг сайтов лаборатории.
Использует lab_playwright_kit.

Запуск:
  python3 site_monitor.py                    # проверить все сайты
  python3 site_monitor.py --init-baselines   # создать эталонные скриншоты
  python3 site_monitor.py --report           # сохранить JSON-отчёт
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path


# Добавить lab_playwright_kit в path
KIT_PATH = Path("/root/LabDoctorM/projects/lab-playwright-expert/src")
sys.path.insert(0, str(KIT_PATH))

from loguru import logger

from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.metrics import (
    SM_CHECKS,
    SM_HTTP_STATUS,
    SM_LATENCY,
    SM_UPTIME,
    SM_VISUAL_DIFF,
    LatencyTimer,
)
from lab_playwright_kit.screenshot import ScreenshotMaker
from lab_playwright_kit.stealth import StealthConfig, apply_stealth
from lab_playwright_kit.vpn_proxy import VPNProxyManager


# Конфигурация сайтов
DEFAULT_SITES = [
    {
        "name": "snablab",
        "url": "https://snablab.shtab-ai.ru",
        "expected_title": "СнабЛаб",
        "expected_text": "Управление закупками",
        "selectors": [],
        "wait_until": "networkidle",
    },
    {
        "name": "blog",
        "url": "https://articles.shtab-ai.ru",
        "expected_title": "",
        "selectors": [],
        "wait_until": "domcontentloaded",
        "critical": False,
    },
]

# Пути
SCREENSHOT_DIR = Path("/tmp/playwright_monitor")
BASELINE_DIR = Path("/tmp/playwright_baselines")
REPORT_FILE = Path("/tmp/monitor_report.json")

# Telegram для алертов
TELEGRAM_BOT_TOKEN = os.getenv("MONITOR_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("MONITOR_CHAT_ID", "")


async def send_telegram_alert(message: str) -> None:
    """Отправить алерт в Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": message,
                    "parse_mode": "HTML",
                },
            )
    except Exception as e:
        logger.error(f"Telegram alert failed: {e}")


async def check_site(
    site: dict,
    headless: bool = True,
    proxy_config: dict | None = None,
) -> dict:
    """Проверить один сайт.

    Args:
        site: Конфигурация сайта
        headless: Headless-режим браузера
        proxy_config: Конфиг прокси для Playwright или None
    """
    url = site["url"]
    name = site.get("name", url)
    expected_title = site.get("expected_title", "")
    expected_text = site.get("expected_text", "")
    check_selectors = site.get("selectors", [])

    start = datetime.now()
    result = {
        "url": url,
        "name": name,
        "timestamp": start.isoformat(),
        "status": "error",
        "status_code": None,
        "load_time_ms": 0,
        "title": "",
        "screenshot_path": None,
        "error": None,
        "visual_match": None,
        "visual_diff_ratio": None,
    }

    with LatencyTimer(SM_LATENCY, labels={"site": name}):
        async with BrowserManager(
            headless=headless,
            timeout=30000,
            proxy=proxy_config,
        ) as browser:
            page = await browser.new_page()
            await apply_stealth(page, StealthConfig.minimal())

            try:
                wait_mode = site.get("wait_until", "domcontentloaded")
                response = await page.goto(url, wait_until=wait_mode)
                result["status_code"] = response.status if response else None
                result["load_time_ms"] = (datetime.now() - start).total_seconds() * 1000
                result["title"] = await page.title()

                # HTTP статус
                if result["status_code"] and result["status_code"] >= 400:
                    result["status"] = "error"
                    result["error"] = f"HTTP {result['status_code']}"
                    SM_CHECKS.labels(site=name, status="error").inc()
                    SM_HTTP_STATUS.labels(site=name).set(result["status_code"] or 0)
                    return result

                # Ожидаемый заголовок
                if expected_title and expected_title not in result["title"]:
                    result["status"] = "degraded"
                    result["error"] = f"Title: expected '{expected_title}', got '{result['title']}'"
                    SM_CHECKS.labels(site=name, status="degraded").inc()
                    SM_HTTP_STATUS.labels(site=name).set(result["status_code"] or 0)
                    return result

                # Ожидаемый текст
                if expected_text:
                    body = await page.inner_text("body")
                    if expected_text not in body:
                        result["status"] = "degraded"
                        result["error"] = f"Text not found: '{expected_text}'"
                        SM_CHECKS.labels(site=name, status="degraded").inc()
                        SM_HTTP_STATUS.labels(site=name).set(result["status_code"] or 0)
                        return result

                # Селекторы
                for sel in check_selectors:
                    try:
                        visible = await page.locator(sel).first.is_visible()
                        if not visible:
                            result["status"] = "degraded"
                            result["error"] = f"Selector not visible: {sel}"
                            SM_CHECKS.labels(site=name, status="degraded").inc()
                            SM_HTTP_STATUS.labels(site=name).set(result["status_code"] or 0)
                            return result
                    except Exception:
                        result["status"] = "degraded"
                        result["error"] = f"Selector error: {sel}"
                        SM_CHECKS.labels(site=name, status="degraded").inc()
                        SM_HTTP_STATUS.labels(site=name).set(result["status_code"] or 0)
                        return result

                # Скриншот
                maker = ScreenshotMaker(str(SCREENSHOT_DIR))
                result["screenshot_path"] = await maker.viewport(page, prefix=f"monitor_{name}")

                # Визуальное сравнение
                baseline = BASELINE_DIR / f"{name}_baseline.png"
                if baseline.exists():
                    match, diff_ratio, _ = await maker.compare(page, str(baseline), 0.15)
                    result["visual_match"] = match
                    result["visual_diff_ratio"] = diff_ratio
                    SM_VISUAL_DIFF.labels(site=name).set(diff_ratio or 0)
                    if not match:
                        result["status"] = "degraded"
                        result["error"] = f"Visual diff: {diff_ratio:.2%}"
                        SM_CHECKS.labels(site=name, status="degraded").inc()
                        SM_HTTP_STATUS.labels(site=name).set(result["status_code"] or 0)
                        return result

                result["status"] = "ok"
                SM_CHECKS.labels(site=name, status="ok").inc()
                SM_HTTP_STATUS.labels(site=name).set(result["status_code"] or 0)

            except Exception as e:
                result["status"] = "error"
                result["error"] = str(e)
                result["load_time_ms"] = (datetime.now() - start).total_seconds() * 1000
                SM_CHECKS.labels(site=name, status="error").inc()
                SM_HTTP_STATUS.labels(site=name).set(0)
                logger.error(f"Check failed for {url}: {e}")

    return result


async def init_baselines(sites: list) -> None:
    """Создать эталонные скриншоты."""
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    for site in sites:
        logger.info(f"Creating baseline for {site['name']}...")
        result = await check_site(site)

        if result["status"] == "ok" and result["screenshot_path"]:
            import shutil
            baseline_path = BASELINE_DIR / f"{site['name']}_baseline.png"
            shutil.copy2(result["screenshot_path"], baseline_path)
            logger.info(f"✅ Baseline saved: {baseline_path}")
        else:
            logger.error(f"❌ Failed baseline for {site['name']}: {result.get('error')}")


# ═══════════════════════════════════════════════════════════════════════════════
# ServiceMonitor — расширенный мониторинг доступности сервисов
# ═══════════════════════════════════════════════════════════════════════════════

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CheckResult:
    """Результат проверки одного сервиса."""

    name: str
    url: str
    timestamp: str
    status: str  # "ok" | "degraded" | "error"
    status_code: int | None
    load_time_ms: float
    title: str
    content_found: bool
    screenshot_path: str | None = None
    visual_match: bool | None = None
    visual_diff_ratio: float | None = None
    error: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


class ServiceMonitor:
    """Расширенный мониторинг доступности сервисов.

    Использует Playwright для проверки HTTP-статуса, времени загрузки,
    наличия контента и визуального сравнения с эталоном.

    Example:
        >>> monitor = ServiceMonitor(headless=True)
        >>> result = await monitor.check_url("https://example.com")
        >>> results = await monitor.check_all(config)
    """

    def __init__(
        self,
        headless: bool = True,
        timeout: int = 30000,
        screenshot_dir: str = "/tmp/playwright_monitor",
        baseline_dir: str = "/tmp/playwright_baselines",
        visual_threshold: float = 0.15,
    ):
        self.headless = headless
        self.timeout = timeout
        self.screenshot_dir = Path(screenshot_dir)
        self.baseline_dir = Path(baseline_dir)
        self.visual_threshold = visual_threshold
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.baseline_dir.mkdir(parents=True, exist_ok=True)

    async def check_url(
        self,
        url: str,
        expected_status: int = 200,
        expected_title: str = "",
        expected_text: str = "",
        selectors: list[str] | None = None,
        name: str = "",
        wait_until: str = "domcontentloaded",
        visual_check: bool = False,
    ) -> CheckResult:
        """Проверить один URL.

        Проверяет HTTP-статус, время загрузки, наличие ожидаемого
        заголовка/текста и видимость селекторов.

        Args:
            url: URL для проверки
            expected_status: Ожидаемый HTTP-статус (по умолчанию 200)
            expected_title: Ожидаемый текст в заголовке (title)
            expected_text: Ожидаемый текст в body
            selectors: CSS-селекторы, которые должны быть видимы
            name: Имя сервиса (для отчётов)
            wait_until: Режим ожидания загрузки
            visual_check: Сравнить с эталонным скриншотом

        Returns:
            CheckResult с результатами проверки
        """
        from datetime import datetime as dt

        service_name = name or url
        start = dt.now()
        result = CheckResult(
            name=service_name,
            url=url,
            timestamp=start.isoformat(),
            status="error",
            status_code=None,
            load_time_ms=0,
            title="",
            content_found=True,
        )

        with LatencyTimer(SM_LATENCY, labels={"site": service_name}):
            async with BrowserManager(
                headless=self.headless,
                timeout=self.timeout,
            ) as browser:
                page = await browser.new_page()
                await apply_stealth(page, StealthConfig.minimal())

                try:
                    response = await page.goto(url, wait_until=wait_until)
                    result.status_code = response.status if response else None
                    result.load_time_ms = (
                        dt.now() - start
                    ).total_seconds() * 1000
                    result.title = await page.title()

                    # Проверка HTTP-статуса
                    if result.status_code != expected_status:
                        result.status = "error"
                        result.error = (
                            f"HTTP {result.status_code} "
                            f"(expected {expected_status})"
                        )
                        SM_CHECKS.labels(
                            site=service_name, status="error"
                        ).inc()
                        return result

                    # Проверка заголовка
                    if expected_title and expected_title not in result.title:
                        result.status = "degraded"
                        result.error = (
                            f"Title mismatch: expected "
                            f"'{expected_title}', got '{result.title}'"
                        )
                        SM_CHECKS.labels(
                            site=service_name, status="degraded"
                        ).inc()
                        return result

                    # Проверка текста
                    if expected_text:
                        body = await page.inner_text("body")
                        if expected_text not in body:
                            result.status = "degraded"
                            result.content_found = False
                            result.error = (
                                f"Text not found: '{expected_text}'"
                            )
                            SM_CHECKS.labels(
                                site=service_name, status="degraded"
                            ).inc()
                            return result

                    # Проверка селекторs
                    for sel in (selectors or []):
                        try:
                            visible = await page.locator(sel).first.is_visible()
                            if not visible:
                                result.status = "degraded"
                                result.error = (
                                    f"Selector not visible: {sel}"
                                )
                                SM_CHECKS.labels(
                                    site=service_name, status="degraded"
                                ).inc()
                                return result
                        except Exception:
                            result.status = "degraded"
                            result.error = f"Selector error: {sel}"
                            SM_CHECKS.labels(
                                site=service_name, status="degraded"
                            ).inc()
                            return result

                    # Скриншот
                    maker = ScreenshotMaker(str(self.screenshot_dir))
                    result.screenshot_path = await maker.viewport(
                        page, prefix=f"sm_{service_name}"
                    )

                    # Визуальное сравнение
                    if visual_check:
                        baseline = self.baseline_dir / f"{service_name}_baseline.png"
                        if baseline.exists():
                            match, diff_ratio, _ = await maker.compare(
                                page, str(baseline), self.visual_threshold
                            )
                            result.visual_match = match
                            result.visual_diff_ratio = diff_ratio
                            SM_VISUAL_DIFF.labels(site=service_name).set(
                                diff_ratio or 0
                            )
                            if not match:
                                result.status = "degraded"
                                result.error = (
                                    f"Visual diff: {diff_ratio:.2%}"
                                )
                                SM_CHECKS.labels(
                                    site=service_name, status="degraded"
                                ).inc()
                                return result

                    result.status = "ok"
                    SM_CHECKS.labels(
                        site=service_name, status="ok"
                    ).inc()

                except Exception as e:
                    result.status = "error"
                    result.error = str(e)
                    result.load_time_ms = (
                        dt.now() - start
                    ).total_seconds() * 1000
                    SM_CHECKS.labels(
                        site=service_name, status="error"
                    ).inc()
                    logger.error(f"ServiceMonitor check failed for {url}: {e}")

        return result

    async def check_all(
        self,
        config: dict[str, Any],
    ) -> list[CheckResult]:
        """Проверить все сервисы из конфига.

        Args:
            config: Конфигурация с ключом "services" — список
                    словарей с параметрами сервисов.

        Returns:
            Список CheckResult для каждого сервиса

        Example:
            >>> config = {
            ...     "services": [
            ...         {"name": "snablab", "url": "https://snablab.shtab-ai.ru",
            ...          "expected_status": 200, "expected_title": "СнабЛаб"},
            ...     ]
            ... }
            >>> results = await monitor.check_all(config)
        """
        services = config.get("services", [])
        tasks = []
        for svc in services:
            tasks.append(self.check_url(
                url=svc["url"],
                expected_status=svc.get("expected_status", 200),
                expected_title=svc.get("expected_title", ""),
                expected_text=svc.get("expected_text", ""),
                selectors=svc.get("selectors"),
                name=svc.get("name", svc["url"]),
                wait_until=svc.get("wait_until", "domcontentloaded"),
                visual_check=svc.get("visual_baseline", False),
            ))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed: list[CheckResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed.append(CheckResult(
                    name=services[i].get("name", services[i]["url"]),
                    url=services[i]["url"],
                    timestamp=datetime.now().isoformat(),
                    status="error",
                    status_code=None,
                    load_time_ms=0,
                    title="",
                    content_found=False,
                    error=str(result),
                ))
            else:
                processed.append(result)

        # Обновить метрики аптайма
        for r in processed:
            SM_UPTIME.labels(site=r.name).set(
                1.0 if r.status == "ok" else 0.0
            )

        logger.info(
            f"ServiceMonitor: checked {len(processed)} services — "
            f"{sum(1 for r in processed if r.status == 'ok')} ok, "
            f"{sum(1 for r in processed if r.status == 'degraded')} degraded, "
            f"{sum(1 for r in processed if r.status == 'error')} error"
        )
        return processed

    async def take_screenshot(
        self,
        url: str,
        path: str | None = None,
        full_page: bool = False,
        wait_until: str = "domcontentloaded",
    ) -> str:
        """Сделать скриншот страницы для отчёта.

        Args:
            url: URL страницы
            path: Путь для сохранения (если None — авто-имя)
            full_page: Скриншот всей страницы
            wait_until: Режим ожидания загрузки

        Returns:
            Путь к сохранённому скриншоту
        """
        maker = ScreenshotMaker(str(self.screenshot_dir))

        async with BrowserManager(
            headless=self.headless,
            timeout=self.timeout,
        ) as browser:
            page = await browser.new_page()
            await apply_stealth(page, StealthConfig.minimal())
            await page.goto(url, wait_until=wait_until)

            if path:
                # Кастомный путь
                if full_page:
                    await page.screenshot(path=path, full_page=True)
                else:
                    await page.screenshot(path=path)
                logger.info(f"Screenshot saved: {path}")
                return path
            else:
                if full_page:
                    return await maker.full_page(page, prefix="report")
                else:
                    return await maker.viewport(page, prefix="report")

    async def compare_visual(
        self,
        baseline_path: str,
        current_path: str | None = None,
        url: str | None = None,
        threshold: float | None = None,
    ) -> tuple[bool, float, str | None]:
        """Визуальное сравнение эталона с текущим состоянием.

        Можно сравнить два файла напрямую или сначала сделать
        скриншот страницы, а потом сравнить.

        Args:
            baseline_path: Путь к эталонному скриншоту
            current_path: Путь к текущему скриншоту (если None — сделать новый)
            url: URL для свежего скриншота (используется если current_path=None)
            threshold: Порог различий (по умолчанию self.visual_threshold)

        Returns:
            (match, diff_ratio, diff_path)
            - match: True если различия в пределах порога
            - diff_ratio: Доля отличающихся пикселей (0.0-1.0)
            - diff_path: Путь к изображению отличий (None если match=True)
        """

        from PIL import Image

        thresh = threshold if threshold is not None else self.visual_threshold

        # Если нет текущего скриншота — сделать
        if current_path is None:
            if url is None:
                raise ValueError(
                    "Either current_path or url must be provided"
                )
            current_path = await self.take_screenshot(url)

        # Загрузить изображения
        baseline_img = Image.open(baseline_path).convert("RGB")
        current_img = Image.open(current_path).convert("RGB")

        # Привести к одному размеру
        if current_img.size != baseline_img.size:
            current_img = current_img.resize(baseline_img.size)

        # Pix-by-pix сравнение
        pixels_baseline = list(baseline_img.getdata())
        pixels_current = list(current_img.getdata())

        diff_pixels = sum(
            1 for p1, p2 in zip(pixels_baseline, pixels_current)
            if abs(p1[0] - p2[0]) + abs(p1[1] - p2[1]) + abs(p1[2] - p2[2]) > 30
        )
        total_pixels = len(pixels_baseline)
        diff_ratio = diff_pixels / total_pixels if total_pixels else 1.0
        match = diff_ratio <= thresh

        diff_path = None
        if not match:
            # Сохранить визуализацию отличий
            import itertools
            diff_img = Image.new("RGB", baseline_img.size)
            for i, (p1, p2) in enumerate(
                zip(
                    itertools.islice(pixels_current, total_pixels),
                    pixels_baseline,
                )
            ):
                if abs(p1[0] - p2[0]) + abs(p1[1] - p2[1]) + abs(p1[2] - p2[2]) > 30:
                    diff_img.putpixel(
                        (i % baseline_img.size[0], i // baseline_img.size[0]),
                        (255, 0, 0),
                    )
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            diff_path = str(self.screenshot_dir / f"diff_{ts}.png")
            diff_img.save(diff_path)

        logger.info(
            f"Visual compare: match={match}, diff={diff_ratio:.2%}"
        )
        return match, diff_ratio, diff_path


async def check_all(
    sites: list,
    headless: bool = True,
    proxy_config: dict | None = None,
) -> list:
    """Проверить все сайты."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)

    tasks = [check_site(site, headless, proxy_config) for site in sites]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    processed = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed.append({
                "url": sites[i]["url"],
                "name": sites[i].get("name", sites[i]["url"]),
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "status_code": None,
                "load_time_ms": 0,
                "title": "",
                "error": str(result),
            })
        else:
            processed.append(result)

    return processed


def save_report(results: list, path: Path = REPORT_FILE) -> None:
    """Сохранить отчёт."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "total": len(results),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "degraded": sum(1 for r in results if r["status"] == "degraded"),
        "error": sum(1 for r in results if r["status"] == "error"),
        "checks": results,
    }
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    logger.info(f"Report saved: {path}")


async def main():
    parser = argparse.ArgumentParser(description="Site Monitor v2")
    parser.add_argument("--init-baselines", action="store_true", help="Создать эталонные скриншоты")
    parser.add_argument("--report", action="store_true", help="Сохранить JSON-отчёт")
    parser.add_argument("--no-headless", action="store_true", help="Показать браузер")
    parser.add_argument("--sites", nargs="+", default=None, help="Имена сайтов для проверки")
    parser.add_argument(
        "--proxy",
        default=None,
        choices=["poland", "florida", "direct"],
        help="VPN-прокси для проверки (poland, florida, direct)",
    )

    args = parser.parse_args()

    sites = DEFAULT_SITES
    if args.sites:
        sites = [s for s in DEFAULT_SITES if s["name"] in args.sites]

    # Загрузить прокси
    proxy_config = None
    if args.proxy:
        pm = VPNProxyManager()
        p = pm.get(args.proxy)
        if p:
            proxy_config = p.to_playwright_format()
            logger.info(f"Using VPN proxy: {args.proxy}")
        else:
            logger.warning(f"Proxy '{args.proxy}' not found, using direct")

    if args.init_baselines:
        await init_baselines(sites)
        return

    results = await check_all(sites, headless=not args.no_headless, proxy_config=proxy_config)

    # Вывод
    for r in results:
        emoji = {"ok": "✅", "degraded": "⚠️", "error": "❌"}.get(r["status"], "❓")
        load = f"({r.get('load_time_ms', 0):.0f}ms)" if r.get("load_time_ms") else ""
        print(f"{emoji} {r.get('name', r['url'])} — {r['status']} {load}")
        if r.get("error"):
            print(f"   → {r['error']}")

        # Алерт при проблемах
        if r["status"] in ("error", "degraded"):
            alert = f"🚨 <b>Monitor Alert</b>\n{emoji} {r.get('name', r['url'])}\n{r['status']}: {r.get('error', '')}"
            await send_telegram_alert(alert)

    if args.report:
        save_report(results)

    # Exit code если есть ошибки на КРИТИЧЕСКИХ сайтах
    critical_errors = [
        r for r in results
        if r["status"] == "error"
        and any(s.get("critical", True) for s in sites if s.get("name") == r.get("name"))
    ]
    if critical_errors:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
