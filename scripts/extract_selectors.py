#!/usr/bin/env python3
"""
Извлечение актуальных селекторов с реальных сайтов (v2).

Использует networkidle для SPA-сайтов, анализирует DOM после полной загрузки.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.browser_auth import AUTH_PRESETS


async def extract_selectors(url: str, wait_selector: str = "", extra_wait: float = 5.0) -> dict:
    """Извлечь селекторы со страницы после полной загрузки."""
    result = {
        "url": url,
        "title": "",
        "final_url": "",
        "forms": [],
        "inputs": [],
        "buttons": [],
        "auth_indicators": [],
    }

    async with BrowserManager(headless=True, timeout=30000) as browser:
        page = await browser.new_page()

        # Ждём networkidle для SPA
        try:
            await page.goto(url, wait_until="networkidle", timeout=20000)
        except Exception:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)

        # Дополнительное ожидание для динамического контента
        await page.wait_for_timeout(extra_wait * 1000)

        # Если указан селектор — ждём его
        if wait_selector:
            try:
                await page.wait_for_selector(wait_selector, timeout=10000)
            except Exception:
                pass

        result["title"] = await page.title()
        result["final_url"] = page.url

        # Анализируем все input-ы
        all_inputs = await page.query_selector_all("input")
        for inp in all_inputs:
            inp_type = await inp.get_attribute("type")
            if inp_type in ("hidden",):
                continue
            inp_info = {
                "type": inp_type,
                "name": await inp.get_attribute("name"),
                "id": await inp.get_attribute("id"),
                "placeholder": await inp.get_attribute("placeholder"),
                "class": (await inp.get_attribute("class") or "")[:100],
                "autocomplete": await inp.get_attribute("autocomplete"),
                "aria-label": await inp.get_attribute("aria-label"),
                "data-testid": await inp.get_attribute("data-testid"),
            }
            result["inputs"].append(inp_info)

        # Анализируем все кнопки
        all_buttons = await page.query_selector_all("button, [role='button'], input[type='submit']")
        for btn in all_buttons[:30]:
            text = (await btn.inner_text())[:60].strip()
            btn_info = {
                "text": text,
                "type": await btn.get_attribute("type"),
                "class": (await btn.get_attribute("class") or "")[:100],
                "id": await btn.get_attribute("id"),
                "data-testid": await btn.get_attribute("data-testid"),
            }
            result["buttons"].append(btn_info)

        # Ищем элементы авторизации (аватар, меню пользователя)
        auth_patterns = [
            ".avatar", ".user-menu", ".user-panel", ".user_login",
            "[data-testid='user-menu']", "[data-testid='SideNav_AccountSwitcher_Button']",
            ".chat-list", ".sidebar-header", "[class*='chatlist']",
            "a[href*='editor']", "a[href*='write']",
        ]
        for pattern in auth_patterns:
            try:
                elements = await page.query_selector_all(pattern)
                if elements:
                    result["auth_indicators"].append({
                        "selector": pattern,
                        "count": len(elements),
                    })
            except Exception:
                pass

    return result


async def main():
    platforms = sys.argv[1:] if len(sys.argv) > 1 else ["habr"]

    for platform in platforms:
        preset = AUTH_PRESETS.get(platform)
        if not preset:
            print(f"❌ Платформа {platform} не найдена")
            continue

        print(f"\n{'='*60}")
        print(f"Анализ: {platform}")
        print(f"{'='*60}")

        # Для Habr — ждём форму авторизации
        wait_sel = ""
        if platform == "habr":
            wait_sel = "input[type='email'], input[name='email']"
            # Habr может редиректить на главную если уже авторизован
            url = preset.login_url
        elif platform == "vcru":
            # VC.ru открывает модалку
            url = "https://vc.ru/?modal=auth"
            wait_sel = "input[type='email'], input[name='email']"
        elif platform in ("twitter", "x"):
            url = "https://x.com/i/flow/login"
            wait_sel = "input[autocomplete='username']"
        elif platform == "telegram":
            url = "https://web.telegram.org/"
            wait_sel = "input[type='tel'], input[name='phone_number']"
        else:
            url = preset.login_url

        result = await extract_selectors(url, wait_selector=wait_sel, extra_wait=5.0)

        print(f"\nСтраница: {result['title']}")
        print(f"URL: {result['final_url']}")

        print(f"\n--- Input-ы ({len(result['inputs'])}) ---")
        for inp in result["inputs"]:
            if not any([inp["name"], inp["id"], inp["placeholder"], inp["autocomplete"]]):
                continue
            parts = []
            if inp["type"]: parts.append(f"type={inp['type']}")
            if inp["name"]: parts.append(f"name={inp['name']}")
            if inp["id"]: parts.append(f"id={inp['id']}")
            if inp["placeholder"]: parts.append(f"placeholder={inp['placeholder']}")
            if inp["autocomplete"]: parts.append(f"autocomplete={inp['autocomplete']}")
            if inp["aria-label"]: parts.append(f"aria-label={inp['aria-label']}")
            if inp["data-testid"]: parts.append(f"data-testid={inp['data-testid']}")
            print(f"  {', '.join(parts)}")
            if inp["class"]:
                print(f"    class: {inp['class']}")

        print(f"\n--- Кнопки ({len(result['buttons'])}) ---")
        for btn in result["buttons"]:
            if not btn["text"] and not btn["data-testid"]:
                continue
            parts = []
            if btn["text"]: parts.append(f"text='{btn['text'][:40]}'")
            if btn["type"]: parts.append(f"type={btn['type']}")
            if btn["data-testid"]: parts.append(f"data-testid={btn['data-testid']}")
            print(f"  {', '.join(parts)}")
            if btn["class"]:
                print(f"    class: {btn['class']}")

        if result["auth_indicators"]:
            print(f"\n--- Индикаторы авторизации ---")
            for ai in result["auth_indicators"]:
                print(f"  ✅ {ai['selector']} ({ai['count']} элементов)")

        # Сохранить
        report_path = Path(f"/tmp/selectors_{platform}.json")
        report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        print(f"\nПолный отчёт: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
