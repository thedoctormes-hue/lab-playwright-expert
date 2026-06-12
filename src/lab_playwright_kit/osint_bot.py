"""
OSINT Telegram Bot — бот для поиска аккаунтов по username.

Команды:
  /start — приветствие и справка
  /find <username> — поиск по всем платформам
  /find <username> --tags coding — поиск по тегам
  /platforms — список доступных платформ
  /stats — статистика бота

Использование:
    >>> from lab_playwright_kit.osint_bot import create_bot
    >>> bot = create_bot("YOUR_BOT_TOKEN")
    >>> bot.run()

CLI:
    python -m lab_playwright_kit.osint_bot --token YOUR_BOT_TOKEN
"""
from __future__ import annotations

import asyncio
import argparse
import time
from typing import Any

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command, CommandStart
from aiogram.enums import ParseMode
from loguru import logger

from .account_finder import AccountFinder, SearchReport
from .platform_registry import PlatformRegistry


# ─── Bot State ───────────────────────────────────────────────────────────────

class BotState:
    """Состояние бота."""
    def __init__(self):
        self.total_searches: int = 0
        self.total_found: int = 0
        self.start_time: float = time.time()
        self.registry = PlatformRegistry()
        self.registry.load_defaults()
        self.finder = AccountFinder(registry=self.registry, max_concurrent=10, timeout=15.0)


state = BotState()
router = Router()


# ─── Command Handlers ────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Приветствие и справка."""
    await message.answer(
        "🔍 <b>OSINT Finder Bot</b>\n\n"
        "Ищу аккаунты по username на 50+ платформах.\n\n"
        "<b>Команды:</b>\n"
        "• <code>/find username</code> — поиск по всем платформам\n"
        "• <code>/find username --tags coding</code> — поиск по тегам\n"
        "• <code>/find username --tags ru,social</code> — несколько тегов\n"
        "• <code>/platforms</code> — список платформ\n"
        "• <code>/stats</code> — статистика\n\n"
        "<b>Теги:</b> <code>social</code>, <code>ru</code>, <code>coding</code>, "
        "<code>forum</code>, <code>messaging</code>, <code>media</code>, <code>gaming</code>",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("find"))
async def cmd_find(message: Message):
    """Поиск аккаунтов по username."""
    args = message.text.split()[1:] if message.text else []

    if not args:
        await message.answer("⚠️ Укажи ник: <code>/find username</code>", parse_mode=ParseMode.HTML)
        return

    # Парсинг аргументов
    username = args[0]
    tags = []
    permute = False

    i = 1
    while i < len(args):
        if args[i] == "--tags" and i + 1 < len(args):
            tags = [t.strip() for t in args[i + 1].split(",")]
            i += 2
        elif args[i] == "--permute":
            permute = True
            i += 1
        else:
            i += 1

    # Отправить сообщение о начале поиска
    tags_str = f" (теги: {', '.join(tags)})" if tags else ""
    status_msg = await message.answer(
        f"🔍 Ищу <b>{username}</b>{tags_str}...\n"
        f"⏳ Проверяю {state.registry.count()} платформ...",
        parse_mode=ParseMode.HTML,
    )

    try:
        # Поиск
        if tags:
            report = await state.finder.search(username, tags=tags, permute=permute)
        else:
            report = await state.finder.search(username, permute=permute)

        state.total_searches += 1
        state.total_found += report.total_found

        # Формирование ответа
        if report.found:
            # Группировка по тегам
            lines = [
                f"✅ <b>Найдено {report.total_found} аккаунтов</b> "
                f"из {report.checked} проверенных ({report.elapsed_seconds:.1f}с)\n",
            ]

            # Сортировка по уверенности
            sorted_accounts = sorted(report.found, key=lambda a: a.confidence, reverse=True)

            for acc in sorted_accounts:
                confidence_emoji = "🟢" if acc.confidence >= 0.8 else "🟡" if acc.confidence >= 0.5 else "🟠"
                tags_display = f" <i>({', '.join(acc.tags[:3])})</i>" if acc.tags else ""
                lines.append(
                    f"{confidence_emoji} <a href=\"{acc.url}\">{acc.platform}</a> — "
                    f"<code>{acc.username}</code>{tags_display}"
                )

            text = "\n".join(lines)
        else:
            text = (
                f"❌ <b>{username}</b> не найден ни на одной из {report.checked} платформ.\n"
                f"⏱ Время: {report.elapsed_seconds:.1f}с"
            )

        # Кнопки
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Повторить", callback_data=f"find:{username}"),
                InlineKeyboardButton(text="📊 Все платформы", callback_data=f"platforms:{username}"),
            ],
        ])

        await status_msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Find error: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}", parse_mode=ParseMode.HTML)


@router.message(Command("platforms"))
async def cmd_platforms(message: Message):
    """Список доступных платформ."""
    platforms = state.registry.all()
    enabled = [p for p in platforms if not p.disabled]

    # Группировка по тегам
    by_tag: dict[str, list[str]] = {}
    for p in enabled:
        for tag in p.tags:
            if tag not in by_tag:
                by_tag[tag] = []
            by_tag[tag].append(p.name)

    lines = [f"📋 <b>Платформы ({len(enabled)} активных)</b>\n"]
    for tag, names in sorted(by_tag.items()):
        lines.append(f"\n<b>{tag}:</b> {', '.join(sorted(names))}")

    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Статистика бота."""
    uptime = time.time() - state.start_time
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)

    await message.answer(
        f"📊 <b>Статистика бота</b>\n\n"
        f"🔍 Поисков: {state.total_searches}\n"
        f"✅ Найдено аккаунтов: {state.total_found}\n"
        f"🌐 Платформ: {state.registry.count()}\n"
        f"⏱ Аптайм: {hours}ч {minutes}мин",
        parse_mode=ParseMode.HTML,
    )


# ─── Callback Handlers ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("find:"))
async def callback_find(callback: CallbackQuery):
    """Повторный поиск по кнопке."""
    username = callback.data.split(":", 1)[1]
    # Создать фейковое сообщение
    class FakeMessage:
        def __init__(self, text, chat):
            self.text = f"/find {username}"
            self.chat = chat
        async def answer(self, *args, **kwargs):
            return await callback.message.answer(*args, **kwargs)

    fake_msg = FakeMessage(f"/find {username}", callback.message.chat)
    await cmd_find(fake_msg)
    await callback.answer("🔍 Ищу...")


@router.callback_query(F.data.startswith("platforms:"))
async def callback_platforms(callback: CallbackQuery):
    """Показать результаты по всем платформам."""
    username = callback.data.split(":", 1)[1]
    await callback.answer("📋 Загружаю...")

    status_msg = await callback.message.answer(f"🔍 Проверяю <b>{username}</b> на всех платформах...", parse_mode=ParseMode.HTML)

    try:
        report = await state.finder.search(username, top_n=51)

        if report.found:
            lines = [f"📋 <b>Все платформы для {username}</b>\n"]
            for acc in sorted(report.found, key=lambda a: a.platform):
                lines.append(f"✅ <a href=\"{acc.url}\">{acc.platform}</a>")
            text = "\n".join(lines)
        else:
            text = f"❌ <b>{username}</b> не найден ({report.checked} платформ, {report.elapsed_seconds:.1f}с)"

        await status_msg.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")


# ─── Bot Factory ─────────────────────────────────────────────────────────────

def create_bot(token: str) -> Bot:
    """Создать бота.

    Args:
        token: Telegram Bot API токен

    Returns:
        Bot экземпляр (готов к запуску)
    """
    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(router)
    return bot, dp


def main():
    """Запуск бота из CLI."""
    parser = argparse.ArgumentParser(description="OSINT Finder Telegram Bot")
    parser.add_argument("--token", required=True, help="Telegram Bot API token")
    args = parser.parse_args()

    logger.info("Starting OSINT Bot...")
    bot = Bot(token=args.token)
    dp = Dispatcher()
    dp.include_router(router)

    asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    main()
