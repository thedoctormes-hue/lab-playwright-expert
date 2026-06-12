#!/usr/bin/env python3
"""
Geo Check — проверка доступности сайтов через разные VPN-прокси.

Сравнивает HTTP-статус, заголовок, время загрузки, хеш контента
и делает скриншоты из каждой локации. Генерирует HTML-отчёт.

Запуск:
  python3 geo_check.py --url https://example.com
  python3 geo_check.py --url https://example.com --output /tmp/geo_report --compare
  python3 geo_check.py --url https://example.com --proxy poland
  python3 geo_check.py  # проверить все URL из дефолтного списка
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from loguru import logger

# Добавить src в path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.screenshot import ScreenshotMaker
from lab_playwright_kit.stealth import StealthConfig, apply_stealth
from lab_playwright_kit.vpn_proxy import VPNProxyManager


# Дефолтные URL для проверки
DEFAULT_URLS = [
    "https://www.google.com",
    "https://www.cloudflare.com",
]


async def check_url_through_proxy(
    url: str,
    proxy_name: str,
    proxy_config: dict | None,
    output_dir: Path,
    take_screenshots: bool = True,
) -> dict:
    """Проверить URL через конкретный прокси.

    Args:
        url: URL для проверки
        proxy_name: Имя прокси (poland, florida, direct)
        proxy_config: Конфиг прокси для Playwright или None
        output_dir: Директория для скриншотов
        take_screenshots: Делать ли скриншот

    Returns:
        Словарь с результатами проверки
    """
    result = {
        "proxy": proxy_name,
        "url": url,
        "timestamp": datetime.now().isoformat(),
        "status": "error",
        "status_code": None,
        "title": "",
        "load_time_ms": 0,
        "content_hash": None,
        "content_length": 0,
        "screenshot_path": None,
        "error": None,
    }

    start = time.monotonic()

    try:
        async with BrowserManager(
            headless=True,
            proxy=proxy_config,
            timeout=30000,
        ) as browser:
            page = await browser.new_page()
            await apply_stealth(page, StealthConfig.minimal())

            response = await page.goto(url, wait_until="domcontentloaded")
            elapsed_ms = (time.monotonic() - start) * 1000

            result["status_code"] = response.status if response else None
            result["load_time_ms"] = round(elapsed_ms, 2)
            result["title"] = await page.title()

            # Хеш контента
            content = await page.content()
            result["content_length"] = len(content)
            result["content_hash"] = hashlib.md5(content.encode()).hexdigest()

            # Скриншот
            if take_screenshots:
                maker = ScreenshotMaker(str(output_dir))
                safe_name = url.replace("https://", "").replace("http://", "").replace("/", "_")[:50]
                screenshot_name = f"geo_{proxy_name}_{safe_name}"
                result["screenshot_path"] = await maker.viewport(page, prefix=screenshot_name)

            # Определение статуса
            if result["status_code"] and 200 <= result["status_code"] < 400:
                result["status"] = "ok"
            elif result["status_code"]:
                result["status"] = "error"
                result["error"] = f"HTTP {result['status_code']}"
            else:
                result["status"] = "error"
                result["error"] = "No response"

            logger.info(
                f"[{proxy_name}] {url} → {result['status_code']} "
                f"({result['load_time_ms']:.0f}ms, {result['content_length']} bytes)"
            )

    except Exception as e:
        elapsed_ms = (time.monotonic() - start) * 1000
        result["load_time_ms"] = round(elapsed_ms, 2)
        result["status"] = "error"
        result["error"] = str(e)
        logger.error(f"[{proxy_name}] {url} → ERROR: {e}")

    return result


async def run_geo_check(
    urls: list[str],
    proxy_manager: VPNProxyManager,
    output_dir: Path,
    take_screenshots: bool = True,
    proxies_filter: list[str] | None = None,
) -> list[dict]:
    """Запустить проверку URL через все прокси.

    Args:
        urls: Список URL для проверки
        proxy_manager: VPNProxyManager с конфигурацией
        output_dir: Директория для скриншотов
        take_screenshots: Делать ли скриншоты
        proxies_filter: Список имён прокси (None = все)

    Returns:
        Список результатов
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Выбрать прокси
    if proxies_filter:
        proxies = []
        for name in proxies_filter:
            p = proxy_manager.get(name)
            if p:
                proxies.append(p)
            else:
                logger.warning(f"Proxy '{name}' not found, skipping")
    else:
        proxies = proxy_manager.list_all()

    logger.info(f"Geo check: {len(urls)} URLs × {len(proxies)} proxies")

    tasks = []
    for url in urls:
        for proxy in proxies:
            proxy_config = proxy.to_playwright_format()
            tasks.append(check_url_through_proxy(
                url=url,
                proxy_name=proxy.name,
                proxy_config=proxy_config,
                output_dir=output_dir,
                take_screenshots=take_screenshots,
            ))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    processed = []
    for r in results:
        if isinstance(r, Exception):
            processed.append({
                "proxy": "unknown",
                "url": "unknown",
                "status": "error",
                "error": str(r),
            })
        else:
            processed.append(r)

    return results


def generate_html_report(
    results: list[dict],
    output_dir: Path,
    compare: bool = False,
) -> Path:
    """Сгенерировать HTML-отчёт сравнения.

    Args:
        results: Список результатов проверки
        output_dir: Директория для отчёта
        compare: Сравнить результаты между прокси

    Returns:
        Путь к HTML-файлу
    """
    report_path = output_dir / "geo_report.html"

    # Группировка по URL
    by_url: dict[str, list[dict]] = {}
    for r in results:
        url = r.get("url", "unknown")
        by_url.setdefault(url, []).append(r)

    # Сравнение хешей
    comparisons = {}
    if compare:
        for url, proxy_results in by_url.items():
            hashes = {
                r["proxy"]: r.get("content_hash")
                for r in proxy_results
                if r.get("content_hash")
            }
            unique_hashes = set(hashes.values())
            comparisons[url] = {
                "identical": len(unique_hashes) <= 1,
                "hashes": hashes,
            }

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Geo Check Report — {datetime.now().strftime("%Y-%m-%d %H:%M")}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 20px; background: #f5f5f5; }}
        h1 {{ color: #333; }}
        h2 {{ color: #555; border-bottom: 2px solid #ddd; padding-bottom: 8px; }}
        .url-group {{ background: white; border-radius: 8px; padding: 16px; margin: 16px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        table {{ width: 100%; border-collapse: collapse; margin: 12px 0; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        .status-ok {{ color: #28a745; font-weight: 600; }}
        .status-error {{ color: #dc3545; font-weight: 600; }}
        .comparison {{ padding: 8px 12px; border-radius: 4px; margin: 8px 0; }}
        .comparison-identical {{ background: #d4edda; color: #155724; }}
        .comparison-different {{ background: #fff3cd; color: #856404; }}
        .screenshot {{ max-width: 400px; max-height: 300px; border: 1px solid #ddd; border-radius: 4px; margin: 4px; }}
        .summary {{ display: flex; gap: 16px; margin: 16px 0; }}
        .summary-card {{ background: white; border-radius: 8px; padding: 16px; flex: 1; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .summary-card h3 {{ margin: 0 0 8px 0; color: #666; font-size: 14px; }}
        .summary-card .value {{ font-size: 24px; font-weight: 700; }}
    </style>
</head>
<body>
    <h1>🌍 Geo Check Report</h1>
    <p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>

    <div class="summary">
        <div class="summary-card">
            <h3>Total checks</h3>
            <div class="value">{len(results)}</div>
        </div>
        <div class="summary-card">
            <h3>OK</h3>
            <div class="value" style="color: #28a745;">{sum(1 for r in results if r.get("status") == "ok")}</div>
        </div>
        <div class="summary-card">
            <h3>Errors</h3>
            <div class="value" style="color: #dc3545;">{sum(1 for r in results if r.get("status") == "error")}</div>
        </div>
        <div class="summary-card">
            <h3>Avg load time</h3>
            <div class="value">{(
                sum(r.get("load_time_ms", 0) for r in results if r.get("status") == "ok")
                / max(sum(1 for r in results if r.get("status") == "ok"), 1)
            ):.0f} ms</div>
        </div>
    </div>
"""

    for url, proxy_results in by_url.items():
        html += f'    <div class="url-group">\n'
        f'        <h2>🔗 {url}</h2>\n'

        # Сравнение
        if compare and url in comparisons:
            comp = comparisons[url]
            css_class = "comparison-identical" if comp["identical"] else "comparison-different"
            text = "✅ Content identical across all proxies" if comp["identical"] else "⚠️ Content differs between proxies"
            html += f'        <div class="comparison {css_class}">{text}</div>\n'

        html += """        <table>
            <tr><th>Proxy</th><th>Status</th><th>HTTP</th><th>Title</th>
                <th>Load time</th><th>Content</th><th>Hash</th><th>Screenshot</th></tr>
"""
        for r in proxy_results:
            status_css = "status-ok" if r.get("status") == "ok" else "status-error"
            screenshot_html = ""
            if r.get("screenshot_path"):
                screenshot_html = f'<img class="screenshot" src="{r["screenshot_path"]}">'
            html += f"""            <tr>
                <td><strong>{r.get("proxy", "?")}</strong></td>
                <td class="{status_css}">{r.get("status", "?")}</td>
                <td>{r.get("status_code", "—")}</td>
                <td>{r.get("title", "")[:60]}</td>
                <td>{r.get("load_time_ms", 0):.0f} ms</td>
                <td>{r.get("content_length", 0):,} B</td>
                <td><code>{r.get("content_hash", "—")[:12]}...</code></td>
                <td>{screenshot_html}</td>
            </tr>\n"""
        html += "        </table>\n    </div>\n"

    html += """</body>
</html>"""

    report_path.write_text(html, encoding="utf-8")
    logger.info(f"HTML report saved: {report_path}")
    return report_path


async def main():
    parser = argparse.ArgumentParser(
        description="Geo Check — проверка сайтов через VPN-прокси",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python3 geo_check.py --url https://example.com
  python3 geo_check.py --url https://example.com --output /tmp/geo --compare
  python3 geo_check.py --url https://example.com --proxy poland florida
  python3 geo_check.py  # проверить дефолтные URL
        """,
    )
    parser.add_argument(
        "--url", "-u",
        nargs="+",
        default=None,
        help="URL(ы) для проверки (по умолчанию: google.com, cloudflare.com)",
    )
    parser.add_argument(
        "--output", "-o",
        default="/tmp/geo_check",
        help="Директория для отчётов и скриншотов (по умолчанию: /tmp/geo_check)",
    )
    parser.add_argument(
        "--compare", "-c",
        action="store_true",
        help="Сравнить контент между прокси (хеши)",
    )
    parser.add_argument(
        "--proxy", "-p",
        nargs="+",
        default=None,
        help="Имена прокси для проверки (по умолчанию: все)",
    )
    parser.add_argument(
        "--no-screenshots",
        action="store_true",
        help="Не делать скриншоты",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Сохранить JSON-отчёт",
    )
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "config" / "vpn_proxies.yaml"),
        help="Путь к YAML-конфигурации прокси",
    )

    args = parser.parse_args()

    # Загрузить прокси
    config_path = Path(args.config)
    if config_path.exists():
        proxy_manager = VPNProxyManager.from_yaml(config_path)
    else:
        logger.warning(f"Config not found: {config_path}, using defaults")
        proxy_manager = VPNProxyManager()

    # URL для проверки
    urls = args.url if args.url else DEFAULT_URLS
    output_dir = Path(args.output)

    logger.info(f"Starting geo check: {len(urls)} URLs through {len(proxy_manager)} proxies")

    # Запуск проверки
    results = await run_geo_check(
        urls=urls,
        proxy_manager=proxy_manager,
        output_dir=output_dir,
        take_screenshots=not args.no_screenshots,
        proxies_filter=args.proxy,
    )

    # HTML-отчёт
    report_path = generate_html_report(results, output_dir, compare=args.compare)

    # JSON-отчёт
    if args.json:
        json_path = output_dir / "geo_report.json"
        json_path.write_text(
            json.dumps(results, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        logger.info(f"JSON report saved: {json_path}")

    # Итоги
    ok = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "ok")
    errors = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "error")
    logger.info(f"Geo check complete: {ok} OK, {errors} errors")
    logger.info(f"Report: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
