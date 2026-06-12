"""
Monitor Daemon — главный демон мониторинга Playwright-инфраструктуры.

Цикл:
  1. Собрать метрики из /metrics (screenshot-service)
  2. Запустить site_monitor для проверки сайтов
  3. Оценить правила алертов
  4. Отправить алерты в Telegram
  5. Обновить дашборд

Запуск:
  python3 monitor_daemon.py                  # однократный цикл
  python3 monitor_daemon.py --daemon         # бесконечный цикл
  python3 monitor_daemon.py --interval 300   # интервал (сек)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import httpx
from loguru import logger


# Пути
PROJECT_DIR = Path("/root/LabDoctorM/projects/lab-playwright-expert")
VENV_PYTHON = PROJECT_DIR / ".venv/bin/python3"
KIT_PATH = PROJECT_DIR / "src"
sys.path.insert(0, str(KIT_PATH))

from alert_manager import Severity, get_alert_manager


# Конфигурация
SCREENSHOT_SERVICE_URL = os.getenv("SCREENSHOT_SERVICE_URL", "http://localhost:8190")
TELEGRAM_BOT_TOKEN = os.getenv("MONITOR_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("MONITOR_CHAT_ID", "")
DEFAULT_INTERVAL = int(os.getenv("MONITOR_INTERVAL", "300"))  # 5 минут

# Файлы состояния
STATE_DIR = Path("/tmp/playwright_monitor")
STATE_DIR.mkdir(parents=True, exist_ok=True)
DASHBOARD_STATE = STATE_DIR / "dashboard_state.json"


# ─── Сбор метрик ──────────────────────────────────────────────────────────────

async def collect_metrics() -> dict:
    """Собрать все метрики из screenshot-service."""
    metrics = {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{SCREENSHOT_SERVICE_URL}/metrics")
            if resp.status_code == 200:
                for line in resp.text.split("\n"):
                    if line.startswith("#") or not line.strip():
                        continue
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].split("{")[0]
                        try:
                            value = float(parts[1])
                            metrics[key] = metrics.get(key, 0) + value
                        except ValueError:
                            pass
    except Exception as e:
        logger.error(f"Failed to collect metrics: {e}")
    return metrics


async def run_site_monitor() -> dict:
    """Запустить site_monitor и получить результаты."""
    report_file = STATE_DIR / "last_monitor_report.json"
    try:
        subprocess.run(
            [str(VENV_PYTHON), str(PROJECT_DIR / "scripts/site_monitor.py"), "--report"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if report_file.exists():
            return json.loads(report_file.read_text())
    except Exception as e:
        logger.error(f"Site monitor failed: {e}")
    return {}


# ─── Оценка алертов ───────────────────────────────────────────────────────────

def evaluate_alerts(metrics: dict, monitor_data: dict) -> list:
    """Оценить все правила алертов."""
    alert_mgr = get_alert_manager()
    triggered = []

    # Screenshot Service alerts
    total_requests = metrics.get("screenshot_requests_total", 0)
    error_requests = sum(
        v for k, v in metrics.items()
        if k.startswith("screenshot_requests_total") and "error" in k
    )
    error_rate = error_requests / total_requests if total_requests > 0 else 0

    alert = alert_mgr.evaluate("ScreenshotHighErrorRate", error_rate)
    if alert:
        triggered.append(alert)

    alert = alert_mgr.evaluate("ScreenshotTooManyBrowsers", metrics.get("screenshot_active_browsers", 0))
    if alert:
        triggered.append(alert)

    launch_errors = sum(
        v for k, v in metrics.items()
        if k.startswith("screenshot_browser_errors_total") and "launch" in k
    )
    alert = alert_mgr.evaluate("ScreenshotBrowserLaunchErrors", launch_errors)
    if alert:
        triggered.append(alert)

    # Cache hit rate
    cache_hits = metrics.get("screenshot_cache_hits_total", 0)
    cache_total = cache_hits + metrics.get("screenshot_cache_misses_total", 0)
    cache_rate = cache_hits / cache_total if cache_total > 0 else 1.0
    alert = alert_mgr.evaluate("ScreenshotLowCacheHitRate", cache_rate)
    if alert:
        triggered.append(alert)

    # Site Monitor alerts
    if monitor_data:
        error_count = monitor_data.get("error", 0)
        if error_count > 0:
            alert = alert_mgr.evaluate("SiteDown", error_count)
            if alert:
                triggered.append(alert)

        degraded_count = monitor_data.get("degraded", 0)
        if degraded_count > 0:
            alert = alert_mgr.evaluate("SiteDegraded", degraded_count)
            if alert:
                triggered.append(alert)

        # Visual diff
        for check in monitor_data.get("checks", []):
            diff = check.get("visual_diff_ratio", 0) or 0
            if diff > 0.10:
                alert = alert_mgr.evaluate("SiteVisualRegression", diff)
                if alert:
                    triggered.append(alert)

    # Stealth alerts
    stealth_score_val = metrics.get("stealth_overall_score_percent", 100)
    if stealth_score_val < 100:
        alert = alert_mgr.evaluate("StealthScoreLow", stealth_score_val)
        if alert:
            triggered.append(alert)

    # Health Monitor alerts
    hm_uptime = metrics.get("health_monitor_uptime_percent", 100)
    alert = alert_mgr.evaluate("ServiceLowUptime", hm_uptime)
    if alert:
        triggered.append(alert)

    return triggered


# ─── Уведомления ──────────────────────────────────────────────────────────────

async def send_alerts(alerts: list) -> None:
    """Отправить алерты в Telegram."""
    if not alerts or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    for alert in alerts:
        emoji = "🔴" if alert.severity == Severity.CRITICAL else "🟡"
        text = (
            f"{emoji} **Playwright Alert**\n"
            f"Rule: `{alert.rule_name}`\n"
            f"Severity: `{alert.severity}`\n"
            f"Value: `{alert.value:.2f}` (threshold: `{alert.threshold:.2f}`)\n"
            f"Time: `{alert.timestamp}`\n"
            f"\n{alert.message}"
        )

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                await client.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": TELEGRAM_CHAT_ID,
                        "text": text,
                        "parse_mode": "Markdown",
                    },
                )
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")


async def send_dashboard() -> None:
    """Отправить дашборд в Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    try:
        result = subprocess.run(
            [str(VENV_PYTHON), str(PROJECT_DIR / "scripts/telegram_dashboard.py")],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            text = result.stdout.strip()
            # Telegram limit = 4096 chars
            if len(text) > 4096:
                text = text[:4093] + "..."

            async with httpx.AsyncClient(timeout=15) as client:
                await client.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": TELEGRAM_CHAT_ID,
                        "text": text,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": True,
                    },
                )
    except Exception as e:
        logger.error(f"Failed to send dashboard: {e}")


# ─── Health отчёт ──────────────────────────────────────────────────────────────

def save_health_snapshot(metrics: dict, monitor_data: dict, alerts: list) -> None:
    """Сохранить снимок состояния."""
    snapshot = {
        "timestamp": datetime.utcnow().isoformat(),
        "metrics_summary": {
            "screenshot_requests": metrics.get("screenshot_requests_total", 0),
            "screenshot_errors": metrics.get("screenshot_browser_errors_total", 0),
            "active_browsers": metrics.get("screenshot_active_browsers", 0),
            "cache_hit_rate": _safe_rate(
                metrics.get("screenshot_cache_hits_total", 0),
                metrics.get("screenshot_cache_hits_total", 0) + metrics.get("screenshot_cache_misses_total", 0),
            ),
            "site_uptime": _compute_site_uptime(monitor_data),
            "stealth_score": metrics.get("stealth_overall_score_percent", 0),
            "health_uptime": metrics.get("health_monitor_uptime_percent", 100),
        },
        "alerts_count": len(alerts),
        "alerts_critical": sum(1 for a in alerts if a.severity == Severity.CRITICAL),
    }

    DASHBOARD_STATE.write_text(json.dumps(snapshot, indent=2, default=str))


def _safe_rate(num: float, den: float) -> float:
    return (num / den * 100) if den > 0 else 0


def _compute_site_uptime(monitor_data: dict) -> float:
    if not monitor_data:
        return 0
    total = monitor_data.get("total", 0)
    ok = monitor_data.get("ok", 0)
    return (ok / total * 100) if total > 0 else 0


# ─── Главный цикл ─────────────────────────────────────────────────────────────

async def run_cycle() -> dict:
    """Выполнить один цикл мониторинга."""
    logger.info("Starting monitoring cycle...")

    # 1. Собрать метрики
    metrics = await collect_metrics()
    logger.info(f"Collected {len(metrics)} metrics")

    # 2. Проверить сайты
    monitor_data = await run_site_monitor()
    logger.info(f"Site monitor: {monitor_data.get('ok', 0)}/{monitor_data.get('total', 0)} OK")

    # 3. Оценить алерты
    alerts = evaluate_alerts(metrics, monitor_data)
    if alerts:
        logger.warning(f"{len(alerts)} alerts triggered")
        await send_alerts(alerts)

    # 4. Сохранить снимок
    save_health_snapshot(metrics, monitor_data, alerts)

    return {
        "metrics_count": len(metrics),
        "sites_ok": monitor_data.get("ok", 0),
        "sites_total": monitor_data.get("total", 0),
        "alerts": len(alerts),
    }


async def run_daemon(interval: int = DEFAULT_INTERVAL):
    """Запуск в режиме демона."""
    logger.info(f"Monitor daemon started — interval={interval}s")

    cycle_count = 0
    while True:
        try:
            result = await run_cycle()
            cycle_count += 1
            logger.info(f"Cycle #{cycle_count} complete: {result}")

            # Каждые 12 циклов (1 час при 5мин) — отправить дашборд
            if cycle_count % 12 == 0:
                await send_dashboard()

        except Exception as e:
            logger.error(f"Monitor cycle failed: {e}")

        await asyncio.sleep(interval)


async def main():
    parser = argparse.ArgumentParser(description="Playwright Monitor Daemon")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help="Check interval (seconds)")
    parser.add_argument("--send-dashboard", action="store_true", help="Send dashboard to Telegram")
    args = parser.parse_args()

    if args.send_dashboard:
        await send_dashboard()
        return

    if args.daemon:
        await run_daemon(args.interval)
    else:
        result = await run_cycle()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
