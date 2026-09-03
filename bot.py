"""
THBOT — бот для роста Telegram-канала (экспертная ниша).
Механики: проверка подписки + лид-магнит + рефералка с уровнями + рейтинг + рассылка.

Запуск:
    1. cp .env.example .env  (и заполни BOT_TOKEN, CHANNEL_ID, ADMIN_IDS)
    2. pip install -r requirements.txt
    3. python bot.py

Важно: добавь бота в АДМИНИСТРАТОРЫ канала (иначе проверка подписки не сработает).
"""
import asyncio
import csv
import io
import logging

from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, BufferedInputFile

import database as db
import texts
import keyboards as kb
from config import config

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("thbot")

router = Router()


class Broadcast(StatesGroup):
    waiting_message = State()


# ---------- helpers ----------

async def is_subscribed(bot: Bot, user_id: int) -> bool:
    """Проверка подписки через getChatMember. Бот должен быть админом канала."""
    try:
        m = await bot.get_chat_member(chat_id=config.chat_id, user_id=user_id)
        return m.status in ("member", "administrator", "creator")
    except Exception as e:
        log.warning("get_chat_member failed: %s", e)
        return False


async def sync_subscription(bot: Bot, user_id: int) -> bool:
    ok = await is_subscribed(bot, user_id)
    await db.set_subscribed(user_id, ok)
    return ok


def ref_link(bot_username: str, user_id: int) -> str:
    return f"https://t.me/{bot_username}?start=ref_{user_id}"


def display_name(username: str, full_name: str, uid: int) -> str:
    if full_name:
        return full_name
    if username:
        return f"@{username}"
    return f"user{uid}"


async def next_level_info(count: int) -> tuple[int | None, int]:
    """Следующий порог и сколько осталось. (None, 0) если максимум взят."""
    for lvl in sorted(config.levels):
        if count < lvl:
            return lvl, lvl - count
    return None, 0


# ---------- /start ----------

@router.message(CommandStart())
async def cmd_start(msg: Message, bot: Bot):
    uid = msg.from_user.id
    uname = msg.from_user.username or ""
    fname = msg.from_user.full_name or ""

    user = await db.upsert_user(uid, uname, fname)

    # --- реферальный хвост ?start=ref_123 ---
    ref_id = None
    if msg.text and "ref_" in msg.text:
        try:
            ref_id = int(msg.text.split("ref_")[1].split()[0].split("_")[0])
        except (ValueError, IndexError):
            ref_id = None
    if ref_id and not user.get("referrer_id"):
        ok = await db.try_set_referrer(uid, ref_id)
        if ok:
            # уведомляем пригласившего (пока без +1 — засчитаем после подписки)
            try:
                await bot.send_message(
                    ref_id,
                    f"👀 По твоей ссылке пришёл <b>{display_name(uname, fname, uid)}</b>! "
                    f"Балл начислится, когда он подпишется на канал.",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass

    sub = await sync_subscription(bot, uid)

    if not sub:
        await msg.answer(
            texts.WELCOME_NEW, parse_mode=ParseMode.HTML, reply_markup=kb.sub_keyboard()
        )
        await msg.answer(
            texts.NEED_SUBSCRIBE.format(channel_url=config.channel_url),
            parse_mode=ParseMode.HTML,
        )
        return

    # подписан — если пришёл по рефке, уведомляем реферера о +1
    if ref_id:
        count = await db.valid_referrals_count(ref_id)
        try:
            await bot.send_message(
                ref_id,
                texts.REFERRER_BONUS.format(name=display_name(uname, fname, uid), count=count),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        me = await bot.get_me()
        # новичку — кто его пригласил
        try:
            ref_user = await db.get_user(ref_id)
            if ref_user:
                await msg.answer(
                    texts.REFERRED_THANKS.format(
                        name=display_name(ref_user.get("username", ""), ref_user.get("full_name", ""), ref_id)
                    )
                )
        except Exception:
            pass
        _ = me  # noqa

    await msg.answer(texts.SUB_OK if ref_id else texts.WELCOME_BACK, parse_mode=ParseMode.HTML)
    await msg.answer("Меню 👇", reply_markup=kb.main_menu())


@router.callback_query(F.data == "check_sub")
async def cb_check_sub(cb: CallbackQuery, bot: Bot):
    uid = cb.from_user.id
    sub = await sync_subscription(bot, uid)
    if not sub:
        await cb.answer("Подписку пока не вижу 😔", show_alert=True)
        try:
            await cb.message.answer(
                texts.SUB_FAIL.format(channel_url=config.channel_url),
                parse_mode=ParseMode.HTML, reply_markup=kb.sub_keyboard(),
            )
        except Exception:
            pass
        return
    # засчитываем рефереру
    count = 0
    ref_id = await db.get_referrer_of(uid)
    if ref_id:
        count = await db.valid_referrals_count(ref_id)
        try:
            u = await db.get_user(uid)
            await bot.send_message(
                ref_id,
                texts.REFERRER_BONUS.format(
                    name=display_name(u.get("username", ""), u.get("full_name", ""), uid), count=count
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
    await cb.answer("Подписка подтверждена! 🎉", show_alert=True)
    try:
        await cb.message.answer(texts.SUB_OK, parse_mode=ParseMode.HTML)
        await cb.message.answer("Меню 👇", reply_markup=kb.main_menu())
    except Exception:
        pass


# ---------- подарки ----------

def gift_status(count: int) -> str:
    lines = []
    for lvl in sorted(config.levels):
        g = config.gifts.get(lvl)
        name = g.name if g else f"Уровень {lvl}"
        mark = "✅" if count >= lvl else "🔒"
        cond = f" — нужно {lvl} друзей" if lvl > 0 else " — за подписку"
        lines.append(f"{mark} <b>{name}</b>{cond}")
    return "\n".join(lines)


@router.message(F.text == "🎁 Мой подарок")
async def gifts(msg: Message, bot: Bot):
    uid = msg.from_user.id
    sub = await sync_subscription(bot, uid)
    if not sub:
        await msg.answer(
            texts.GIFT_LOCKED_SUB.format(channel_url=config.channel_url),
            reply_markup=kb.sub_keyboard(),
        )
        return
    count = await db.valid_referrals_count(uid)
    lines = [f"🎁 <b>Твои подарки</b> (друзей: <b>{count}</b>)\n"]
    for lvl in sorted(config.levels):
        g = config.gifts.get(lvl)
        if not g:
            continue
        if count >= lvl:
            lines.append(f"\n✅ <b>{g.name}</b>\n👉 Забрать: {g.url}")
            if g.desc:
                lines.append(g.desc)
        else:
            lines.append(f"\n🔒 <b>{g.name}</b> — откроется за <b>{lvl}</b> друзей (у тебя {count})")
    lines.append("\n\nХочешь следующий уровень? Жми «👥 Пригласить друзей».")
    await msg.answer("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=kb.gift_keyboard())


# ---------- пригласить ----------

@router.message(F.text == "👥 Пригласить друзей")
async def invite(msg: Message, bot: Bot):
    uid = msg.from_user.id
    sub = await sync_subscription(bot, uid)
    if not sub:
        await msg.answer(
            texts.GIFT_LOCKED_SUB.format(channel_url=config.channel_url),
            reply_markup=kb.sub_keyboard(),
        )
        return
    me = await bot.get_me()
    link = ref_link(me.username, uid)
    count = await db.valid_referrals_count(uid)
    nxt, left = await next_level_info(count)
    if nxt is None:
        text = texts.INVITE_NO_NEXT.format(ref_link=link, count=count)
    else:
        text = texts.INVITE_TEXT.format(ref_link=link, count=count, next_level=nxt, left=left)
    await msg.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb.invite_keyboard())


@router.callback_query(F.data == "go_invite")
async def cb_invite(cb: CallbackQuery, bot: Bot):
    me = await bot.get_me()
    link = ref_link(me.username, cb.from_user.id)
    count = await db.valid_referrals_count(cb.from_user.id)
    nxt, left = await next_level_info(count)
    text = texts.INVITE_NO_NEXT.format(ref_link=link, count=count) if nxt is None else \
        texts.INVITE_TEXT.format(ref_link=link, count=count, next_level=nxt, left=left)
    await cb.message.answer(text, parse_mode=ParseMode.HTML)
    await cb.answer()


# ---------- рейтинг ----------

@router.message(F.text == "🏆 Рейтинг")
async def rating(msg: Message):
    await send_rating(msg)


async def send_rating(msg_or_cb_message: Message, viewer_id: int | None = None):
    top = await db.get_top(10)
    viewer = viewer_id or msg_or_cb_message.chat.id
    if not top or all(c == 0 for _, _, _, c in top):
        await msg_or_cb_message.answer(texts.RATING_EMPTY)
        return
    rows = []
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, uname, fname, cnt) in enumerate(top, start=1):
        medal = medals[i - 1] if i <= 3 else f"{i}."
        name = fname or (f"@{uname}" if uname else f"ID {uid}")
        # лёгкая анонимизация чужих
        rows.append(f"{medal} {name} — <b>{cnt}</b>")
    place = await db.get_place(viewer)
    me_count = await db.valid_referrals_count(viewer)
    await msg_or_cb_message.answer(
        texts.RATING_TITLE.format(rows="\n".join(rows), place=place, count=me_count),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "go_rating")
async def cb_rating(cb: CallbackQuery):
    await send_rating(cb.message, viewer_id=cb.from_user.id)
    await cb.answer()


# ---------- как работает ----------

@router.message(F.text == "ℹ️ Как это работает")
async def how(msg: Message):
    lvls = sorted(config.levels)
    l0, l1, l2 = (lvls + [0, 3, 10])[:3]
    await msg.answer(
        texts.HOW_IT_WORKS.format(
            g0=config.gifts.get(l0, config.gifts[0]).name,
            l1=l1, g1=config.gifts.get(l1, config.gifts[3]).name,
            l2=l2, g2=config.gifts.get(l2, config.gifts[10]).name,
        ),
        parse_mode=ParseMode.HTML,
    )


# ---------- админка ----------

def is_admin(uid: int) -> bool:
    return uid in config.admin_ids


@router.message(Command("admin"))
async def admin_help(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    await msg.answer(texts.ADMIN_HELP, parse_mode=ParseMode.HTML)


@router.message(Command("stats"))
async def stats(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    s = await db.get_stats()
    await msg.answer(texts.STATS.format(**s), parse_mode=ParseMode.HTML)


@router.message(Command("top"))
async def top_cmd(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    await send_rating(msg, viewer_id=msg.from_user.id)


@router.message(Command("export"))
async def export_cmd(msg: Message, bot: Bot):
    if not is_admin(msg.from_user.id):
        return
    rows = await db.export_rows()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["user_id", "username", "full_name", "referrer_id", "is_subscribed", "valid_refs"])
    for r in rows:
        w.writerow([r["user_id"], r["username"], r["full_name"], r["referrer_id"], r["is_subscribed"], r["refs"]])
    data = buf.getvalue().encode("utf-8-sig")
    await msg.answer_document(BufferedInputFile(data, filename="users.csv"), caption=f"👥 Всего: {len(rows)}")


@router.message(Command("cancel"))
async def cancel(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(texts.BROADCAST_CANCEL)


@router.message(Command("broadcast"))
async def broadcast_start(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    # /broadcast ответом на сообщение = разослать его сразу
    if msg.reply_to_message:
        await do_broadcast(msg, msg.reply_to_message)
        return
    await state.set_state(Broadcast.waiting_message)
    await msg.answer(texts.BROADCAST_ASK)


@router.message(Broadcast.waiting_message)
async def broadcast_go(msg: Message, state: FSMContext, bot: Bot):
    if not is_admin(msg.from_user.id):
        return
    if msg.text == "/cancel":
        await state.clear()
        await msg.answer(texts.BROADCAST_CANCEL)
        return
    await state.clear()
    await do_broadcast(msg, msg)


async def do_broadcast(trigger: Message, source: Message):
    ids = await db.get_all_user_ids()
    ok, fail = 0, 0
    status = await trigger.answer(f"🚀 Рассылка {len(ids)} пользователям... 0/{len(ids)}")
    bot = trigger.bot
    for i, uid in enumerate(ids, start=1):
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=source.chat.id, message_id=source.message_id)
            ok += 1
        except Exception:
            fail += 1
        if i % 20 == 0:
            try:
                await status.edit_text(f"🚀 Рассылка... {i}/{len(ids)}")
            except Exception:
                pass
            await asyncio.sleep(0.5)
        else:
            await asyncio.sleep(0.04)
    from aiogram.enums import ParseMode as PM
    await trigger.answer(texts.BROADCAST_DONE.format(ok=ok, fail=fail), parse_mode=PM.HTML)


# ---------- запуск ----------

async def main():
    if not config.bot_token:
        print("❌ Нет BOT_TOKEN. Скопируй .env.example в .env и вставь токен от @BotFather.")
        return
    if not config.channel_id:
        print("❌ Нет CHANNEL_ID в .env.")
        return
    await db.init_db(config.db_path)
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    me = await bot.get_me()
    print(f"🤖 @{me.username} запущен. Канал: {config.channel_url}. Админы: {sorted(config.admin_ids) or '—'}")
    print("⚠️  Не забудь добавить бота в администраторы канала!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
