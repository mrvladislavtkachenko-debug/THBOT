"""Сбор данных канала через публичную веб-версию Telegram: https://t.me/s/<username>.

Bot API не умеет читать чужие каналы, а поднимать user-аккаунт Telethon
в MVP не хотим (серая зона ToS). Веб-страница t.me/s/<username> доступна
без авторизации и содержит последние ~20 постов; более старые догружаются
через `?before=<id поста>`.

Что достаём:
- метаданные канала: название, описание, число подписчиков;
- посты: id, ссылка, дата (UTC), текст/подпись, просмотры, реакции,
  признак репоста, тип медиа.

CLI-проверка без Telegram и LLM:
    python -m thbot.parser molyanov_blog
    python -m thbot.parser molyanov_blog --limit 40
"""
from __future__ import annotations

import asyncio
import re
import sys
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

WEB_BASE = "https://t.me/s/"
USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
LINK_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/(?:s/)?(?:@)?([A-Za-z][A-Za-z0-9_]{3,31})(?:/(\d+))?",
)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class ChannelNotFoundError(Exception):
    """Канал не существует, забанен или это не публичный канал."""


class PrivateChannelError(Exception):
    """Приватный канал (инвайт-ссылка t.me/+...) — t.me/s не отдаёт контент."""


def normalize_channel_ref(text: str) -> str:
    """Принимает @name, t.me/name, t.me/s/name, https://t.me/name/123 → username."""
    text = text.strip()
    if text.startswith("@"):
        name = text[1:]
        if USERNAME_RE.match(name):
            return name
        raise ChannelNotFoundError(f"«{text}» не похоже на имя канала.")

    m = LINK_RE.search(text)
    if m:
        if "/+" in text or "t.me/+" in text or "joinchat" in text:
            raise PrivateChannelError(
                "Это приватный канал (ссылка-инвайт). MVP умеет только публичные "
                "каналы вида t.me/username — поддержка приватных будет позже."
            )
        return m.group(1)

    # Может, просто username без @
    if USERNAME_RE.match(text):
        return text

    raise ChannelNotFoundError(
        "Не понял ссылку. Пришлите, например: https://t.me/molyanov_blog или @molyanov_blog"
    )


def _parse_count(text: str | None) -> int | None:
    """'3.63K' → 3630, '1.2M' → 1_200_000, '1 234' → 1234."""
    if not text:
        return None
    text = text.strip().replace(" ", "").replace(",", ".")
    m = re.match(r"^([\d.]+)\s*([KMkm])?$", text)
    if not m:
        return None
    value = float(m.group(1))
    mult = {"k": 1_000, "m": 1_000_000}.get((m.group(2) or "").lower(), 1)
    return int(value * mult)


@dataclass
class Post:
    id: int
    url: str
    date_iso: str | None
    text: str
    views: int | None
    reactions: dict[str, int] = field(default_factory=dict)
    is_repost: bool = False
    media_type: str | None = None  # photo | video | audio | voice | document | poll | media
    service: bool = False

    @property
    def reactions_total(self) -> int:
        return sum(self.reactions.values())


@dataclass
class ChannelData:
    username: str
    title: str
    description: str
    subscribers: int | None
    url: str
    posts: list[Post]


def _media_type(msg: Tag) -> str | None:
    if msg.select_one(".tgme_widget_message_poll"):
        return "poll"
    if msg.select_one(".tgme_widget_message_voice_player"):
        return "voice"
    if msg.select_one(".tgme_widget_message_audio_player"):
        return "audio"
    if msg.select_one(".tgme_widget_message_video, .tgme_widget_message_video_player"):
        return "video"
    if msg.select_one(".tgme_widget_message_document"):
        return "document"
    if msg.select_one(".tgme_widget_message_photo_wrap, .tgme_widget_message_sticker, .media_supported_cont"):
        return "photo" if msg.select_one(".tgme_widget_message_photo_wrap") else "media"
    return None


def _parse_reactions(msg: Tag) -> dict[str, int]:
    reactions: dict[str, int] = {}
    container = msg.select_one(".tgme_widget_message_reactions")
    if container:
        for item in container.select("span.tgme_widget_message_reaction, .message_reaction"):
            emoji_el = item.select_one("i.emoji, .emoji")
            count_el = item.select_one("b")
            if emoji_el and count_el:
                count = _parse_count(count_el.get_text())
                if count is not None:
                    reactions[emoji_el.get_text().strip()] = count
    return reactions


def _clean_text(el: Tag | None) -> str:
    if el is None:
        return ""
    text = el.get_text("\n")
    # схлопываем пустые строки и лишние пробелы
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def _parse_page(html: str, username: str) -> tuple[list[Post], int | None]:
    """Разбирает одну страницу t.me/s/... → (посты, id для пагинации `before`)."""
    soup = BeautifulSoup(html, "html.parser")
    posts: list[Post] = []

    for msg in soup.select("div.tgme_widget_message"):
        data_post = msg.get("data-post") or ""
        # data-post вида "username/123"; берём только сообщения этого канала
        if "/" not in data_post:
            continue
        try:
            post_id = int(data_post.rsplit("/", 1)[1])
        except ValueError:
            continue

        service = bool(msg.select_one(".tgme_widget_message_service"))
        text_el = msg.select_one(".tgme_widget_message_text")
        text = _clean_text(text_el)
        if service and not text:
            continue  # «X pinned a message» и т.п. — не контент

        date_el = msg.select_one(".tgme_widget_message_date time")
        date_iso = date_el.get("datetime") if date_el else None

        views_el = msg.select_one(".tgme_widget_message_views")
        views = _parse_count(views_el.get_text() if views_el else None)

        posts.append(
            Post(
                id=post_id,
                url=f"https://t.me/{data_post}",
                date_iso=date_iso,
                text=text,
                views=views,
                reactions=_parse_reactions(msg),
                is_repost=bool(msg.select_one(".tgme_widget_message_forwarded_from")),
                media_type=_media_type(msg),
                service=service,
            )
        )

    # ссылка на более старые сообщения: <a class="tme_messages_more" href="/s/name?before=123">
    before_id: int | None = None
    for link in soup.select("a.tme_messages_more[href]"):
        m = re.search(r"before=(\d+)", link["href"])
        if m:
            cand = int(m.group(1))
            before_id = cand if before_id is None else min(before_id, cand)

    return posts, before_id


async def fetch_channel(
    username: str, limit: int = 100, client: httpx.AsyncClient | None = None
) -> ChannelData:
    """Собирает метаданные канала и до `limit` последних постов."""
    username = username.lstrip("@")
    own_client = client is None
    client = client or httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=httpx.Timeout(20.0),
    )

    try:
        url = f"{WEB_BASE}{username}"
        resp = await client.get(url)
        first_html = resp.text

        soup = BeautifulSoup(first_html, "html.parser")
        header = soup.select_one(".tgme_channel_info_header_title, .tgme_page_title")
        if resp.status_code >= 400 or header is None:
            raise ChannelNotFoundError(
                f"Канал @{username} не найден: он не существует, забанен "
                "или не является публичным каналом."
            )

        title = header.get_text(strip=True)

        desc_el = soup.select_one(".tgme_channel_info_description")
        description = _clean_text(desc_el)

        subscribers: int | None = None
        counters = soup.select(".tgme_channel_info_counter")
        if counters:
            value_el = counters[0].select_one(".counter_value")
            subscribers = _parse_count(value_el.get_text() if value_el else None)

        all_posts: dict[int, Post] = {}
        posts, before_id = _parse_page(first_html, username)
        for p in posts:
            all_posts[p.id] = p

        # догружаем старые посты пачками по ~20
        pages = 0
        while before_id and len(all_posts) < limit and pages < 20:
            pages += 1
            resp = await client.get(f"{url}?before={before_id}")
            if resp.status_code >= 400:
                break
            page_posts, before_id = _parse_page(resp.text, username)
            if not page_posts:
                break
            new_ids = 0
            for p in page_posts:
                if p.id not in all_posts:
                    all_posts[p.id] = p
                    new_ids += 1
            if new_ids == 0:
                break  # защита от зацикливания
            await asyncio.sleep(0.4)  # вежливая пауза между страницами

        ordered = sorted(all_posts.values(), key=lambda p: p.id)
        return ChannelData(
            username=username,
            title=title,
            description=description,
            subscribers=subscribers,
            url=f"https://t.me/{username}",
            posts=ordered[-limit:],
        )
    finally:
        if own_client:
            await client.aclose()


async def _main() -> None:
    """CLI для проверки парсера: python -m thbot.parser <username> [--limit N]."""
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    limit = 100
    if "--limit" in sys.argv:
        i = sys.argv.index("--limit")
        limit = int(sys.argv[i + 1])
    if not args:
        print("Использование: python -m thbot.parser <username> [--limit N]")
        return

    username = normalize_channel_ref(args[0])
    channel = await fetch_channel(username, limit=limit)
    print(f"Канал: {channel.title} (@{channel.username})")
    print(f"Подписчиков: {channel.subscribers}")
    print(f"Описание: {channel.description[:200]}")
    print(f"Собрано постов: {len(channel.posts)}")
    print("-" * 60)
    for p in channel.posts[-5:]:
        reactions = " ".join(f"{e}{c}" for e, c in p.reactions.items())
        flags = []
        if p.is_repost:
            flags.append("repost")
        if p.media_type:
            flags.append(p.media_type)
        print(f"#{p.id} [{p.date_iso}] 👁{p.views} {reactions} {' '.join(flags)}")
        print(p.text[:300].replace("\n", " "))
        print(p.url)
        print("-" * 60)


if __name__ == "__main__":
    asyncio.run(_main())
