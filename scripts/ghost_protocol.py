from __future__ import annotations


"""
Operation Ghost Protocol - boevoy stress-test vseka steka Lab Playwright Kit.

Faza 1: Stealth Recon - razvedka antibot-system na 50+ saytakh
Faza 2: Full Stack Attack - massovaya ataka s raznymi profilami povedeniya
Faza 3: Anti-Anti-Bot - analiz detektsii nashikh skriptov
Faza 4: Battle Report - HTML otchyot s grafikami
"""
import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from loguru import logger


BATTLE_DIR = Path("/tmp/ghost_protocol")
SCREENSHOTS_DIR = BATTLE_DIR / "screenshots"
REPORTS_DIR = BATTLE_DIR / "reports"

RECON_TARGETS = [
    {"url": "https://bot.sannysoft.com", "name": "sannysoft", "protection": "none"},
    {"url": "https://browserleaks.com/canvas", "name": "browserleaks_canvas", "protection": "none"},
    {"url": "https://browserleaks.com/webgl", "name": "browserleaks_webgl", "protection": "none"},
    {"url": "https://browserleaks.com/webrtc", "name": "browserleaks_webrtc", "protection": "none"},
    {"url": "https://abrahamjuliot.github.io/creepjs/", "name": "creepjs", "protection": "none"},
    {"url": "https://coveryourtracks.eff.org", "name": "eff_coveryourtracks", "protection": "none"},
    {"url": "https://www.deviceinfo.me", "name": "deviceinfo", "protection": "none"},
    {"url": "https://recaptcha-demo.appspot.com/", "name": "recaptcha_demo", "protection": "recaptcha"},
    {"url": "https://www.cloudflare.com", "name": "cloudflare", "protection": "cloudflare"},
    {"url": "https://www.kickstarter.com", "name": "kickstarter", "protection": "cloudflare"},
    {"url": "https://www.discord.com", "name": "discord", "protection": "cloudflare"},
    {"url": "https://www.ddos-guard.net", "name": "ddosguard", "protection": "ddosguard"},
    {"url": "https://yandex.ru", "name": "yandex", "protection": "yandex"},
    {"url": "https://mail.ru", "name": "mailru", "protection": "mailru"},
    {"url": "https://vk.com", "name": "vk", "protection": "vk"},
    {"url": "https://habr.com", "name": "habr", "protection": "cloudflare"},
    {"url": "https://vc.ru", "name": "vcru", "protection": "vcru"},
    {"url": "https://www.google.com", "name": "google", "protection": "google"},
    {"url": "https://www.github.com", "name": "github", "protection": "github"},
    {"url": "https://www.wikipedia.org", "name": "wikipedia", "protection": "none"},
    {"url": "https://www.reddit.com", "name": "reddit", "protection": "reddit"},
    {"url": "https://www.twitter.com", "name": "twitter", "protection": "twitter"},
    {"url": "https://www.linkedin.com", "name": "linkedin", "protection": "linkedin"},
    {"url": "https://www.facebook.com", "name": "facebook", "protection": "facebook"},
    {"url": "https://www.amazon.com", "name": "amazon", "protection": "amazon"},
    {"url": "https://www.netflix.com", "name": "netflix", "protection": "netflix"},
    {"url": "https://www.drugs.com", "name": "drugs_com", "protection": "cloudflare"},
    {"url": "https://www.webmd.com", "name": "webmd", "protection": "webmd"},
    {"url": "https://pubmed.ncbi.nlm.nih.gov", "name": "pubmed", "protection": "none"},
    {"url": "https://clinicaltrials.gov", "name": "clinicaltrials", "protection": "none"},
    {"url": "https://www.rxlist.com", "name": "rxlist", "protection": "cloudflare"},
    {"url": "https://www.pharmacychecker.com", "name": "pharmacychecker", "protection": "cloudflare"},
    {"url": "https://www.medscape.com", "name": "medscape", "protection": "medscape"},
    {"url": "https://www.gov.uk", "name": "govuk", "protection": "govuk"},
    {"url": "https://www.usa.gov", "name": "usagov", "protection": "usagov"},
    {"url": "https://rosminzdrav.ru", "name": "rosminzdrav", "protection": "ru_gov"},
    {"url": "https://www.ebay.com", "name": "ebay", "protection": "ebay"},
    {"url": "https://www.aliexpress.com", "name": "aliexpress", "protection": "aliexpress"},
    {"url": "https://www.wildberries.ru", "name": "wildberries", "protection": "wildberries"},
    {"url": "https://www.ozon.ru", "name": "ozon", "protection": "ozon"},
    {"url": "https://www.binance.com", "name": "binance", "protection": "binance"},
    {"url": "https://www.coinbase.com", "name": "coinbase", "protection": "coinbase"},
    {"url": "https://www.bbc.com", "name": "bbc", "protection": "bbc"},
    {"url": "https://www.cnn.com", "name": "cnn", "protection": "cnn"},
    {"url": "https://www.meduza.io", "name": "meduza", "protection": "meduza"},
    {"url": "https://stackoverflow.com", "name": "stackoverflow", "protection": "cloudflare"},
    {"url": "https://www.producthunt.com", "name": "producthunt", "protection": "cloudflare"},
    {"url": "https://news.ycombinator.com", "name": "hackernews", "protection": "none"},
    {"url": "https://www.aruljohn.com/webgl/", "name": "aruljohn_webgl", "protection": "none"},
    {"url": "https://jsfiddle.net/6L7q8p0v/", "name": "jsfiddle", "protection": "none"},
]

BEHAVIORAL_PROFILES = [
    {"name": "chrome_win", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36", "viewport": {"width": 1920, "height": 1080}, "platform": "Win32", "language": "ru-RU"},
    {"name": "chrome_mac", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36", "viewport": {"width": 2560, "height": 1440}, "platform": "MacIntel", "language": "en-US"},
    {"name": "firefox_win", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0", "viewport": {"width": 1366, "height": 768}, "platform": "Win32", "language": "ru-RU"},
    {"name": "safari_iphone", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1", "viewport": {"width": 390, "height": 844}, "platform": "iPhone", "language": "ru-RU"},
    {"name": "chrome_android", "ua": "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36", "viewport": {"width": 412, "height": 915}, "platform": "Linux armv8l", "language": "ru-RU"},
    {"name": "edge_win", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0", "viewport": {"width": 1536, "height": 864}, "platform": "Win32", "language": "en-US"},
    {"name": "chrome_linux", "ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36", "viewport": {"width": 1920, "height": 1080}, "platform": "Linux x86_64", "language": "en-US"},
    {"name": "safari_mac", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15", "viewport": {"width": 1680, "height": 1050}, "platform": "MacIntel", "language": "en-US"},
    {"name": "firefox_mac", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0", "viewport": {"width": 1440, "height": 900}, "platform": "MacIntel", "language": "en-US"},
    {"name": "firefox_linux", "ua": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0", "viewport": {"width": 1920, "height": 1080}, "platform": "Linux x86_64", "language": "en-US"},
]

TIMEZONES = [
    "Europe/Moscow", "Europe/Kiev", "Europe/Berlin", "Europe/London",
    "America/New_York", "America/Los_Angeles", "America/Chicago",
    "Asia/Tokyo", "Asia/Shanghai", "Asia/Dubai",
    "Australia/Sydney", "Pacific/Auckland",
]


@dataclass
class ReconResult:
    url: str
    name: str
    protection: str
    status: str = "pending"
    status_code: int | None = None
    load_time_ms: float = 0.0
    title: str = ""
    screenshot_path: str = ""
    stealth_score: int = 0
    blocked_signals: list[str] = field(default_factory=list)
    detected_signals: list[str] = field(default_factory=list)
    error: str = ""
    timestamp: str = ""


@dataclass
class AttackResult:
    session_id: int
    profile_name: str
    target_name: str
    target_url: str
    status: str = "pending"
    load_time_ms: float = 0.0
    screenshot_ok: bool = False
    parse_ok: bool = False
    har_entries: int = 0
    page_title: str = ""
    error: str = ""
    timestamp: str = ""


async def phase1_recon(max_concurrent: int = 3) -> list[ReconResult]:
    from lab_playwright_kit import BrowserManager, ScreenshotMaker

    logger.info(f"=== PHASE 1: STEALTH RECON -- {len(RECON_TARGETS)} targets ===")

    results: list[ReconResult] = []
    semaphore = asyncio.Semaphore(max_concurrent)

    async def scan_target(target: dict) -> ReconResult:
        async with semaphore:
            result = ReconResult(
                url=target["url"],
                name=target["name"],
                protection=target["protection"],
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            try:
                async with BrowserManager(headless=True) as browser:
                    profile = random.choice(BEHAVIORAL_PROFILES)
                    page = await browser.new_page()
                    await page.set_viewport_size(profile["viewport"])
                    await page.set_extra_http_headers({"Accept-Language": profile["language"]})

                    t0 = time.monotonic()
                    response = await page.goto(target["url"], wait_until="domcontentloaded", timeout=20000)
                    result.load_time_ms = (time.monotonic() - t0) * 1000
                    result.status_code = response.status if response else None
                    result.title = (await page.title())[:100]

                    content = (await page.content()).lower()
                    block_indicators = [
                        "access denied", "blocked", "captcha", "challenge",
                        "please verify", "are you a robot", "ddos-guard",
                        "checking your browser", "just a moment", "ray id",
                        "access forbidden", "403 forbidden", "bot detected",
                    ]
                    for indicator in block_indicators:
                        if indicator in content or indicator in result.title.lower():
                            result.blocked_signals.append(indicator)

                    if result.status_code and result.status_code >= 400:
                        result.status = "error"
                    elif len(result.blocked_signals) >= 3:
                        result.status = "blocked"
                    else:
                        result.status = "success"

                    maker = ScreenshotMaker(str(SCREENSHOTS_DIR))
                    try:
                        ss_path = await maker.full_page(page, f"recon_{target['name']}.png")
                        result.screenshot_path = str(ss_path)
                    except Exception:
                        pass

                    if any(k in target["name"] for k in ["sannysoft", "browserleaks", "creepjs", "deviceinfo"]):
                        try:
                            wd = await page.evaluate("() => navigator.webdriver")
                            result.detected_signals.append(f"webdriver:{wd}")
                            pl = await page.evaluate("() => navigator.plugins.length")
                            result.detected_signals.append(f"plugins:{pl}")
                            pf = await page.evaluate("() => navigator.platform")
                            result.detected_signals.append(f"platform:{pf}")
                        except Exception:
                            pass

                    await page.close()

            except asyncio.TimeoutError:
                result.status = "timeout"
                result.error = "20s timeout"
            except Exception as e:
                result.status = "error"
                result.error = str(e)[:200]

            emoji = {"success": "[OK]", "blocked": "[BLOCKED]", "error": "[ERR]", "timeout": "[TIMEOUT]"}.get(result.status, "[?]")
            logger.info(f"  {emoji} {result.name:30s} | {result.status:8s} | {result.load_time_ms:,.0f}ms | signals={len(result.blocked_signals)}")
            return result

    tasks = [asyncio.wait_for(scan_target(t), timeout=60) for t in RECON_TARGETS]
    raw = await asyncio.gather(*tasks, return_exceptions=True)

    for i, r in enumerate(raw):
        if isinstance(r, Exception):
            results.append(ReconResult(
                url=RECON_TARGETS[i]["url"], name=RECON_TARGETS[i]["name"],
                protection=RECON_TARGETS[i]["protection"], status="error", error=str(r)[:200],
            ))
        else:
            results.append(r)

    success = sum(1 for r in results if r.status == "success")
    blocked = sum(1 for r in results if r.status == "blocked")
    errors = sum(1 for r in results if r.status in ("error", "timeout"))
    logger.info(f"=== RECON DONE: {success} passed, {blocked} blocked, {errors} errors ===")
    return results


async def phase2_attack(sessions_per_target: int = 3, max_concurrent: int = 5) -> list[AttackResult]:
    from lab_playwright_kit import BrowserManager, PageParser, ScreenshotMaker
    from lab_playwright_kit.stealth import StealthConfig, apply_stealth

    attack_targets = [
        t for t in RECON_TARGETS
        if t["protection"] in ("none", "cloudflare", "yandex", "mailru", "habr", "vcru", "google", "wikipedia", "hackernews", "pubmed", "stackoverflow")
    ][:12]

    total = len(attack_targets) * sessions_per_target
    logger.info(f"=== PHASE 2: FULL STACK ATTACK -- {len(attack_targets)} targets x {sessions_per_target} = {total} sessions ===")

    results: list[AttackResult] = []
    semaphore = asyncio.Semaphore(max_concurrent)

    async def attack_session(target: dict, profile: dict, sid: int) -> AttackResult:
        async with semaphore:
            result = AttackResult(
                session_id=sid, profile_name=profile["name"],
                target_name=target["name"], target_url=target["url"],
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            try:
                async with BrowserManager(headless=True, viewport=profile["viewport"]) as browser:
                    page = await browser.new_page()
                    await page.set_extra_http_headers({"Accept-Language": profile["language"]})
                    try:
                        await apply_stealth(page, StealthConfig.full())
                    except Exception:
                        pass

                    t0 = time.monotonic()
                    await page.goto(target["url"], wait_until="domcontentloaded", timeout=20000)
                    result.load_time_ms = (time.monotonic() - t0) * 1000
                    result.page_title = (await page.title())[:100]

                    maker = ScreenshotMaker(str(SCREENSHOTS_DIR))
                    try:
                        await maker.viewport(page, f"attack_{sid:04d}_{target['name']}.png")
                        result.screenshot_ok = True
                    except Exception:
                        pass

                    try:
                        parser = PageParser(page)
                        data = parser.extract_article()
                        result.parse_ok = bool(data.get("title") or data.get("text"))
                    except Exception:
                        pass

                    try:
                        entries = await page.evaluate("() => performance.getEntriesByType('resource').length")
                        result.har_entries = entries or 0
                    except Exception:
                        pass

                    try:
                        await page.evaluate(f"window.scrollBy(0, {random.randint(100, 500)})")
                        await asyncio.sleep(random.uniform(0.3, 1.0))
                    except Exception:
                        pass

                    result.status = "success"
                    await page.close()

            except asyncio.TimeoutError:
                result.status = "timeout"
            except Exception as e:
                result.status = "error"
                result.error = str(e)[:200]
            return result

    all_tasks = []
    sid = 0
    for target in attack_targets:
        for _ in range(sessions_per_target):
            profile = random.choice(BEHAVIORAL_PROFILES)
            sid += 1
            all_tasks.append(attack_session(target, profile, sid))

    raw = await asyncio.gather(*all_tasks, return_exceptions=True)
    for i, r in enumerate(raw):
        if isinstance(r, Exception):
            results.append(AttackResult(
                session_id=i + 1, profile_name="unknown", target_name="unknown",
                target_url="", status="error", error=str(r)[:200],
            ))
        else:
            results.append(r)

    success = sum(1 for r in results if r.status == "success")
    blocked = sum(1 for r in results if r.status == "blocked")
    errors = sum(1 for r in results if r.status in ("error", "timeout"))
    avg_load = statistics.mean([r.load_time_ms for r in results if r.load_time_ms > 0]) if any(r.load_time_ms > 0 for r in results) else 0
    screenshots = sum(1 for r in results if r.screenshot_ok)
    parsed = sum(1 for r in results if r.parse_ok)
    logger.info(f"=== ATTACK DONE: {success} ok, {blocked} blocked, {errors} errors ===")
    logger.info(f"   Screenshots: {screenshots}/{len(results)} | Parse: {parsed}/{len(results)} | Avg load: {avg_load:,.0f}ms")
    return results


def phase3_analyze(recon: list[ReconResult], attack: list[AttackResult]) -> dict:
    logger.info("=== PHASE 3: ANTI-ANTI-BOT ANALYSIS ===")
    analysis: dict = {
        "recon": {
            "total": len(recon),
            "success": sum(1 for r in recon if r.status == "success"),
            "blocked": sum(1 for r in recon if r.status == "blocked"),
            "errors": sum(1 for r in recon if r.status in ("error", "timeout")),
            "avg_load_ms": statistics.mean([r.load_time_ms for r in recon if r.load_time_ms > 0]) if any(r.load_time_ms > 0 for r in recon) else 0,
            "by_protection": {},
            "most_detecting": [],
            "fastest": [],
        },
        "attack": {
            "total": len(attack),
            "success": sum(1 for r in attack if r.status == "success"),
            "blocked": sum(1 for r in attack if r.status == "blocked"),
            "errors": sum(1 for r in attack if r.status in ("error", "timeout")),
            "screenshots": sum(1 for r in attack if r.screenshot_ok),
            "parsed": sum(1 for r in attack if r.parse_ok),
            "avg_load_ms": statistics.mean([r.load_time_ms for r in attack if r.load_time_ms > 0]) if any(r.load_time_ms > 0 for r in attack) else 0,
            "by_profile": {},
            "by_target": {},
        },
        "stealth_effectiveness": 0.0,
        "recommendations": [],
    }

    pstats: dict = {}
    for r in recon:
        p = r.protection
        pstats.setdefault(p, {"total": 0, "success": 0, "blocked": 0})
        pstats[p]["total"] += 1
        if r.status == "success":
            pstats[p]["success"] += 1
        elif r.status == "blocked":
            pstats[p]["blocked"] += 1
    analysis["recon"]["by_protection"] = pstats

    detecting = sorted([(r.name, r.blocked_signals) for r in recon if r.blocked_signals], key=lambda x: len(x[1]), reverse=True)
    analysis["most_detecting"] = detecting[:10]

    fast = sorted([r for r in recon if r.load_time_ms > 0], key=lambda r: r.load_time_ms)
    analysis["fastest"] = [(r.name, round(r.load_time_ms)) for r in fast[:10]]

    profstats: dict = {}
    for r in attack:
        p = r.profile_name
        profstats.setdefault(p, {"total": 0, "success": 0, "loads": []})
        profstats[p]["total"] += 1
        if r.status == "success":
            profstats[p]["success"] += 1
        if r.load_time_ms > 0:
            profstats[p]["loads"].append(r.load_time_ms)
    for p in profstats:
        loads = profstats[p]["loads"]
        profstats[p]["avg_load_ms"] = round(statistics.mean(loads)) if loads else 0
        del profstats[p]["loads"]
    analysis["attack"]["by_profile"] = profstats

    tstats: dict = {}
    for r in attack:
        t = r.target_name
        tstats.setdefault(t, {"total": 0, "success": 0, "screenshots": 0, "parsed": 0})
        tstats[t]["total"] += 1
        if r.status == "success":
            tstats[t]["success"] += 1
        if r.screenshot_ok:
            tstats[t]["screenshots"] += 1
        if r.parse_ok:
            tstats[t]["parsed"] += 1
    analysis["attack"]["by_target"] = tstats

    total = len(attack)
    ok = analysis["attack"]["success"]
    analysis["stealth_effectiveness"] = round(ok / total * 100, 1) if total > 0 else 0

    eff = analysis["stealth_effectiveness"]
    if eff >= 80:
        analysis["recommendations"].append("[EXCELLENT] Stealth effectiveness > 80%. Battle ready.")
    elif eff >= 50:
        analysis["recommendations"].append("[WARNING] Stealth effectiveness < 80%. Needs improvement.")
    else:
        analysis["recommendations"].append("[CRITICAL] Stealth effectiveness < 50%. Major overhaul needed.")

    for p, s in pstats.items():
        if s.get("blocked", 0) > s.get("success", 0):
            analysis["recommendations"].append(f"[DETECTED] Protection '{p}' blocks more than passes ({s['blocked']}/{s['total']})")

    logger.info(f"=== ANALYSIS: Stealth Effectiveness = {eff}% ===")
    for rec in analysis["recommendations"]:
        logger.info(f"  {rec}")
    return analysis


def _td(s: str) -> str:
    return f"<td>{s}</td>"


def _tr(*cells: str) -> str:
    return "<tr>" + "".join(_td(c) for c in cells) + "</tr>\n"


def phase4_report(recon, attack, analysis):
    import logging
    from datetime import datetime
    from pathlib import Path
    logger = logging.getLogger(__name__)
    logger.info("=== PHASE 4: BATTLE REPORT ===")
    REPORTS_DIR = Path("/tmp/ghost_protocol/reports")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / ("battle_report_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".html")

    rs = analysis["recon"]["success"]
    rb = analysis["recon"]["blocked"]
    rt = analysis["recon"]["total"]
    als = analysis["attack"]["success"]
    alt = analysis["attack"]["total"]
    eff = analysis["stealth_effectiveness"]
    eff_color = "#22c55e" if eff >= 80 else "#f59e0b" if eff >= 50 else "#ef4444"
    eff_label = "EXCELLENT" if eff >= 80 else "GOOD" if eff >= 50 else "POOR"
    now = datetime.now().strftime("%d.%m.%Y %H:%M:%S UTC")
    ss_count = analysis["attack"]["screenshots"]
    parse_count = analysis["attack"]["parsed"]

    # Build table rows
    recon_rows = []
    for r in recon:
        sc = {"success": "s-ok", "blocked": "s-blocked", "error": "s-err", "timeout": "s-timeout"}.get(r.status, "")
        signals = ", ".join(r.blocked_signals[:5]) if r.blocked_signals else "-"
        title = r.title[:50] if r.title else "-"
        recon_rows.append("<tr><td>" + r.name + "</td><td>" + r.protection + "</td><td class=\"" + sc + "\">" + r.status + "</td><td>" + str(int(r.load_time_ms)) + "</td><td>" + title + "</td><td>" + signals + "</td></tr>")

    profile_rows = []
    for pn, ps in sorted(analysis["attack"]["by_profile"].items()):
        pct = (ps["success"] / ps["total"] * 100) if ps["total"] > 0 else 0
        c = "#22c55e" if pct >= 80 else "#f59e0b" if pct >= 50 else "#ef4444"
        al = ps.get("avg_load_ms", 0)
        profile_rows.append("<tr><td>" + pn + "</td><td>" + str(ps["total"]) + "</td><td style=\"color:" + c + "\">" + str(ps["success"]) + "</td><td>" + str(int(pct)) + "%</td><td>" + str(int(al)) + "ms</td></tr>")

    target_rows = []
    for tn, ts in sorted(analysis["attack"]["by_target"].items(), key=lambda x: x[1]["success"], reverse=True):
        target_rows.append("<tr><td>" + tn + "</td><td>" + str(ts["total"]) + "</td><td>" + str(ts["success"]) + "</td><td>" + str(ts["screenshots"]) + "</td><td>" + str(ts["parsed"]) + "</td></tr>")

    prot_rows = []
    for pn, ps in sorted(analysis["recon"]["by_protection"].items(), key=lambda x: x[1].get("success", 0) / max(x[1]["total"], 1), reverse=True):
        pct = (ps["success"] / ps["total"] * 100) if ps["total"] > 0 else 0
        c = "#22c55e" if pct >= 80 else "#f59e0b" if pct >= 50 else "#ef4444"
        prot_rows.append("<tr><td>" + pn + "</td><td>" + str(ps["total"]) + "</td><td style=\"color:" + c + "\">" + str(ps["success"]) + "</td><td>" + str(ps.get("blocked", 0)) + "</td><td>" + str(int(pct)) + "%</td></tr>")

    recs = ""
    for r in analysis["recommendations"]:
        recs += "<li>" + r + "</li>"

    # Build HTML
    html = "<!DOCTYPE html>\n"
    html += "<html lang=\"ru\">\n"
    html += "<head><meta charset=\"UTF-8\"><title>Ghost Protocol - Battle Report</title>\n"
    html += "<style>\n"
    html += "body{font-family:sans-serif;background:#0a0a0f;color:#e0e0e0;padding:2rem;}\n"
    html += "h1{text-align:center;font-size:2rem;}\n"
    html += "table{width:100%;border-collapse:collapse;margin:1rem 0;}\n"
    html += "th,td{padding:0.5rem;border-bottom:1px solid #333;text-align:left;}\n"
    html += "th{background:#151520;color:#888;}\n"
    html += ".s-ok{color:#22c55e;}.s-blocked{color:#ef4444;}.s-err{color:#f59e0b;}\n"
    html += ".stats{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin:1rem 0;}\n"
    html += ".stat{background:#151520;padding:1rem;border-radius:8px;text-align:center;}\n"
    html += ".stat-value{font-size:2rem;font-weight:bold;}\n"
    html += ".eff{border:2px solid " + eff_color + ";}\n"
    html += "</style></head><body>\n"
    html += "<h1>GHOST PROTOCOL - Battle Report</h1>\n"
    html += "<p style=\"text-align:center;color:#888\">" + now + "</p>\n"
    html += "<div class=\"stats\">\n"
    html += "<div class=\"stat eff\"><div class=\"stat-value\" style=\"color:" + eff_color + "\">" + str(int(eff)) + "%</div><div>Stealth: " + eff_label + "</div></div>\n"
    html += "<div class=\"stat\"><div class=\"stat-value\" style=\"color:#22c55e\">" + str(rs) + "/" + str(rt) + "</div><div>Recon Passed</div></div>\n"
    html += "<div class=\"stat\"><div class=\"stat-value\" style=\"color:#ef4444\">" + str(rb) + "</div><div>Recon Blocked</div></div>\n"
    html += "<div class=\"stat\"><div class=\"stat-value\" style=\"color:#22c55e\">" + str(als) + "/" + str(alt) + "</div><div>Attack Success</div></div>\n"
    html += "<div class=\"stat\"><div class=\"stat-value\" style=\"color:#3b82f6\">" + str(ss_count) + "</div><div>Screenshots</div></div>\n"
    html += "<div class=\"stat\"><div class=\"stat-value\" style=\"color:#8b5cf6\">" + str(parse_count) + "</div><div>Parsed</div></div>\n"
    html += "</div>\n"
    html += "<h2>Recon Results</h2><table>\n"
    html += "<thead><tr><th>Site</th><th>Protection</th><th>Status</th><th>Load (ms)</th><th>Title</th><th>Signals</th></tr></thead>\n"
    html += "<tbody>" + "".join(recon_rows) + "</tbody></table>\n"
    html += "<h2>Attack by Profile</h2><table>\n"
    html += "<thead><tr><th>Profile</th><th>Total</th><th>Success</th><th>Rate</th><th>Avg Load</th></tr></thead>\n"
    html += "<tbody>" + "".join(profile_rows) + "</tbody></table>\n"
    html += "<h2>Attack by Target</h2><table>\n"
    html += "<thead><tr><th>Target</th><th>Attacks</th><th>Success</th><th>Screenshots</th><th>Parsed</th></tr></thead>\n"
    html += "<tbody>" + "".join(target_rows) + "</tbody></table>\n"
    html += "<h2>Protection Analysis</h2><table>\n"
    html += "<thead><tr><th>Protection</th><th>Targets</th><th>Passed</th><th>Blocked</th><th>Rate</th></tr></thead>\n"
    html += "<tbody>" + "".join(prot_rows) + "</tbody></table>\n"
    html += "<h2>Recommendations</h2><ul>" + recs + "</ul>\n"
    html += "<p style=\"text-align:center;color:#555;margin-top:2rem\">Lab Playwright Kit v1.0.0 - Operation Ghost Protocol - Lab DoctorM&Ai, 2026</p>\n"
    html += "</body></html>"

    report_path.write_text(html, encoding="utf-8")
    logger.info("=== REPORT: " + str(report_path) + " ===")
    return str(report_path)

async def run_ghost_protocol(phase: int | None = None):
    for d in [BATTLE_DIR, SCREENSHOTS_DIR, REPORTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    start = time.monotonic()
    recon_results: list[ReconResult] = []
    attack_results: list[AttackResult] = []
    analysis: dict = {}

    logger.info("=" * 60)
    logger.info("  OPERATION GHOST PROTOCOL")
    logger.info("  Lab Playwright Kit v1.0.0 - Battle Test")
    logger.info("=" * 60)

    if phase is None or phase == 1:
        recon_results = await phase1_recon(max_concurrent=3)
        data = [{"url": r.url, "name": r.name, "protection": r.protection, "status": r.status,
                 "load_time_ms": r.load_time_ms, "title": r.title, "blocked_signals": r.blocked_signals,
                 "detected_signals": r.detected_signals, "error": r.error} for r in recon_results]
        (BATTLE_DIR / "recon_results.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))

    if phase is None or phase == 2:
        attack_results = await phase2_attack(sessions_per_target=3, max_concurrent=5)
        data = [{"session_id": r.session_id, "profile": r.profile_name, "target": r.target_name,
                 "status": r.status, "load_time_ms": r.load_time_ms, "screenshot_ok": r.screenshot_ok,
                 "parse_ok": r.parse_ok, "har_entries": r.har_entries, "error": r.error} for r in attack_results]
        (BATTLE_DIR / "attack_results.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))

    if phase is None or phase == 3:
        if recon_results and attack_results:
            analysis = phase3_analyze(recon_results, attack_results)
            (BATTLE_DIR / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2, default=str))

    if phase is None or phase == 4:
        if analysis:
            report_path = phase4_report(recon_results, attack_results, analysis)
            logger.info(f"Report: file://{report_path}")

    duration = time.monotonic() - start
    logger.info(f"=== GHOST PROTOCOL COMPLETE in {duration:.1f}s ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Operation Ghost Protocol")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3, 4])
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    if args.report:
        rd = json.loads(Path("/tmp/ghost_protocol/recon_results.json").read_text())
        ad = json.loads(Path("/tmp/ghost_protocol/attack_results.json").read_text())
        an = json.loads(Path("/tmp/ghost_protocol/analysis.json").read_text())
        recon = [ReconResult(**{k: v for k, v in r.items() if k in ReconResult.__dataclass_fields__}) for r in rd]
        attack = [AttackResult(**{k: v for k, v in r.items() if k in AttackResult.__dataclass_fields__}) for r in ad]
        rp = phase4_report(recon, attack, an)
        print(f"Report: file://{rp}")
    else:
        asyncio.run(run_ghost_protocol(phase=args.phase))
