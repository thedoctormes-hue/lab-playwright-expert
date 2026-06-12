"""
Telegram Dashboard — текстовый дашборд Playwright-инфраструктуры для Telegram.

Формирует сводку метрик в формате, готовом для отправки в Telegram.
Поддерживает Markdown-разметку.

Использование:
  python3 telegram_dashboard.py                    # полный дашборд
  python3 telegram_dashboard.py --compact          # компактная версия
  python3 telegram_dashboard.py --component stealth # по компоненту
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx
from loguru import logger


# Пути
KIT_PATH = Path("/root/LabDoctorM/projects/lab-playwright-expert/src")
sys.path.insert(0, str(KIT_PATH))


# Конфигурация
SCREENSHOT_SERVICE_URL = "http://localhost:8190"
HEALTH_LOG = Path("/var/log/screenshot-service-health.jsonl")
STEALTH_REPORT = Path("/tmp/stealth_report.json")
MONITOR_REPORT = Path("/tmp/monitor_report.json")
ALERT_STATE = Path("/tmp/playwright_alerts_state.json")


# ─── Форматирование ───────────────────────────────────────────────────────────

def fmt_pct(value: float) -> str:
    """Форматировать процент с цветовым индикатором."""
    if value >= 95:
        return f"🟢 {value:.1f}%"
    elif value >= 80:
        return f"🟡 {value:.1f}%"
    else:
        return f"🔴 {value:.1f}%"


def fmt_time(seconds: float) -> str:
    """Форматировать время."""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    else:
        return f"{seconds/60:.1f}m"


def fmt_bytes(size: int) -> str:
    """Форматировать размер."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


# ─── Сбор метрик ──────────────────────────────────────────────────────────────

async def fetch_prometheus_metrics() -> dict:
    """Получить метрики из screenshot-service /metrics."""
    metrics = {}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{SCREENSHOT_SERVICE_URL}/metrics")
            if resp.status_code == 200:
                text = resp.text
                for line in text.split("\n"):
                    if line.startswith("#") or not line.strip():
                        continue
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].split("{")[0]  # убрать labels
                        try:
                            value = float(parts[1])
                            metrics[key] = metrics.get(key, 0) + value
                        except ValueError:
                            pass
    except Exception as e:
        logger.debug(f"Failed to fetch metrics: {e}")
    return metrics


def load_json_safe(path: Path) -> dict:
    """Безопасно загрузить JSON."""
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {}


# ─── Формирование дашборда ────────────────────────────────────────────────────

def build_dashboard(
    metrics: dict,
    health_data: dict,
    stealth_data: dict,
    monitor_data: dict,
    alert_data: dict,
    compact: bool = False,
) -> str:
    """Сформировать текстовый дашборд."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []

    # Заголовок
    lines.append(f"📊 **Playwright Dashboard** — {now}")
    lines.append("")

    # ── Алерты ──
    active_alerts = alert_data.get("active_alerts", {})
    if active_alerts:
        critical = sum(1 for a in active_alerts.values() if a.get("severity") == "critical")
        warning = sum(1 for a in active_alerts.values() if a.get("severity") == "warning")
        lines.append(f"🚨 **Алерты:** {len(active_alerts)} активных")
        if critical:
            lines.append(f"  🔴 Critical: {critical}")
        if warning:
            lines.append(f"  🟡 Warning: {warning}")
        lines.append("")

    # ── Screenshot Service ──
    lines.append("📸 **Screenshot Service**")

    ss_requests = metrics.get("screenshot_requests_total", 0)
    ss_errors = metrics.get("screenshot_browser_errors_total", 0)
    ss_active = metrics.get("screenshot_active_browsers", 0)
    ss_cache_hits = metrics.get("screenshot_cache_hits_total", 0)
    ss_cache_misses = metrics.get("screenshot_cache_misses_total", 0)
    ss_cache_total = ss_cache_hits + ss_cache_misses
    ss_cache_rate = (ss_cache_hits / ss_cache_total * 100) if ss_cache_total > 0 else 0

    lines.append(f"  Запросы: {int(ss_requests)} | Активных браузеров: {int(ss_active)}")
    lines.append(f"  Кэш: {fmt_pct(ss_cache_rate)} ({int(ss_cache_hits)}/{int(ss_cache_total)})")
    lines.append(f"  Ошибки: {int(ss_errors)}")

    if not compact:
        # Latency buckets из метрик
        latency_sum = metrics.get("screenshot_latency_seconds_sum", 0)
        latency_count = metrics.get("screenshot_latency_seconds_count", 0)
        avg_latency = (latency_sum / latency_count * 1000) if latency_count > 0 else 0
        lines.append(f"  Latency avg: {fmt_time(avg_latency/1000)}")

    lines.append("")

    # ── Site Monitor ──
    lines.append("🌐 **Site Monitor**")

    if monitor_data:
        checks = monitor_data.get("checks", [])
        total = monitor_data.get("total", 0)
        ok = monitor_data.get("ok", 0)
        degraded = monitor_data.get("degraded", 0)
        errors = monitor_data.get("error", 0)
        uptime = (ok / total * 100) if total > 0 else 0

        lines.append(f"  Uptime: {fmt_pct(uptime)} ({ok}/{total} OK)")
        if degraded:
            lines.append(f"  ⚠️ Degraded: {degraded}")
        if errors:
            lines.append(f"  ❌ Errors: {errors}")

        if not compact:
            for check in checks:
                status_emoji = {"ok": "✅", "degraded": "⚠️", "error": "❌"}.get(check.get("status"), "❓")
                name = check.get("name", "?")
                load = check.get("load_time_ms", 0)
                lines.append(f"  {status_emoji} {name}: {load:.0f}ms")
    else:
        lines.append("  Нет данных (site_monitor не запущен)")

    lines.append("")

    # ── Stealth ──
    lines.append("🔒 **Stealth**")

    if stealth_data:
        score = stealth_data.get("score", 0)
        passed = stealth_data.get("passed", 0)
        failed = stealth_data.get("failed", 0)
        total_tests = passed + failed

        lines.append(f"  Score: {fmt_pct(score)} ({passed}/{total_tests} passed)")

        if not compact:
            results = stealth_data.get("results", [])
            for r in results:
                icon = "✅" if r.get("passed") else "❌"
                lines.append(f"  {icon} {r.get('test', '?')}")
    else:
        lines.append("  Нет данных (stealth_research не запущен)")

    lines.append("")

    # ── CrossPost ──
    lines.append("📤 **CrossPost**")

    cp_posts = metrics.get("crosspost_posts_total", 0)
    cp_errors = metrics.get("crosspost_errors_total", 0)
    cp_success = metrics.get("crosspost_posts_total_success", 0)
    cp_total = cp_posts + cp_errors
    cp_rate = (cp_success / cp_total * 100) if cp_total > 0 else 0

    lines.append(f"  Публикаций: {int(cp_posts)} | Успех: {fmt_pct(cp_rate)}")

    if not compact:
        cp_latency_sum = metrics.get("crosspost_latency_seconds_sum", 0)
        cp_latency_count = metrics.get("crosspost_latency_seconds_count", 0)
        cp_avg = (cp_latency_sum / cp_latency_count * 1000) if cp_latency_count > 0 else 0
        lines.append(f"  Latency avg: {fmt_time(cp_avg/1000)}")

    lines.append("")

    # ── Health Monitor ──
    lines.append("💓 **Health Monitor**")

    hm_checks = metrics.get("health_monitor_checks_total", 0)
    hm_uptime = metrics.get("health_monitor_uptime_percent", 100)

    lines.append(f"  Проверок: {int(hm_checks)} | Uptime: {fmt_pct(hm_uptime)}")

    if health_data:
        last_check = health_data.get("status", "?")
        last_response = health_data.get("response_time_ms", 0)
        status_emoji = {"ok": "✅", "degraded": "⚠️", "down": "❌"}.get(last_check, "❓")
        lines.append(f"  Последняя: {status_emoji} {last_check} ({last_response:.0f}ms)")

    lines.append("")

    # ── Системные метрики ──
    if not compact:
        lines.append("🖥 **Система**")
        try:
            import os
            load_avg = os.getloadavg()
            lines.append(f"  Load: {load_avg[0]:.2f} / {load_avg[1]:.2f} / {load_avg[2]:.2f}")

            # RAM
            with open("/proc/meminfo") as f:
                meminfo = f.read()
            total_ram = 0
            available_ram = 0
            for line in meminfo.split("\n"):
                if line.startswith("MemTotal:"):
                    total_ram = int(line.split()[1]) * 1024
                elif line.startswith("MemAvailable:"):
                    available_ram = int(line.split()[1]) * 1024
            if total_ram > 0:
                used_pct = (1 - available_ram / total_ram) * 100
                lines.append(f"  RAM: {fmt_pct(100-used_pct)} ({fmt_bytes(available_ram)} free / {fmt_bytes(total_ram)})")
        except Exception:
            pass

    lines.append("")
    lines.append("_Обновлено: " + now + "_")

    return "\n".join(lines)


def build_compact_dashboard(metrics: dict, monitor_data: dict, stealth_data: dict) -> str:
    """Компактный дашборд — одна строка на компонент."""
    now = datetime.now().strftime("%H:%M")
    parts = [f"📊 {now}"]

    # Screenshot
    ss_requests = int(metrics.get("screenshot_requests_total", 0))
    ss_active = int(metrics.get("screenshot_active_browsers", 0))
    parts.append(f"📸 {ss_requests}req/{ss_active}br")

    # Sites
    if monitor_data:
        ok = monitor_data.get("ok", 0)
        total = monitor_data.get("total", 0)
        parts.append(f"🌐 {ok}/{total}✅")
    else:
        parts.append("🌐 N/A")

    # Stealth
    if stealth_data:
        score = stealth_data.get("score", 0)
        icon = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
        parts.append(f"🔒 {icon}{score:.0f}%")
    else:
        parts.append("🔒 N/A")

    # Alerts
    alert_state = load_json_safe(ALERT_STATE)
    active = alert_state.get("active_alerts", {})
    if active:
        parts.append(f"🚨 {len(active)}")

    return " | ".join(parts)


# ─── Отправка в Telegram ──────────────────────────────────────────────────────

async def send_to_telegram(text: str, bot_token: str, chat_id: str) -> bool:
    """Отправить сообщение в Telegram."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
            )
            return resp.status_code == 200
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Telegram Dashboard для Playwright-инфраструктуры")
    parser.add_argument("--compact", action="store_true", help="Компактный формат")
    parser.add_argument("--component", choices=["screenshot", "monitor", "stealth", "crosspost", "health"],
                        help="Показать только компонент")
    parser.add_argument("--send", action="store_true", help="Отправить в Telegram")
    parser.add_argument("--bot-token", default="", help="Telegram bot token")
    parser.add_argument("--chat-id", default="", help="Telegram chat ID")
    args = parser.parse_args()

    # Собрать данные
    metrics = await fetch_prometheus_metrics()
    health_data = {}
    if HEALTH_LOG.exists():
        try:
            # Последняя запись
            lines = HEALTH_LOG.read_text().strip().split("\n")
            if lines:
                health_data = json.loads(lines[-1])
        except Exception:
            pass
    stealth_data = load_json_safe(STEALTH_REPORT)
    monitor_data = load_json_safe(MONITOR_REPORT)
    alert_data = load_json_safe(ALERT_STATE)

    # Сформировать дашборд
    if args.compact:
        text = build_compact_dashboard(metrics, monitor_data, stealth_data)
    else:
        text = build_dashboard(metrics, health_data, stealth_data, monitor_data, alert_data)

    # Вывод
    if args.send and args.bot_token and args.chat_id:
        success = await send_to_telegram(text, args.bot_token, args.chat_id)
        if success:
            logger.info("Dashboard sent to Telegram")
        else:
            logger.error("Failed to send dashboard")
            print(text)
    else:
        print(text)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
