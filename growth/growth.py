"""
THBOT Growth — автоматический рост канала на чистом Bot API (без банов и левых аккаунтов).

Что делает сам после настройки:
  📅 Автопостинг — пересылаешь боту посты, он публикует их по расписанию + кнопка «Поделиться»
  🎲 Авторозыгрыши — приз → дедлайн → автовыбор победителей среди подписчиков
  🔗 UTM-ссылки — /link tiktok → считает, откуда идут подписчики
  💬 Живой чат — викторины/опросы по расписанию, приветствие, капча, антиспам, топ недели
  📊 Отчёт админу каждое утро

Бот должен быть АДМИНОМ канала (посты + пригласительные ссылки) и чата (удаление + баны).

Запуск:
  1. cp .env.example .env и заполни (BOT_TOKEN, CHANNEL_ID, ADMIN_IDS, ...)
  2. cp quiz.txt.example quiz.txt; cp polls.txt.example polls.txt (по желанию)
  3. pip install -r requirements.txt
  4. python growth.py
"""
import asyncio
import logging
import random
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated, ChatPermissions

import storage
import keyboards as kb
import texts
import content as C
from config import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("growth")
router = Router()
spam_cooldown: dict[int, float] = {}


class ContestFSM(StatesGroup):
    prize = State()
    hours = State()
    winners = State()


# ---------- helpers ----------

def is_admin(uid: int) -> bool:
    return uid in config.admin_ids


async def is_subscribed(bot: Bot, uid: int) -> bool:
    try:
        m = await bot.get_chat_member(chat_id=config.channel_id, user_id=uid)
        return m.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
    except Exception:
        return False


async def subs_count(bot: Bot) -> int | None:
    try:
        return await bot.get_chat_member_count(chat_id=config.channel_id)
    except Exception as e:
        log.warning("member count: %s", e)
        return None


def uname(m: Message) -> str:
    return m.from_user.username or ""


def fname(m: Message) -> str:
    return m.from_user.full_name or ""


# ---------- /start: UTM-метки ----------

@router.message(CommandStart())
async def cmd_start(msg: Message):
    src = ""
    if msg.text and "src_" in msg.text:
        try:
            src = msg.text.split("src_")[1].split()[0][:32]
        except IndexError:
            src = ""
    await storage.upsert_user(msg.from_user.id, uname(msg), fname(msg), src)
    if config.channel_url:
        await msg.answer(f"👋 Привет! Все материалы — в канале 👇",
                         reply_markup=kb.to_channel_kb(config.channel_url))
    else:
        await msg.answer("👋 Привет! Я — бот роста канала.")


# ---------- админ: очередь ----------

@router.message(Command("admin"))
async def admin_help(msg: Message):
    if is_admin(msg.from_user.id):
        await msg.answer(texts.ADMIN_HELP, parse_mode=ParseMode.HTML)


@router.message(Command("queue"))
async def q_len(msg: Message):
    if is_admin(msg.from_user.id):
        await msg.answer(f"📝 Постов в очереди: <b>{await storage.queue_len()}</b>", parse_mode=ParseMode.HTML)


@router.message(Command("clear"))
async def q_clear(msg: Message):
    if is_admin(msg.from_user.id):
        await msg.answer(f"🗑 Очередь очищена ({await storage.queue_clear()} шт).")


@router.message(Command("post"))
async def q_post_now(msg: Message, bot: Bot):
    if not is_admin(msg.from_user.id):
        return
    ok = await publish_next(bot)
    await msg.answer("✅ Опубликовал следующий пост." if ok else "📭 Очередь пуста — перешли мне посты.")


async def publish_next(bot: Bot) -> bool:
    item = await storage.queue_pop()
    if not item:
        return False
    _, from_chat, mid = item
    try:
        sent = await bot.copy_message(chat_id=config.channel_id, from_chat_id=from_chat, message_id=mid)
        teaser = (getattr(sent, "text", "") or getattr(sent, "caption", "") or "Загляни в канал")[:200]
        try:
            await bot.edit_message_reply_markup(chat_id=config.channel_id, message_id=sent.message_id,
                                                reply_markup=kb.plain_share_kb(config.channel_url, teaser))
        except Exception:
            pass
        log.info("📝 Автопост опубликован (очередь: %s)", await storage.queue_len())
        return True
    except Exception as e:
        log.warning("publish failed: %s", e)
        return False


async def autopost_loop(bot: Bot):
    while True:
        try:
            now = datetime.now().strftime("%H:%M")
            if now in config.autopost_times:
                flag = f"auto_{datetime.now():%Y-%m-%d}_{now}"
                if await storage.get_state(flag) != "1":
                    await storage.set_state(flag, "1")
                    if not await publish_next(bot):
                        for aid in config.admin_ids:
                            try:
                                await bot.send_message(aid, "📭 Очередь автопостов пуста! Перешли мне посты.")
                                break
                            except Exception:
                                pass
        except Exception as e:
            log.warning("autopost: %s", e)
        await asyncio.sleep(30)


# ---------- розыгрыши ----------

@router.message(Command("contest"))
async def contest_start(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await state.set_state(ContestFSM.prize)
    await msg.answer("🎁 Что разыгрываем? Пришли название приза. /cancel — отмена.")


@router.message(Command("cancel"))
async def contest_cancel(msg: Message, state: FSMContext):
    if is_admin(msg.from_user.id):
        await state.clear()
        await msg.answer("❌ Отменено.")


@router.message(ContestFSM.prize)
async def contest_prize(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await state.update_data(prize=(msg.text or "Приз")[:200])
    await state.set_state(ContestFSM.hours)
    await msg.answer("⏰ На сколько часов запускаем? Пришли число (например 48).")


@router.message(ContestFSM.hours)
async def contest_hours(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    try:
        hours = max(1, min(int((msg.text or "").strip()), 24 * 30))
    except ValueError:
        await msg.answer("Нужно число часов, например 48.")
        return
    await state.update_data(hours=hours)
    await state.set_state(ContestFSM.winners)
    await msg.answer("🏆 Сколько победителей? Пришли число (1–10).")


@router.message(ContestFSM.winners)
async def contest_winners(msg: Message, state: FSMContext, bot: Bot):
    if not is_admin(msg.from_user.id):
        return
    try:
        n = max(1, min(int((msg.text or "").strip()), 10))
    except ValueError:
        await msg.answer("Нужно число 1–10.")
        return
    data = await state.get_data()
    await state.clear()
    deadline = int((datetime.now() + timedelta(hours=data["hours"])).timestamp())
    cid = await storage.contest_create(data["prize"], n, deadline)
    dl = (datetime.now() + timedelta(hours=data["hours"])).strftime("%d.%m %H:%M")
    post = await bot.send_message(
        chat_id=config.channel_id,
        text=texts.CONTEST_POST.format(prize=data["prize"], deadline=dl, n=n, count=0),
        parse_mode=ParseMode.HTML, reply_markup=kb.contest_kb(cid),
    )
    await storage.contest_set_msg(cid, post.message_id)
    await msg.answer(f"🚀 Розыгрыш #{cid} запущен до {dl}!")


@router.message(F.chat.type == "private")
async def to_queue(msg: Message, state: FSMContext):
    """Любое сообщение админа в личку (не команда, не ответ в FSM) = пост в очередь."""
    if not is_admin(msg.from_user.id):
        return
    if await state.get_state() is not None:
        return  # идёт создание розыгрыша — не перехватываем
    if msg.text and msg.text.startswith("/"):
        return
    qid = await storage.queue_add(msg.chat.id, msg.message_id)
    await msg.answer(f"📥 В очередь! Позиция #{qid}, всего: <b>{await storage.queue_len()}</b>",
                     parse_mode=ParseMode.HTML)


@router.callback_query(F.data.startswith("join_"))
async def contest_join(cb: CallbackQuery, bot: Bot):
    cid = int(cb.data.split("_")[1])
    c = await storage.contest_get(cid)
    if not c or c["status"] != "open":
        await cb.answer("Розыгрыш уже завершён.", show_alert=True)
        return
    if not await is_subscribed(bot, cb.from_user.id):
        await cb.answer("Сначала подпишись на канал! 📢", show_alert=True)
        try:
            await bot.send_message(cb.from_user.id, "📢 Подпишись и возвращайся 👇",
                                   reply_markup=kb.to_channel_kb(config.channel_url))
        except Exception:
            pass
        return
    added = await storage.contest_add(cid, cb.from_user.id)
    await cb.answer("Ты в игре! 🍀" if added else "Ты уже участвуешь! 🍀")
    # throttled-обновление счётчика
    try:
        last = float(await storage.get_state(f"cedit_{cid}", "0"))
        if datetime.now().timestamp() - last > 300:
            await storage.set_state(f"cedit_{cid}", str(datetime.now().timestamp()))
            count = await storage.contest_count(cid)
            dl = datetime.fromtimestamp(c["deadline"]).strftime("%d.%m %H:%M")
            await bot.edit_message_text(
                chat_id=config.channel_id, message_id=c["channel_msg_id"],
                text=texts.CONTEST_POST.format(prize=c["prize"], deadline=dl, n=c["winners_n"], count=count),
                parse_mode=ParseMode.HTML, reply_markup=kb.contest_kb(cid),
            )
    except Exception:
        pass


async def draw_contest(bot: Bot, c: dict):
    users = await storage.contest_users(c["id"])
    ok: list[int] = []
    for uid in users[:1000]:
        if await is_subscribed(bot, uid):
            ok.append(uid)
        await asyncio.sleep(0.03)
    if not ok:
        # продлеваем на сутки
        await storage.contest_extend(c["id"], 86400)
        try:
            await bot.send_message(chat_id=config.channel_id,
                                   text=texts.CONTEST_NOBODY.format(prize=c["prize"]))
        except Exception:
            pass
        log.info("Конкурс #%s продлён — нет подписчиков среди участников", c["id"])
        return
    winners = random.sample(ok, min(c["winners_n"], len(ok)))
    await storage.contest_close(c["id"])
    names = []
    for w in winners:
        try:
            u = await bot.get_chat(w, request_timeout=10)
            names.append(f"@{u.username}" if u.username else (u.full_name or f"ID {w}"))
        except Exception:
            names.append(f"ID {w}")
    text = texts.CONTEST_WINNERS.format(prize=c["prize"], winners=", ".join(names), total=len(ok))
    try:
        if c["channel_msg_id"]:
            await bot.edit_message_text(chat_id=config.channel_id, message_id=c["channel_msg_id"],
                                        text=text, parse_mode=ParseMode.HTML)
        else:
            await bot.send_message(chat_id=config.channel_id, text=text, parse_mode=ParseMode.HTML)
    except Exception:
        pass
    for w in winners:
        try:
            await bot.send_message(w, f"🎉 Ты выиграл(а) «{c['prize']}»! Напиши в личку канала для получения приза.")
        except Exception:
            pass
    log.info("Конкурс #%s завершён, победители: %s", c["id"], winners)


async def contest_loop(bot: Bot):
    while True:
        try:
            now = int(datetime.now().timestamp())
            for c in await storage.open_contests():
                if c["deadline"] <= now:
                    await draw_contest(bot, c)
        except Exception as e:
            log.warning("contest_loop: %s", e)
        await asyncio.sleep(60)


# ---------- UTM-ссылки и учёт входов ----------

@router.message(Command("link"))
async def make_link(msg: Message, bot: Bot):
    if not is_admin(msg.from_user.id):
        return
    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await msg.answer("Использование: /link <i>название</i> — например /link tiktok", parse_mode=ParseMode.HTML)
        return
    name = f"src_{parts[1].strip()[:28]}"
    try:
        link = await bot.create_chat_invite_link(chat_id=config.channel_id, name=name)
        await msg.answer(texts.LINK_DONE.format(link=link.invite_link, name=name), parse_mode=ParseMode.HTML)
    except Exception as e:
        await msg.answer(f"❌ Не получилось (боту нужно право на пригласительные ссылки): {e}")


@router.message(Command("sources"))
async def sources(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    rows = await storage.joins_by_source()
    if not rows:
        await msg.answer(texts.SOURCES_EMPTY)
        return
    await msg.answer("🔗 <b>Откуда идут подписчики</b>\n\n" + "\n".join(
        f"• <code>{s}</code> — <b>{n}</b>" for s, n in rows), parse_mode=ParseMode.HTML)


@router.chat_member()
async def on_member_update(ev: ChatMemberUpdated, bot: Bot):
    uid = ev.new_chat_member.user.id
    old, new = ev.old_chat_member.status, ev.new_chat_member.status
    # --- вход в канал: считаем источник ---
    if ev.chat.id == config.channel_id and old in ("left", "kicked") and new == "member":
        src = ""
        if ev.invite_link and ev.invite_link.name:
            src = ev.invite_link.name
        u = ev.new_chat_member.user
        await storage.upsert_user(uid, u.username or "", u.full_name or "", src)
        await storage.log_join(uid, src)
        return
    # --- вход в чат: капча + приветствие ---
    if config.chat_id and ev.chat.id == config.chat_id and old in ("left", "kicked") and new == "member":
        u = ev.new_chat_member.user
        if u.is_bot:
            return
        name = u.full_name or f"@{u.username}" if u.username else f"ID {uid}"
        if config.captcha:
            try:
                await bot.restrict_chat_member(
                    chat_id=config.chat_id, user_id=uid,
                    permissions=ChatPermissions(can_send_messages=False, can_send_media_messages=False,
                                                can_send_other_messages=False, can_add_web_page_previews=False),
                )
                cm = await bot.send_message(chat_id=config.chat_id,
                                            text=texts.CAPTCHA_TEXT.format(name=name),
                                            reply_markup=kb.captcha_kb(uid))
                asyncio.create_task(captcha_timeout(bot, uid, cm.message_id))
                return
            except Exception as e:
                if await storage.get_state("captcha_warn") != "1":
                    await storage.set_state("captcha_warn", "1")
                    log.warning("Капча не работает — дай боту права на баны в чате: %s", e)
        if config.welcome_new:
            try:
                await bot.send_message(chat_id=config.chat_id,
                                       text=texts.WELCOME_CHAT.format(name=name, channel_url=config.channel_url))
            except Exception:
                pass


async def captcha_timeout(bot: Bot, uid: int, captcha_msg_id: int):
    await asyncio.sleep(150)
    try:
        m = await bot.get_chat_member(chat_id=config.chat_id, user_id=uid)
        if m.status == "restricted" and not m.can_send_messages:
            await bot.ban_chat_member(chat_id=config.chat_id, user_id=uid)
            await asyncio.sleep(1)
            await bot.unban_chat_member(chat_id=config.chat_id, user_id=uid)  # кик с правом вернуться
            await bot.send_message(chat_id=config.chat_id, text=texts.CAPTCHA_FAIL)
        try:
            await bot.delete_message(chat_id=config.chat_id, message_id=captcha_msg_id)
        except Exception:
            pass
    except Exception:
        pass


@router.callback_query(F.data.startswith("captcha_"))
async def captcha_ok(cb: CallbackQuery, bot: Bot):
    uid = int(cb.data.split("_")[1])
    if cb.from_user.id != uid and not is_admin(cb.from_user.id):
        await cb.answer("Это кнопка не для тебя 🙂")
        return
    try:
        await bot.restrict_chat_member(
            chat_id=config.chat_id, user_id=uid,
            permissions=ChatPermissions(can_send_messages=True, can_send_media_messages=True,
                                        can_send_other_messages=True, can_add_web_page_previews=True),
        )
        await cb.answer("Добро пожаловать! 🎉")
        try:
            await bot.delete_message(chat_id=config.chat_id, message_id=cb.message.message_id)
        except Exception:
            pass
        if config.welcome_new:
            u = cb.from_user
            name = u.full_name or (f"@{u.username}" if u.username else "друг")
            await bot.send_message(chat_id=config.chat_id,
                                   text=texts.WELCOME_CHAT.format(name=name, channel_url=config.channel_url))
    except Exception:
        await cb.answer("Не получилось — позови админа.", show_alert=True)


# ---------- чат: антиспам + активность ----------

@router.message(F.chat.id == 0)  # заглушка, реальный фильтр ниже
async def _never(msg: Message):
    pass


@router.message()
async def chat_guard(msg: Message, bot: Bot):
    if not config.chat_id or not msg.from_user or (msg.chat.id != config.chat_id):
        return
    if msg.from_user.is_bot:
        return
    await storage.bump_activity(msg.from_user.id, msg.from_user.username or "", msg.from_user.full_name or "")
    if config.antispam and not is_admin(msg.from_user.id) and msg.text:
        low = msg.text.lower()
        if any(w in low for w in config.banwords):
            try:
                await msg.delete()
            except Exception:
                return
            now = datetime.now().timestamp()
            if spam_cooldown.get(msg.from_user.id, 0) < now - 300:
                spam_cooldown[msg.from_user.id] = now
                try:
                    await bot.send_message(chat_id=config.chat_id,
                                           text=texts.SPAM_WARN.format(name=msg.from_user.full_name))
                except Exception:
                    pass


# ---------- викторины / опросы / топ ----------

async def quiz_loop(bot: Bot):
    if not config.chat_id:
        return
    while True:
        try:
            now = datetime.now().strftime("%H:%M")
            if now in config.quiz_times:
                flag = f"quiz_{datetime.now():%Y-%m-%d}_{now}"
                if await storage.get_state(flag) != "1":
                    await storage.set_state(flag, "1")
                    items = C.load_quiz(config.quiz_file)
                    if items:
                        idx = int(await storage.get_state("quiz_idx", "0") or 0) % len(items)
                        q = items[idx]
                        await storage.set_state("quiz_idx", str(idx + 1))
                        await bot.send_poll(chat_id=config.chat_id, question=q["q"], options=q["options"],
                                            type="quiz", correct_option_id=q["correct"],
                                            explanation=q["explanation"] or None, is_anonymous=False)
        except Exception as e:
            log.warning("quiz: %s", e)
        await asyncio.sleep(30)


async def poll_loop(bot: Bot):
    if not config.chat_id:
        return
    while True:
        try:
            now = datetime.now().strftime("%H:%M")
            if now in config.poll_times:
                flag = f"poll_{datetime.now():%Y-%m-%d}_{now}"
                if await storage.get_state(flag) != "1":
                    await storage.set_state(flag, "1")
                    items = C.load_polls(config.polls_file)
                    if items:
                        idx = int(await storage.get_state("poll_idx", "0") or 0) % len(items)
                        p = items[idx]
                        await storage.set_state("poll_idx", str(idx + 1))
                        await bot.send_poll(chat_id=config.chat_id, question=p["q"], options=p["options"],
                                            is_anonymous=False)
        except Exception as e:
            log.warning("poll: %s", e)
        await asyncio.sleep(30)


async def weekly_top_loop(bot: Bot):
    if not config.chat_id or not config.weekly_top:
        return
    while True:
        try:
            now = datetime.now()
            if now.weekday() == config.top_day and now.strftime("%H:%M") == config.top_time:
                flag = f"top_{now:%Y-%m-%d}"
                if await storage.get_state(flag) != "1":
                    await storage.set_state(flag, "1")
                    top = await storage.chat_top(10)
                    if top and top[0][3] > 0:
                        rows = []
                        for i, (_, un, fn, n) in enumerate(top, 1):
                            rows.append(f"{i}. {fn or ('@'+un if un else 'участник')} — {n} 💬")
                        await bot.send_message(chat_id=config.chat_id,
                                               text=texts.WEEKLY_TOP_POST.format(rows="\n".join(rows)),
                                               parse_mode=ParseMode.HTML)
                    await storage.activity_reset()
        except Exception as e:
            log.warning("top: %s", e)
        await asyncio.sleep(30)


# ---------- статистика / отчёты ----------

@router.message(Command("stats"))
async def stats(msg: Message, bot: Bot):
    if not is_admin(msg.from_user.id):
        return
    subs = await subs_count(bot)
    f, l = await storage.subs_first_last(7)
    delta = f"{(l - f):+}" if f is not None and l is not None else "±0"
    await msg.answer(texts.STATS.format(
        subs=subs or "?", delta=delta,
        joins_day=await storage.joins_total(datetime.now().strftime("%Y-%m-%d")),
        joins_all=await storage.joins_total(),
        queue=await storage.queue_len(), contests=len(await storage.open_contests()),
    ), parse_mode=ParseMode.HTML)


@router.message(Command("topchat"))
async def topchat(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    top = await storage.chat_top(10)
    if not top or top[0][3] == 0:
        await msg.answer("В чате пока тихо 🤫")
        return
    rows = [f"{i}. {fn or ('@'+un if un else uid)} — {n}" for i, (uid, un, fn, n) in enumerate(top, 1)]
    await msg.answer("💬 <b>Топ чата</b>\n\n" + "\n".join(rows), parse_mode=ParseMode.HTML)


async def subs_loop(bot: Bot):
    while True:
        try:
            n = await subs_count(bot)
            if n:
                await storage.log_subs(n)
        except Exception as e:
            log.warning("subs: %s", e)
        await asyncio.sleep(6 * 3600)


async def report_loop(bot: Bot):
    sent = ""
    while True:
        try:
            now = datetime.now()
            if now.strftime("%H:%M") == config.report_time and sent != now.strftime("%Y-%m-%d"):
                sent = now.strftime("%Y-%m-%d")
                subs = await subs_count(bot)
                f, l = await storage.subs_first_last(7)
                delta = f"{(l - f):+}" if f is not None and l is not None else "±0"
                rows = await storage.joins_by_source(now.strftime("%Y-%m-%d"))
                src_line = ", ".join(f"{s}: {n}" for s, n in rows) or "входов нет"
                text = (f"📊 <b>Утро в канале</b>\n\n👥 Подписчиков: <b>{subs or '?'}</b> ({delta} за 7 дн.)\n"
                        f"📥 Вчера→сегодня: {src_line}\n📝 Очередь постов: <b>{await storage.queue_len()}</b>\n"
                        f"🎲 Открыто розыгрышей: <b>{len(await storage.open_contests())}</b>")
                for aid in config.admin_ids:
                    try:
                        await bot.send_message(aid, text, parse_mode=ParseMode.HTML)
                    except Exception:
                        pass
        except Exception as e:
            log.warning("report: %s", e)
        await asyncio.sleep(30)


# ---------- main ----------

async def main():
    if not config.bot_token or not config.channel_id:
        print("❌ Заполни BOT_TOKEN и CHANNEL_ID в growth/.env")
        return
    await storage.init_db(config.db_path)
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    for coro in (autopost_loop(bot), contest_loop(bot), quiz_loop(bot), poll_loop(bot),
                 weekly_top_loop(bot), subs_loop(bot), report_loop(bot)):
        asyncio.create_task(coro)
    me = await bot.get_me()
    n = await subs_count(bot)
    print(f"🚀 @{me.username} запущен. Подписчиков: {n}. Очередь: {await storage.queue_len()}")
    print("📥 Перешли мне посты — буду публиковать их по расписанию.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
