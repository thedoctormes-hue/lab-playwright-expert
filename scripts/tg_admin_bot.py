"""
Lab Playwright Kit — Telegram Admin Bot.

Remote management of all Playwright operations:
  /status          — Status of all services
  /screenshot <url> [name] — Take a screenshot
  /crawl <url> [depth]     — Crawl a URL
  /stealth_test            — Run stealth benchmark
  /ghost_protocol <mode>   — Run Ghost Protocol (recon|full|anti|report)
  /metrics                 — System metrics (CPU, RAM, disk)
  /logs <service> [lines]  — Recent logs
  /help                    — Available commands

Environment variables:
  TG_BOT_TOKEN   — Bot token (required)
  TG_ADMIN_IDS   — Comma-separated admin user IDs (required)

Usage:
  python3 scripts/tg_admin_bot.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

import psutil

# ─── aiogram v3 ──────────────────────────────────────────────────────────────
from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, Message


# ─── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SRC_DIR = PROJECT_ROOT / "src"
LOG_DIR = Path("/var/log")

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("tg_admin_bot")

# ─── Configuration ────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
RAW_ADMIN_IDS = os.environ.get("TG_ADMIN_IDS", "")
ADMIN_IDS: set[int] = set()
for _raw in RAW_ADMIN_IDS.split(","):
    _raw = _raw.strip()
    if _raw.isdigit():
        ADMIN_IDS.add(int(_raw))

# ─── Rate limiting ────────────────────────────────────────────────────────────
_rate_limit: dict[int, list[float]] = {}
RATE_LIMIT_MAX = 10  # max commands
_RATE_LIMIT_WINDOW = 60  # per 60 seconds


def _is_rate_limited(user_id: int) -> bool:
    """Check if user exceeded rate limit."""
    now = time.monotonic()
    timestamps = _rate_limit.get(user_id, [])
    # Purge old entries
    timestamps = [t for t in timestamps if now - t < _RATE_LIMIT_WINDOW]
    _rate_limit[user_id] = timestamps
    if len(timestamps) >= RATE_LIMIT_MAX:
        return True
    timestamps.append(now)
    return False


# ─── Service registry ─────────────────────────────────────────────────────────
# Maps service names → (systemd unit, description, script path)
SERVICES: dict[str, dict] = {
    "screenshot": {
        "unit": "screenshot-service",
        "desc": "Screenshot-as-a-Service",
        "script": SCRIPTS_DIR / "screenshot_service.py",
    },
    "health": {
        "unit": "screenshot-healthcheck",
        "desc": "Health Monitor",
        "script": SCRIPTS_DIR / "health_monitor.py",
    },
    "monitor": {
        "unit": "site-monitor",
        "desc": "Site Monitor",
        "script": SCRIPTS_DIR / "site_monitor.py",
    },
    "ghost": {
        "unit": "",
        "desc": "Ghost Protocol",
        "script": SCRIPTS_DIR / "ghost_protocol.py",
    },
    "stealth": {
        "unit": "",
        "desc": "Stealth Benchmark",
        "script": SCRIPTS_DIR / "stealth_research.py",
    },
    "crosspost": {
        "unit": "",
        "desc": "Crosspost",
        "script": SCRIPTS_DIR / "crosspost.py",
    },
}

# ─── Router ───────────────────────────────────────────────────────────────────
router = Router()


# ─── Security middleware ──────────────────────────────────────────────────────
@router.message.middleware()
async def security_middleware(handler, event: Message, data: dict):
    """Check admin access and rate limiting."""
    user = event.from_user
    if not user:
        return  # no user, skip

    uid = user.id

    # Admin check
    if ADMIN_IDS and uid not in ADMIN_IDS:
        log.warning(f"Unauthorized access attempt from user {uid} ({user.username or 'N/A'})")
        await event.answer("🚫 Доступ запрещён. Вы не администратор.")
        return

    # Rate limiting
    if _is_rate_limited(uid):
        log.warning(f"Rate limited user {uid}")
        await event.answer("⏳ Слишком много команд. Подождите минуту.")
        return

    # Log command
    log.info(f"User {uid} ({user.username or 'N/A'}): {event.text}")

    return await handler(event, data)


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _run_subprocess(
    cmd: list[str],
    timeout: int = 30,
    cwd: Path | None = None,
) -> tuple[str, str, int]:
    """Run a command and return (stdout, stderr, returncode)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd) if cwd else None,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return (
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
            proc.returncode or 0,
        )
    except asyncio.TimeoutError:
        return "", "⏰ Таймаут выполнения команды", 1
    except Exception as e:
        return "", f"❌ Ошибка: {e}", 1


def _truncate(text: str, max_len: int = 4000) -> str:
    """Truncate text to fit Telegram message limit."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n\n... (обрезано)"


async def _send_long_message(bot: Bot, chat_id: int, text: str, **kwargs):
    """Split and send long messages."""
    MAX = 4096
    for i in range(0, len(text), MAX):
        chunk = text[i : i + MAX]
        await bot.send_message(chat_id, chunk, **kwargs)


# ─── /start ───────────────────────────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "🤖 *Lab Playwright Kit — Admin Bot*\n\n"
        "Удалённое управление операциями Playwright.\n"
        "Введите /help для списка команд.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── /help ────────────────────────────────────────────────────────────────────
@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📋 *Доступные команды:*\n\n"
        "/status — Статус всех сервисов\n"
        "/screenshot `<url>` `[name]` — Скриншот URL\n"
        "/crawl `<url>` `[depth]` — Обход сайта\n"
        "/stealth_test — Запуск stealth benchmark\n"
        "/ghost_protocol `<mode>` — Ghost Protocol\n"
        "  • `recon` — разведка\n"
        "  • `full` — полная атака\n"
        "  • `anti` — анти-детект\n"
        "  • `report` — отчёт\n"
        "/metrics — Системные метрики (CPU, RAM, диск)\n"
        "/logs `<service>` `[lines]` — Логи сервиса\n"
        "  Сервисы: screenshot, health, monitor\n"
        "/help — Эта справка",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── /status ──────────────────────────────────────────────────────────────────
@router.message(Command("status"))
async def cmd_status(message: Message):
    lines = ["📊 *Статус сервисов:*\n"]

    for name, svc in SERVICES.items():
        unit = svc.get("unit", "")
        desc = svc["desc"]
        if unit:
            # Check systemd status
            out, _, rc = await _run_subprocess(
                ["systemctl", "is-active", unit], timeout=5
            )
            state = out.strip()
            if state == "active":
                icon = "🟢"
                status_text = "работает"
            elif state == "inactive":
                icon = "🔴"
                status_text = "остановлен"
            elif state == "failed":
                icon = "💥"
                status_text = "ошибка"
            else:
                icon = "⚪"
                status_text = state or "неизвестно"
        else:
            icon = "🔵"
            status_text = "скрипт"

        lines.append(f"{icon} *{desc}* — {status_text}")

    # Add system uptime
    try:
        boot = psutil.boot_time()
        uptime_sec = time.time() - boot
        hours, remainder = divmod(int(uptime_sec), 3600)
        minutes, _ = divmod(remainder, 60)
        lines.append(f"\n⏱ Аптайм: {hours}ч {minutes}м")
    except Exception:
        pass

    await message.answer("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ─── /screenshot ──────────────────────────────────────────────────────────────
@router.message(Command("screenshot"))
async def cmd_screenshot(message: Message):
    text = message.text or ""
    parts = text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(
            "⚠️ Использование: /screenshot `<url>` `[name]`\n"
            "Пример: /screenshot https://example.com",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    url = parts[1].strip()
    name = parts[2].strip() if len(parts) > 2 else "screenshot"

    # Basic URL validation
    if not url.startswith(("http://", "https://")):
        await message.answer("❌ Некорректный URL. Должен начинаться с http:// или https://")
        return

    status_msg = await message.answer(f"📸 Делаю скриншот: {url} ...")

    # Use playwright screenshot via the kit
    out, err, rc = await _run_subprocess(
        [
            sys.executable, "-c",
            f"""
import asyncio, sys
sys.path.insert(0, '{SRC_DIR}')
from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.screenshot import ScreenshotMaker

async def main():
    async with BrowserManager() as browser:
        maker = ScreenshotMaker(browser)
        path = await maker.screenshot('{url}', name='{name}')
        print(f'OK:{{path}}')

asyncio.run(main())
""",
        ],
        timeout=60,
        cwd=str(PROJECT_ROOT),
    )

    if rc == 0 and "OK:" in out:
        # Extract path
        path_str = out.split("OK:")[-1].strip()
        screenshot_path = Path(path_str)
        if screenshot_path.exists():
            await message.answer_photo(
                photo=FSInputFile(screenshot_path),
                caption=f"✅ Скриншот: {url}",
            )
        else:
            await message.answer(f"✅ Скриншот сохранён: {path_str}\nНо файл не найден на диске.")
    else:
        await message.answer(
            f"❌ Ошибка скриншота:\n```\n{_truncate(err or out)}\n```",
            parse_mode=ParseMode.MARKDOWN,
        )

    # Delete status message
    try:
        await status_msg.delete()
    except Exception:
        pass


# ─── /crawl ───────────────────────────────────────────────────────────────────
@router.message(Command("crawl"))
async def cmd_crawl(message: Message):
    text = message.text or ""
    parts = text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(
            "⚠️ Использование: /crawl `<url>` `[depth]`\n"
            "Пример: /crawl https://example.com 2",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    url = parts[1].strip()
    depth = int(parts[2]) if len(parts) > 2 and parts[2].strip().isdigit() else 1

    if not url.startswith(("http://", "https://")):
        await message.answer("❌ Некорректный URL.")
        return

    if depth < 1 or depth > 5:
        await message.answer("❌ Глубина должна быть от 1 до 5.")
        return

    status_msg = await message.answer(f"🕷 Начинаю обход: {url} (глубина {depth}) ...")

    out, err, rc = await _run_subprocess(
        [
            sys.executable, "-c",
            f"""
import asyncio, json, sys
sys.path.insert(0, '{SRC_DIR}')
from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.parser import PageParser

async def crawl(url, max_depth):
    results = []
    visited = set()
    queue = [(url, 0)]

    async with BrowserManager() as browser:
        while queue:
            current_url, current_depth = queue.pop(0)
            if current_url in visited or current_depth > max_depth:
                continue
            visited.add(current_url)

            try:
                page = await browser.new_page()
                await page.goto(current_url, wait_until='domcontentloaded', timeout=15000)
                parser = PageParser(page)
                data = await parser.extract_links()
                title = await page.title()
                results.append({{
                    'url': current_url,
                    'title': title,
                    'links': data.get('links', [])[:20],
                    'depth': current_depth
                }})
                if current_depth < max_depth:
                    for link in data.get('links', [])[:10]:
                        if link and link.startswith('http') and link not in visited:
                            queue.append((link, current_depth + 1))
                await page.close()
            except Exception as e:
                results.append({{'url': current_url, 'error': str(e), 'depth': current_depth}})

    print(json.dumps(results, ensure_ascii=False, indent=2))

asyncio.run(crawl('{url}', {depth}))
""",
        ],
        timeout=120,
        cwd=str(PROJECT_ROOT),
    )

    if rc == 0:
        try:
            data = json.loads(out)
            lines = [f"🕷 *Результаты обхода:* {url}\n"]
            lines.append(f"Найдено страниц: {len(data)}\n")
            for item in data[:15]:
                title = item.get("title", "Без заголовка")
                item_url = item.get("url", "")
                item_depth = item.get("depth", 0)
                n_links = len(item.get("links", []))
                err_msg = item.get("error", "")
                if err_msg:
                    lines.append(f"  ❌ {item_url} — {err_msg}")
                else:
                    lines.append(f"  📄 [D{item_depth}] {title}")
                    lines.append(f"     {item_url} ({n_links} ссылок)")
            if len(data) > 15:
                lines.append(f"\n... и ещё {len(data) - 15} страниц")
            await _send_long_message(
                message.bot, message.chat.id, "\n".join(lines),
                parse_mode=ParseMode.MARKDOWN,
            )
        except json.JSONDecodeError:
            await message.answer(
                f"✅ Обход завершён (сырой вывод):\n```\n{_truncate(out)}\n```",
                parse_mode=ParseMode.MARKDOWN,
            )
    else:
        await message.answer(
            f"❌ Ошибка обхода:\n```\n{_truncate(err or out)}\n```",
            parse_mode=ParseMode.MARKDOWN,
        )

    try:
        await status_msg.delete()
    except Exception:
        pass


# ─── /stealth_test ────────────────────────────────────────────────────────────
@router.message(Command("stealth_test"))
async def cmd_stealth_test(message: Message):
    status_msg = await message.answer("🥷 Запуск stealth benchmark ...")

    out, err, rc = await _run_subprocess(
        [sys.executable, str(SCRIPTS_DIR / "stealth_research.py"), "--quick"],
        timeout=120,
        cwd=str(PROJECT_ROOT),
    )

    if rc == 0:
        # Try to find and parse the report
        report_path = Path("/tmp/stealth_report.json")
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text())
                score = report.get("score", "?")
                tests = report.get("tests_run", "?")
                passed = report.get("tests_passed", "?")
                await message.answer(
                    f"🥷 *Stealth Benchmark*\n\n"
                    f"Score: *{score}*\n"
                    f"Тестов: {tests}\n"
                    f"Пройдено: {passed}\n\n"
                    f"```\n{_truncate(out[:2000])}\n```",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception:
                await message.answer(
                    f"✅ Stealth benchmark завершён:\n```\n{_truncate(out)}\n```",
                    parse_mode=ParseMode.MARKDOWN,
                )
        else:
            await message.answer(
                f"✅ Stealth benchmark завершён:\n```\n{_truncate(out)}\n```",
                parse_mode=ParseMode.MARKDOWN,
            )
    else:
        await message.answer(
            f"❌ Ошибка stealth benchmark:\n```\n{_truncate(err or out)}\n```",
            parse_mode=ParseMode.MARKDOWN,
        )

    try:
        await status_msg.delete()
    except Exception:
        pass


# ─── /ghost_protocol ──────────────────────────────────────────────────────────
@router.message(Command("ghost_protocol"))
async def cmd_ghost_protocol(message: Message):
    text = message.text or ""
    parts = text.split(maxsplit=1)
    mode = parts[1].strip() if len(parts) > 1 else "recon"

    valid_modes = ("recon", "full", "anti", "report")
    if mode not in valid_modes:
        await message.answer(
            f"⚠️ Режим должен быть одним из: {', '.join(valid_modes)}\n"
            f"Пример: /ghost_protocol recon",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    status_msg = await message.answer(f"👻 Запуск Ghost Protocol (режим: {mode}) ...")

    out, err, rc = await _run_subprocess(
        [sys.executable, str(SCRIPTS_DIR / "ghost_protocol.py"), "--mode", mode],
        timeout=300,
        cwd=str(PROJECT_ROOT),
    )

    if rc == 0:
        # Check for report files
        report_dir = Path("/tmp/ghost_protocol/reports")
        report_files = list(report_dir.glob("*.html")) if report_dir.exists() else []

        msg_text = (
            f"👻 *Ghost Protocol — {mode}*\n\n"
            f"```\n{_truncate(out[:3000])}\n```"
        )
        if report_files:
            msg_text += f"\n\n📄 Отчёты: {len(report_files)} файл(ов)"
            for rf in report_files[:3]:
                msg_text += f"\n  • {rf.name}"

        await message.answer(msg_text, parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer(
            f"❌ Ошибка Ghost Protocol:\n```\n{_truncate(err or out)}\n```",
            parse_mode=ParseMode.MARKDOWN,
        )

    try:
        await status_msg.delete()
    except Exception:
        pass


# ─── /metrics ─────────────────────────────────────────────────────────────────
@router.message(Command("metrics"))
async def cmd_metrics(message: Message):
    # CPU
    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_count = psutil.cpu_count()

    # RAM
    mem = psutil.virtual_memory()
    mem_total_gb = mem.total / (1024 ** 3)
    mem_used_gb = mem.used / (1024 ** 3)
    mem_pct = mem.percent

    # Disk
    disk = psutil.disk_usage("/")
    disk_total_gb = disk.total / (1024 ** 3)
    disk_used_gb = disk.used / (1024 ** 3)
    disk_pct = disk.percent

    # Load average
    load1, load5, load15 = psutil.getloadavg()

    # Network
    net = psutil.net_io_counters()
    net_sent_gb = net.bytes_sent / (1024 ** 3)
    net_recv_gb = net.bytes_recv / (1024 ** 3)

    # Processes
    n_procs = len(psutil.pids())

    # Color indicators
    def _indicator(pct: float) -> str:
        if pct < 60:
            return "🟢"
        elif pct < 85:
            return "🟡"
        return "🔴"

    await message.answer(
        f"📊 *Системные метрики*\n\n"
        f"*CPU:* {_indicator(cpu_percent)} {cpu_percent}% ({cpu_count} ядер)\n"
        f"*Load:* {load1:.2f} / {load5:.2f} / {load15:.2f}\n\n"
        f"*RAM:* {_indicator(mem_pct)} {mem_pct}%\n"
        f"  {mem_used_gb:.1f} / {mem_total_gb:.1f} ГБ\n\n"
        f"*Диск:* {_indicator(disk_pct)} {disk_pct}%\n"
        f"  {disk_used_gb:.1f} / {disk_total_gb:.1f} ГБ\n\n"
        f"*Сеть:* ↑{net_sent_gb:.2f} ГБ / ↓{net_recv_gb:.2f} ГБ\n"
        f"*Процессы:* {n_procs}\n",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── /logs ────────────────────────────────────────────────────────────────────
@router.message(Command("logs"))
async def cmd_logs(message: Message):
    text = message.text or ""
    parts = text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(
            "⚠️ Использование: /logs `<service>` `[lines]`\n"
            "Сервисы: screenshot, health, monitor\n"
            "Пример: /logs screenshot 50",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    service = parts[1].strip().lower()
    n_lines = int(parts[2]) if len(parts) > 2 and parts[2].strip().isdigit() else 30

    if n_lines > 200:
        n_lines = 200

    # Try journalctl first, then fall back to log files
    svc = SERVICES.get(service)
    if svc and svc.get("unit"):
        out, err, rc = await _run_subprocess(
            ["journalctl", "-u", svc["unit"], "-n", str(n_lines), "--no-pager"],
            timeout=10,
        )
        if rc == 0 and out.strip():
            await message.answer(
                f"📜 *Логи {service}* (последние {n_lines} строк):\n"
                f"```\n{_truncate(out)}\n```",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

    # Fallback: try log files
    log_candidates = [
        LOG_DIR / f"{service}.log",
        LOG_DIR / f"{service}-service.log",
        Path(f"/tmp/{service}.log"),
    ]
    for log_path in log_candidates:
        if log_path.exists():
            out, _, _ = await _run_subprocess(
                ["tail", "-n", str(n_lines), str(log_path)], timeout=5
            )
            if out.strip():
                await message.answer(
                    f"📜 *Логи {service}* ({log_path}):\n"
                    f"```\n{_truncate(out)}\n```",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return

    await message.answer(f"⚠️ Логи для '{service}' не найдены.")


# ─── Main entry point ─────────────────────────────────────────────────────────
async def main():
    """Start the bot."""
    if not BOT_TOKEN:
        log.error("TG_BOT_TOKEN is not set!")
        sys.exit(1)

    if not ADMIN_IDS:
        log.warning("TG_ADMIN_IDS is not set — no admins configured!")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    log.info(f"Starting bot. Admins: {ADMIN_IDS}")
    log.info(f"Registered services: {list(SERVICES.keys())}")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
