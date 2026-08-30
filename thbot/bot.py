"""Telegram-бот THBOT (MVP): ссылка на канал → сводка об авторе, пользе и развитии.

Запуск: python -m thbot.bot (нужны BOT_TOKEN и OPENROUTER_API_KEY в .env).
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from . import analyzer, parser, report, storage
from .config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("thbot")

WELCOME = (
    "👋 <b>THBOT</b> — делаю сводку по Telegram-каналу.\n\n"
    "Пришлите ссылку на публичный канал или @username — например:\n"
    "<code>https://t.me/molyanov_blog</code>\n\n"
    "Я соберу последние посты, прогоню их через ИИ и отвечу:\n"
    "👤 кто автор и насколько он эксперт;\n"
    "📚 о чём канал и как он развивался;\n"
    "🎯 сколько контента полезного, а сколько — реклама/репосты/шум;\n"
    "🧰 какие практики и форматы можно забрать себе.\n\n"
    f"Лимит: {settings.user_daily_limit} свежих анализов в сутки "
    "(повторные открытия из кэша — без лимита)."
)


def _keyboard(username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data=f"refresh:{username}"),
                InlineKeyboardButton(text="👍", callback_data=f"fb:{username}:up"),
                InlineKeyboardButton(text="👎", callback_data=f"fb:{username}:down"),
            ]
        ]
    )


def _extract_username(message: Message) -> str | None:
    """Достаёт username из текста сообщения или из пересланного поста канала."""
    origin = getattr(message, "forward_origin", None)
    if origin is not None:
        chat = getattr(origin, "chat", None)
        if chat is not None and getattr(chat, "username", None):
            return chat.username
    if message.text:
        return message.text.strip()
    return None


async def _analyze_and_answer(username: str, bot: Bot, chat_id: int, status_id: int) -> None:
    """Фоновая задача: сбор → классификация → синтез → отправка отчёта."""

    async def status(text: str) -> None:
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=status_id, text=text)
        except Exception:  # noqa: BLE001 — сообщение могло не измениться/пропасть
            pass

    try:
        await status("🔎 Собираю посты канала…")
        channel = await parser.fetch_channel(username, limit=settings.fetch_posts_limit)
        if len(channel.posts) < 5:
            await status(
                f"В канале @{username} слишком мало постов для анализа "
                f"(нашёл {len(channel.posts)}). Попробуйте более живой канал."
            )
            return

        await status(f"🧠 Анализирую {len(channel.posts)} постов через ИИ…")
        classified = await analyzer.classify_posts(channel.posts)
        metrics = analyzer.compute_metrics(channel.posts, classified)
        top_posts = analyzer.rank_posts(channel.posts, classified)

        await status("📝 Формирую сводку…")
        synthesis = await analyzer.synthesize(channel, metrics, classified, top_posts)

        await storage.save_report(
            username,
            {
                "channel": {
                    "username": channel.username,
                    "title": channel.title,
                    "subscribers": channel.subscribers,
                },
                "metrics": metrics,
                "synthesis": synthesis,
            },
        )

        messages = report.build_report(channel, metrics, synthesis)
        # первую часть показываем на месте статус-сообщения
        await bot.edit_message_text(
            chat_id=chat_id, message_id=status_id, text=messages[0],
            disable_web_page_preview=True,
        )
        for chunk in messages[1:]:
            await bot.send_message(chat_id, chunk, disable_web_page_preview=True)
        await bot.send_message(
            chat_id,
            f"Готово! Отчёт по @{username}. Полезен разбор? 👇",
            reply_markup=_keyboard(username),
        )
    except parser.ChannelNotFoundError as exc:
        await status(f"❌ {exc}")
    except parser.PrivateChannelError as exc:
        await status(f"❌ {exc}")
    except analyzer.RateLimitedError as exc:
        log.warning("OpenRouter лимит: %s", exc)
        await status(
            "⏳ Бесплатный лимит ИИ сейчас исчерпан (много отказов 429 от OpenRouter). "
            "Это общий лимит на минуту/сутки. Подождите 2–5 минут и нажмите «🔄 Обновить» "
            "или пришлите канал позже — собранные данные по каналу уже подгружены, "
            "повторный анализ будет быстрее."
        )
    except RuntimeError as exc:
        log.warning("LLM недоступен: %s", exc)
        await status(
            "⚠️ Бесплатные ИИ-модели сейчас перегружены или недоступны. "
            "Попробуйте через несколько минут или нажмите «🔄 Обновить» позже."
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("Ошибка анализа @%s: %s", username, exc)
        await status("💥 Что-то пошло не так при анализе. Попробуйте другой канал или позже.")


def register(dp: Dispatcher) -> None:
    @dp.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        await message.answer(WELCOME)

    @dp.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(WELCOME)

    @dp.callback_query(F.data.startswith("fb:"))
    async def on_feedback(cb: CallbackQuery) -> None:
        _, username, vote = cb.data.split(":", 2)
        await storage.save_feedback(username, cb.from_user.id, vote)
        await cb.answer("Спасибо за фидбек! 🙌" if vote == "up" else "Спасибо, доработаем! 🛠")

    @dp.callback_query(F.data.startswith("refresh:"))
    async def on_refresh(cb: CallbackQuery) -> None:
        username = cb.data.split(":", 1)[1]
        await cb.answer("Обновляю…")
        left = await storage.usage_left(cb.from_user.id)
        if left <= 0:
            await cb.message.answer(
                f"Лимит свежих анализов на сегодня исчерпан ({settings.user_daily_limit}/день). "
                "Кэш доступен без ограничений, лимит обновится завтра."
            )
            return
        await storage.usage_increment(cb.from_user.id)
        status_msg = await cb.message.answer(f"🔎 Обновляю анализ @{username}…")
        asyncio.create_task(
            _analyze_and_answer(username, cb.bot, cb.message.chat.id, status_msg.message_id)
        )

    @dp.message(F.text)
    async def on_link(message: Message) -> None:
        ref = _extract_username(message)
        if not ref:
            await message.answer(WELCOME)
            return
        try:
            username = parser.normalize_channel_ref(ref)
        except (parser.ChannelNotFoundError, parser.PrivateChannelError) as exc:
            await message.answer(f"❌ {exc}")
            return

        # кэш: повторный анализ не тратим ни лимит, ни запросы к ИИ
        cached = await storage.get_cached_report(username)
        if cached:
            ch = cached["channel"]
            channel = parser.ChannelData(
                username=ch["username"],
                title=ch["title"],
                description="",
                subscribers=ch.get("subscribers"),
                url=f"https://t.me/{ch['username']}",
                posts=[],
            )
            messages = report.build_report(channel, cached["metrics"], cached["synthesis"])
            for i, chunk in enumerate(messages):
                if i == 0:
                    await message.answer(
                        chunk + "\n\n<i>(из кэша — до 7 дней; можно обновить кнопкой)</i>",
                        disable_web_page_preview=True,
                    )
                else:
                    await message.answer(chunk, disable_web_page_preview=True)
            await message.answer(f"Отчёт по @{username}.", reply_markup=_keyboard(username))
            return

        left = await storage.usage_left(message.from_user.id)
        if left <= 0:
            await message.answer(
                f"Лимит свежих анализов на сегодня исчерпан ({settings.user_daily_limit}/день). "
                "Попробуйте завтра или пришлите канал, который уже анализировали (кэш)."
            )
            return
        await storage.usage_increment(message.from_user.id)

        status_msg = await message.answer(f"🔎 Анализирую @{username}…")
        asyncio.create_task(
            _analyze_and_answer(username, message.bot, message.chat.id, status_msg.message_id)
        )


async def main() -> None:
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN не задан — создайте бота у @BotFather и впишите токен в .env")
    if not settings.openrouter_api_key:
        raise SystemExit("OPENROUTER_API_KEY не задан — получите ключ на https://openrouter.ai/keys")

    storage.init_db()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    register(dp)
    log.info("THBOT запущен. Модели классификации: %s", settings.classifier_models)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
