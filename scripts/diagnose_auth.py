#!/usr/bin/env python3
"""
Диагностика авторизации на платформах.

Проверяет что селекторы из пресетов работают на реальных сайтах.
Открывает headless-браузер, загружает страницы, проверяет селекторы.

Запуск:
  python3 diagnose_auth.py habr
  python3 diagnose_auth.py vcru
  python3 diagnose_auth.py twitter
  python3 diagnose_auth.py telegram
  python3 diagnose_auth.py all
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from loguru import logger

from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.stealth import StealthConfig
from lab_playwright_kit.browser_auth import AUTH_PRESETS, AuthPreset


async def check_selectors(page, preset: AuthPreset) -> dict:
    """Проверить селекторы пресета на странице."""
    results = {}

    # Проверяем селекторы авторизации
    auth_found = []
    for sel in preset.auth_selectors:
        try:
            count = await page.locator(sel).count()
            if count > 0:
                auth_found.append(sel)
        except Exception:
            pass
    results["auth_selectors"] = {
        "found": auth_found,
        "total": len(preset.auth_selectors),
    }

    # Проверяем поля формы
    form_fields = {
        "username": preset.username_selector,
        "password": preset.password_selector,
        "submit": preset.submit_selector,
    }
    for field_name, selector in form_fields.items():
        try:
            count = await page.locator(selector).count()
            results[f"{field_name}_field"] = {"found": count > 0, "count": count}
        except Exception as e:
            results[f"{field_name}_field"] = {"found": False, "error": str(e)}

    # Проверяем капчу
    if preset.captcha_selector:
        try:
            count = await page.locator(preset.captcha_selector).count()
            results["captcha"] = {"found": count > 0, "count": count}
        except Exception:
            results["captcha"] = {"found": False}

    return results


async def diagnose_platform(platform: str) -> dict:
    """Диагностика одной платформы."""
    preset = AUTH_PRESETS.get(platform)
    if not preset:
        return {"error": f"Платформа {platform} не найдена"}

    logger.info(f"Диагностика {platform}...")
    result = {
        "platform": platform,
        "login_url": preset.login_url,
        "auth_check_url": preset.auth_check_url,
        "login_page": None,
        "auth_check_page": None,
    }

    async with BrowserManager(headless=True, timeout=30000, stealth="standard") as browser:
        # Проверяем страницу логина
        page = await browser.new_page()
        try:
            await page.goto(preset.login_url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(3000)
            result["login_page"] = await check_selectors(page, preset)
            result["login_page"]["title"] = await page.title()
            result["login_page"]["url"] = page.url
        except Exception as e:
            result["login_page"] = {"error": str(e)}

        # Проверяем страницу проверки авторизации
        try:
            await page.goto(preset.auth_check_url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(3000)
            result["auth_check_page"] = await check_selectors(page, preset)
            result["auth_check_page"]["title"] = await page.title()
            result["auth_check_page"]["url"] = page.url
        except Exception as e:
            result["auth_check_page"] = {"error": str(e)}

    return result


async def main():
    platforms = sys.argv[1:] if len(sys.argv) > 1 else ["all"]

    if "all" in platforms:
        platforms = list(AUTH_PRESETS.keys())

    all_results = {}
    for platform in platforms:
        result = await diagnose_platform(platform)
        all_results[platform] = result

        # Краткий вывод
        print(f"\n{'='*60}")
        print(f"Платформа: {platform}")
        print(f"Login URL: {result.get('login_url', 'N/A')}")

        lp = result.get("login_page", {})
        if lp and "error" not in lp:
            print(f"  Страница логина: {lp.get('title', '?')} ({lp.get('url', '?')})")
            auth = lp.get("auth_selectors", {})
            print(f"  Селекторы авторизации: {len(auth.get('found', []))}/{auth.get('total', 0)} найдено")
            for field in ["username", "password", "submit"]:
                fdata = lp.get(f"{field}_field", {})
                status = "✅" if fdata.get("found") else "❌"
                print(f"  {status} поле {field}: {fdata.get('count', 0)} элементов")
            captcha = lp.get("captcha", {})
            if captcha.get("found"):
                print(f"  ⚠️ Капча обнаружена: {captcha.get('count', 0)} элементов")
        else:
            print(f"  ❌ Ошибка: {lp.get('error', 'unknown')}")

        ac = result.get("auth_check_page", {})
        if ac and "error" not in ac:
            print(f"  Страница проверки: {ac.get('title', '?')} ({ac.get('url', '?')})")
            auth = ac.get("auth_selectors", {})
            if auth.get("found"):
                print(f"  ✅ Авторизация обнаружена: {auth['found']}")
            else:
                print(f"  ❌ Авторизация не обнаружена (нужен логин)")

    # Сохранить полный отчёт
    report_path = Path("/tmp/diagnose_auth_report.json")
    report_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False, default=str))
    print(f"\nПолный отчёт: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
