"""
Stealth Research Lab — исследование и тестирование обхода антибот-системы.

Проверяет уровень детектирования браузера на различных сервисах.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from loguru import logger

from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.metrics import STEALTH_OVERALL, STEALTH_SCORE, STEALTH_TESTS_RUN
from lab_playwright_kit.screenshot import ScreenshotMaker
from lab_playwright_kit.stealth import StealthConfig, apply_stealth


# ─── Тестовые эндпоинты ───────────────────────────────────────────────────────

STEALTH_TEST_URLS = {
    # Проверка webdriver
    "webdriver_js": {
        "url": "https://bot.sannysoft.com",
        "checks": ["navigator.webdriver"],
        "description": "SannySoft — полный тест детекта автоматизации",
    },
    # Проверка fingerprint
    "fingerprint": {
        "url": "https://browserleaks.com/canvas",
        "checks": ["canvas"],
        "description": "BrowserLeaks — Canvas fingerprint",
    },
    # Проверка headers
    "headers": {
        "url": "https://httpbin.org/headers",
        "checks": ["headers"],
        "description": "HTTPBin — проверка HTTP-заголовков",
    },
    # Cloudflare challenge
    "cloudflare": {
        "url": "https://www.cloudflare.com",
        "checks": ["title"],
        "description": "Cloudflare — проверка прохождения challenge",
    },
    # Проверка WebGL
    "webgl": {
        "url": "https://browserleaks.com/webgl",
        "checks": ["webgl"],
        "description": "BrowserLeaks — WebGL fingerprint",
    },
}


@dataclass
class StealthTestResult:
    """Результат одного stealth-теста."""
    test_name: str
    url: str
    timestamp: str
    passed: bool
    details: dict
    screenshot_path: str | None = None
    error: str | None = None


@dataclass
class StealthReport:
    """Полный отчёт по stealth-тестам."""
    timestamp: str
    total: int
    passed: int
    failed: int
    results: list[StealthTestResult] = field(default_factory=list)

    @property
    def score(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.passed) / len(self.results) * 100

    def summary(self) -> str:
        lines = [
            f"🔒 Stealth Report — {self.timestamp}",
            f"Score: {self.score:.0f}% ({self.passed}/{self.total})",
            "",
        ]
        for r in self.results:
            icon = "✅" if r.passed else "❌"
            lines.append(f"{icon} {r.test_name}: {r.url}")
            if r.error:
                lines.append(f"   → {r.error}")
        return "\n".join(lines)


async def test_webdriver_hidden(page) -> dict:
    """Проверить скрыт ли webdriver."""
    result = await page.evaluate("""
        () => ({
            webdriver: navigator.webdriver,
            webdriverValue: String(navigator.webdriver),
            automationControlled: navigator.automationControlled,
            chromeRuntime: !!window.chrome?.runtime,
            pluginsLength: navigator.plugins?.length,
            languages: navigator.languages,
        })
    """)
    return result


async def test_headers(page) -> dict:
    """Проверить HTTP-заголовки через httpbin."""
    await page.goto("https://httpbin.org/headers", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)
    try:
        pre = page.locator("pre").first
        text = await pre.inner_text()
        data = json.loads(text)
        return data.get("headers", {})
    except Exception as e:
        return {"error": str(e)}


async def test_canvas_fingerprint(page) -> dict:
    """Проверить Canvas fingerprint."""
    result = await page.evaluate("""
        () => {
            const canvas = document.createElement('canvas');
            canvas.width = 200;
            canvas.height = 50;
            const ctx = canvas.getContext('2d');
            ctx.textBaseline = 'top';
            ctx.font = '14px Arial';
            ctx.fillStyle = '#f60';
            ctx.fillRect(0, 0, 200, 50);
            ctx.fillStyle = '#069';
            ctx.fillText('Playwright stealth test', 2, 15);
            return {
                dataUrl: canvas.toDataURL().substring(0, 100),
                length: canvas.toDataURL().length,
            };
        }
    """)
    return result


async def test_webgl_fingerprint(page) -> dict:
    """Проверить WebGL fingerprint."""
    result = await page.evaluate("""
        () => {
            const canvas = document.createElement('canvas');
            const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
            if (!gl) return { supported: false };
            const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
            return {
                supported: true,
                vendor: gl.getParameter(debugInfo?.UNMASKED_VENDOR_WEBGL || gl.VENDOR),
                renderer: gl.getParameter(debugInfo?.UNMASKED_RENDERER_WEBGL || gl.RENDERER),
                version: gl.getParameter(gl.VERSION),
            };
        }
    """)
    return result


async def run_stealth_test(
    test_name: str,
    config: StealthConfig,
    headless: bool = True,
) -> StealthTestResult:
    """Запустить один stealth-тест."""
    test_info = STEALTH_TEST_URLS.get(test_name)
    if not test_info:
        return StealthTestResult(
            test_name=test_name,
            url="",
            timestamp=datetime.now().isoformat(),
            passed=False,
            details={},
            error=f"Unknown test: {test_name}",
        )

    url = test_info["url"]
    result = StealthTestResult(
        test_name=test_name,
        url=url,
        timestamp=datetime.now().isoformat(),
        passed=False,
        details={},
    )

    async with BrowserManager(headless=headless, timeout=30000) as browser:
        page = await browser.new_page()
        await apply_stealth(page, config)

        try:
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # Скриншот
            maker = ScreenshotMaker("/tmp/stealth_research")
            result.screenshot_path = await maker.viewport(
                page, prefix=f"stealth_{test_name}"
            )

            # Выполнить проверки
            details = {}

            if "webdriver" in test_info["checks"]:
                wd = await test_webdriver_hidden(page)
                details["webdriver"] = wd
                # webdriver должен быть undefined/None
                result.passed = wd.get("webdriver") is None or wd.get("webdriver") is False

            if "headers" in test_info["checks"]:
                headers = await test_headers(page)
                details["headers"] = headers
                # Проверить что нет подозрительных заголовков
                suspicious = ["HeadlessChrome", "PhantomJS", "Selenium", "Playwright"]
                user_agent = headers.get("User-Agent", "")
                result.passed = not any(s in user_agent for s in suspicious)

            if "canvas" in test_info["checks"]:
                canvas = await test_canvas_fingerprint(page)
                details["canvas"] = canvas
                result.passed = canvas.get("length", 0) > 100

            if "webgl" in test_info["checks"]:
                webgl = await test_webgl_fingerprint(page)
                details["webgl"] = webgl
                result.passed = webgl.get("supported", False)

            if "title" in test_info["checks"]:
                title = await page.title()
                details["title"] = title
                result.passed = "challenge" not in title.lower() and "blocked" not in title.lower()

            result.details = details

        except Exception as e:
            result.error = str(e)
            logger.error(f"Stealth test {test_name} failed: {e}")

    return result


async def run_all_stealth_tests(
    config: StealthConfig | None = None,
    headless: bool = True,
) -> StealthReport:
    """Запустить все stealth-тесты."""
    config = config or StealthConfig.full()
    report = StealthReport(
        timestamp=datetime.now().isoformat(),
        total=len(STEALTH_TEST_URLS),
        passed=0,
        failed=0,
    )

    for test_name in STEALTH_TEST_URLS:
        logger.info(f"Running stealth test: {test_name}...")
        result = await run_stealth_test(test_name, config, headless)
        report.results.append(result)
        if result.passed:
            report.passed += 1
        else:
            report.failed += 1

        # Записать в Prometheus метрики
        score = 100.0 if result.passed else 0.0
        STEALTH_SCORE.labels(test=test_name).set(score)
        STEALTH_TESTS_RUN.labels(test=test_name, result="pass" if result.passed else "fail").inc()

    # Общий stealth score
    STEALTH_OVERALL.set(report.score)

    return report


async def compare_stealth_levels() -> dict:
    """Сравнить разные уровни stealth (none, minimal, full)."""
    levels = {
        "none": StealthConfig(enabled=False),
        "minimal": StealthConfig.minimal(),
        "full": StealthConfig.full(),
    }

    results = {}
    for name, config in levels.items():
        logger.info(f"Testing stealth level: {name}...")
        report = await run_all_stealth_tests(config)
        results[name] = {
            "score": report.score,
            "passed": report.passed,
            "total": report.total,
        }

    return results


async def main():
    """CLI запуск stealth-исследований."""
    import argparse

    parser = argparse.ArgumentParser(description="Stealth Research Lab")
    parser.add_argument("--test", default=None, help="Конкретный тест")
    parser.add_argument("--compare", action="store_true", help="Сравнить уровни stealth")
    parser.add_argument("--no-headless", action="store_true", help="Показать браузер")

    args = parser.parse_args()

    if args.compare:
        results = await compare_stealth_levels()
        print("\n🔒 Stealth Level Comparison:")
        for level, data in results.items():
            print(f"  {level}: {data['score']:.0f}% ({data['passed']}/{data['total']})")
        return

    if args.test:
        config = StealthConfig.full()
        result = await run_stealth_test(args.test, config, headless=not args.no_headless)
        icon = "✅" if result.passed else "❌"
        print(f"{icon} {result.test_name}: {result.url}")
        print(f"   Details: {json.dumps(result.details, indent=2, default=str)[:500]}")
        return

    # Все тесты
    report = await run_all_stealth_tests(headless=not args.no_headless)
    print(report.summary())

    # Сохранить отчёт
    report_path = Path("/tmp/stealth_report.json")
    report_data = {
        "timestamp": report.timestamp,
        "score": report.score,
        "passed": report.passed,
        "failed": report.failed,
        "results": [
            {
                "test": r.test_name,
                "url": r.url,
                "passed": r.passed,
                "details": r.details,
                "error": r.error,
            }
            for r in report.results
        ],
    }
    report_path.write_text(json.dumps(report_data, indent=2, default=str))
    print(f"\nReport saved: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
