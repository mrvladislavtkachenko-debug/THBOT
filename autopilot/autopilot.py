"""
THBOT Autopilot — полностью автоматическое привлечение подписчиков.

Что делает сам, без тебя:
  1. Следит за каналами-донорами (твоя ниша) и оставляет умные комментарии
     под свежими постами — люди видят коммент, заходят в профиль/канал и подписываются.
  2. Ведёт твой канал по расписанию (посты из posts.txt).
  3. Замеряет подписчиков каждые N часов и присылает отчёт в Избранное.

Запуск:
  1. cp .env.example .env  (в autopilot/) и заполни API_ID/API_HASH с my.telegram.org
  2. pip install -r requirements.txt
  3. python autopilot.py   (первый раз попросит телефон и код из Telegram)
  4. Первые 2-3 дня DRY_RUN=1 — только лог, ничего не отправляет. Потом DRY_RUN=0.

Управление из Избранного (пишешь себе):
  /stat   — статистика (комменты + подписчики)
  /pause  — пауза комментирования | /resume — продолжить
  /dry on|off — вкл/выкл тестовый режим на лету
"""
import asyncio
import logging
import random
from datetime import datetime, timedelta

from telethon import TelegramClient, events
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetDiscussionMessageRequest

import storage
import templates
from config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("autopilot.log", encoding="utf-8")],
)
log = logging.getLogger("autopilot")

donor_entities: dict[str, object] = {}
send_as_entity = None
my_channel_entity = None


# ---------- helpers ----------

def in_active_hours() -> bool:
    h = datetime.now().hour
    if config.active_start <= config.active_end:
        return config.active_start <= h < config.active_end
    return h >= config.active_start or h < config.active_end


async def paused() -> bool:
    return await storage.get_state("paused", "0") == "1"


async def dry() -> bool:
    override = await storage.get_state("dry", "")
    if override == "1":
        return True
    if override == "0":
        return False
    return config.dry_run


async def subs_count(client: TelegramClient) -> int | None:
    try:
        full = await client(GetFullChannelRequest(my_channel_entity))
        return full.full_chat.participants_count
    except Exception as e:
        log.warning("subs_count failed: %s", e)
        return None


async def send_comment(client: TelegramClient, channel_entity, channel_msg_id: int, text: str):
    """Оставить комментарий под постом канала. Сначала быстрый способ, потом запасной."""
    kwargs = {}
    if send_as_entity is not None:
        kwargs["send_as"] = send_as_entity
    # Способ 1: Telethon сам найдёт ветку обсуждения
    try:
        full = await client(GetFullChannelRequest(channel_entity))
        linked_id = full.full_chat.linked_chat_id
        if not linked_id:
            raise RuntimeError("у канала нет привязанной группы обсуждений — комментировать некуда")
        try:
            return await client.send_message(linked_id, text, comment_to=channel_msg_id, **kwargs)
        except TypeError:
            # старая версия telethon без send_as
            return await client.send_message(linked_id, text, comment_to=channel_msg_id)
    except Exception as e1:
        log.info("comment fast-path failed (%s), пробую через discussion message", e1)
    # Способ 2: явно находим сообщение в группе обсуждений и отвечаем на него
    disc = await client(GetDiscussionMessageRequest(peer=channel_entity, msg_id=channel_msg_id))
    if not disc.messages:
        raise RuntimeError("не нашёл ветку обсуждений")
    stub_id = disc.messages[0].id
    linked = disc.chats[0] if disc.chats else None
    if linked is None:
        full = await client(GetFullChannelRequest(channel_entity))
        linked = full.full_chat.linked_chat_id
    try:
        return await client.send_message(linked, text, reply_to=stub_id, **kwargs)
    except TypeError:
        return await client.send_message(linked, text, reply_to=stub_id)


# ---------- commenting pipeline ----------

async def handle_new_post(client: TelegramClient, donor: str, msg):
    """Новый пост у донора: фильтруем и ставим в очередь с человеческой задержкой."""
    text = msg.text or ""
    ok, reason = templates.post_allowed(text, config.stopwords)
    if not ok:
        log.info("⏭ %s post %s пропущен (%s)", donor, msg.id, reason)
        return
    if await storage.already_commented(donor, msg.id):
        return
    delay = random.randint(config.comment_delay_min * 60, config.comment_delay_max * 60)
    log.info("📥 %s post %s в очереди, коммент через ~%s мин", donor, msg.id, delay // 60)
    await asyncio.sleep(delay)
    await try_comment(client, donor, msg)


async def try_comment(client: TelegramClient, donor: str, msg):
    if await paused():
        log.info("⏸ пауза — коммент %s/%s отложен", donor, msg.id)
        return
    if not in_active_hours():
        log.info("🌙 неактивные часы — коммент %s/%s пропущен", donor, msg.id)
        await storage.log_comment(donor, msg.id, -1, "skipped_night")
        return
    if await storage.comments_today() >= config.max_comments_per_day:
        log.info("🛑 дневной лимит — %s/%s пропущен", donor, msg.id)
        await storage.log_comment(donor, msg.id, -1, "skipped_limit")
        return
    if await storage.comments_today_for_donor(donor) >= config.max_per_donor_per_day:
        log.info("🛑 лимит на донора %s — пост %s пропущен", donor, msg.id)
        await storage.log_comment(donor, msg.id, -1, "skipped_donor_limit")
        return
    if await storage.already_commented(donor, msg.id):
        return

    variants = templates.load_blocks(config.comments_file)
    if not variants:
        log.error("Нет шаблонов в %s!", config.comments_file)
        return
    idx = templates.pick_variant(len(variants), await storage.variant_usage())
    text = templates.render(variants[idx], config.my_channel, send_as_entity is not None)

    if await dry():
        await storage.log_comment(donor, msg.id, idx, "dry")
        log.info("🧪 DRY: %s post %s — «%s...»", donor, msg.id, text[:80].replace("\n", " "))
        return
    # микропауза перед отправкой, как у живого человека
    await asyncio.sleep(random.randint(20, 90))
    try:
        entity = donor_entities.get(donor)
        await send_comment(client, entity, msg.id, text)
        await storage.log_comment(donor, msg.id, idx, "sent")
        log.info("✅ Коммент %s post %s отправлен (шаблон #%s)", donor, msg.id, idx)
    except Exception as e:
        await storage.log_comment(donor, msg.id, idx, "error", str(e))
        log.warning("❌ Коммент %s post %s не ушёл: %s", donor, msg.id, e)


# ---------- autoposting ----------

async def autopost_loop(client: TelegramClient):
    if not config.autopost_enabled or not my_channel_entity:
        return
    if not await storage.get_state("queue_empty_warned", ""):
        pass
    while True:
        try:
            now = datetime.now().strftime("%H:%M")
            today_s = datetime.now().strftime("%Y-%m-%d")
            if now in config.autopost_times and not await paused():
                flag = f"post_{today_s}_{now}"
                if await storage.get_state(flag, "") != "1":
                    await publish_next(client)
                    await storage.set_state(flag, "1")
        except Exception as e:
            log.warning("autopost_loop: %s", e)
        await asyncio.sleep(30)


async def publish_next(client: TelegramClient):
    posts = templates.load_blocks(config.posts_file)
    idx = int(await storage.get_state("queue_index", "0") or 0)
    if idx >= len(posts):
        if await storage.get_state("queue_empty_warned", "") != "1":
            await storage.set_state("queue_empty_warned", "1")
            try:
                await client.send_message("me", "📭 Очередь постов пуста! Добавь посты в posts.txt и сбрось: /reset_queue")
            except Exception:
                pass
            log.warning("Очередь постов пуста")
        return
    text = posts[idx]
    if config.signature:
        text = text + "\n\n" + config.signature
    if await dry():
        log.info("🧪 DRY: автопост #%s не отправлен (тестовый режим)", idx)
        return
    await client.send_message(my_channel_entity, text)
    await storage.set_state("queue_index", str(idx + 1))
    log.info("📝 Автопост #%s опубликован", idx)


# ---------- stats ----------

async def stats_loop(client: TelegramClient):
    while True:
        try:
            if my_channel_entity:
                n = await subs_count(client)
                if n:
                    await storage.log_subs(n)
        except Exception as e:
            log.warning("stats_loop: %s", e)
        await asyncio.sleep(config.subs_check_hours * 3600)


async def report_loop(client: TelegramClient):
    last_report = ""
    while True:
        try:
            now = datetime.now()
            if now.strftime("%H:%M") == config.report_time and last_report != now.strftime("%Y-%m-%d"):
                last_report = now.strftime("%Y-%m-%d")
                await send_report(client)
        except Exception as e:
            log.warning("report_loop: %s", e)
        await asyncio.sleep(30)


async def build_report() -> str:
    series = await storage.subs_series(14)
    cstats = await storage.comments_stats(7)
    lines = ["📊 <b>Отчёт автопилота</b>", ""]
    if series:
        first, last = series[0][1], series[-1][1]
        lines.append(f"👥 Подписчиков: <b>{last}</b> ({last - first:+} за {len(series)} дн.)")
        lines.append("Динамика: " + " → ".join(f"{d[5:]}: {d[1]}" for d in series[-7:]))
    else:
        lines.append("👥 Подписчиков: пока нет данных (проверка каждые "
                     f"{config.subs_check_hours} ч)")
    lines.append("")
    if cstats:
        lines.append("💬 Комментарии: " + ", ".join(f"{d[5:]}: {d[1]}" for d in cstats))
        lines.append(f"Сегодня: <b>{await storage.comments_today()}</b> / лимит {config.max_comments_per_day}")
    else:
        lines.append("💬 Комментариев пока нет")
    lines.append("")
    lines.append(f"Режим: {'🧪 ТЕСТ (DRY_RUN)' if await dry() else '🚀 БОЕВОЙ'}"
                f" | {'⏸ пауза' if await paused() else '▶️ работает'}")
    return "\n".join(lines)


async def send_report(client: TelegramClient):
    try:
        await client.send_message("me", await build_report(), parse_mode="html")
    except Exception as e:
        log.warning("send_report: %s", e)


# ---------- main ----------

async def main():
    if not config.api_id or not config.api_hash:
        print("❌ Нет API_ID/API_HASH. Возьми на https://my.telegram.org -> API development tools")
        return
    await storage.init_db(config.db_path)
    client = TelegramClient(config.session_name, config.api_id, config.api_hash)
    await client.start()
    me = await client.get_me()
    log.info("👤 Вошёл как %s", getattr(me, "username", me.id))

    global send_as_entity, my_channel_entity
    if config.my_channel:
        try:
            my_channel_entity = await client.get_entity(config.my_channel)
            n = await subs_count(client)
            if n:
                await storage.log_subs(n)
                log.info("📊 Канал %s: %s подписчиков", config.my_channel, n)
        except Exception as e:
            log.warning("Нет доступа к MY_CHANNEL %s: %s", config.my_channel, e)
    if config.send_as:
        try:
            send_as_entity = await client.get_entity(config.send_as)
            log.info("💬 Комментарии от имени: %s", config.send_as)
        except Exception as e:
            log.warning("SEND_AS не resolved (%s) — буду комментировать от личного аккаунта", e)

    donors_ok = []
    for d in config.donors:
        try:
            donor_entities[d] = await client.get_entity(d)
            donors_ok.append(d)
        except Exception as e:
            log.warning("Донор %s недоступен: %s", d, e)
    log.info("👀 Слежу за донорами (%s): %s", len(donors_ok), ", ".join(donors_ok) or "—")

    @client.on(events.NewMessage(chats=list(donor_entities.values()) or None))
    async def on_donor_post(event):
        chat = await event.get_chat()
        uname = "@" + (getattr(chat, "username", "") or "")
        donor = uname if uname in donor_entities else str(getattr(chat, "id", "?"))
        asyncio.create_task(handle_new_post(client, donor, event.message))

    @client.on(events.NewMessage(chats=["me"], outgoing=True, pattern=r"^/(stat|pause|resume|dry|reset_queue)"))
    async def on_cmd(event):
        cmd = event.pattern_match.group(1)
        if cmd == "stat":
            await event.reply(await build_report(), parse_mode="html")
        elif cmd == "pause":
            await storage.set_state("paused", "1")
            await event.reply("⏸ Пауза. Комменты и посты остановлены. /resume — продолжить.")
        elif cmd == "resume":
            await storage.set_state("paused", "0")
            await event.reply("▶️ Работаю дальше.")
        elif cmd == "dry":
            arg = (event.text or "").split()[1:] and event.text.split()[1].lower()
            if arg == "on":
                await storage.set_state("dry", "1")
                await event.reply("🧪 Тестовый режим ВКЛ — ничего не отправляю, только лог.")
            elif arg == "off":
                await storage.set_state("dry", "0")
                await event.reply("🚀 Боевой режим — комментирую и публикую по-настоящему.")
            else:
                await event.reply(f"Сейчас: {'🧪 тест' if await dry() else '🚀 боевой'}. /dry on | /dry off")
        elif cmd == "reset_queue":
            await storage.set_state("queue_index", "0")
            await storage.set_state("queue_empty_warned", "")
            await event.reply("📝 Очередь постов сброшена — начну с первого.")

    asyncio.create_task(autopost_loop(client))
    asyncio.create_task(stats_loop(client))
    asyncio.create_task(report_loop(client))

    mode = "🧪 ТЕСТ" if await dry() else "🚀 БОЕВОЙ"
    try:
        await client.send_message(
            "me",
            f"🤖 <b>Автопилот запущен</b> ({mode})\n"
            f"👀 Доноров: {len(donors_ok)}\n"
            f"💬 Лимит: {config.max_comments_per_day}/день\n"
            f"Команды: /stat /pause /resume /dry on|off",
            parse_mode="html",
        )
    except Exception:
        pass
    log.info("🚀 Автопилот работает (%s). Остановка: Ctrl+C", mode)
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
