"""Telegram MTProto client wrapper (Telethon).

Provides a thin async wrapper around a Telethon client that is used only
to *read publicly available* channel metadata and posts. It never attempts
to access private channels or bypass Telegram limits.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    ChatAdminRequiredError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.tl.types import (
    Channel,
    Chat,
    Message,
    User,
)

from app.config import get_settings
from app.schemas import ChannelInfo, PostData

logger = logging.getLogger("telegram.client")


class TelegramChannelNotFound(Exception):
    """Raised when the channel does not exist or is not accessible."""


class TelegramClientError(Exception):
    """Generic Telegram API error."""


class TelegramClientWrapper:
    """Async wrapper around Telethon with a lazily-created client."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.telegram_enabled:
            raise TelegramClientError(
                "Telegram API credentials missing (TELEGRAM_API_ID/HASH)"
            )
        self._client = TelegramClient(
            "tg_session",
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )
        self._connected = False
        self._lock = asyncio.Lock()

    async def _ensure_connected(self) -> None:
        if self._connected:
            return
        async with self._lock:
            if not self._connected:
                await self._client.connect()
                self._connected = True

    async def get_entity(self, username: str) -> Any:
        """Resolve a username into a Telethon entity.

        Raises TelegramChannelNotFound if the channel doesn't exist or is
        private. Raises TelegramClientError for network issues.
        """
        await self._ensure_connected()
        try:
            return await self._client.get_entity(username)
        except (UsernameInvalidError, UsernameNotOccupiedError, ValueError) as exc:
            raise TelegramChannelNotFound(
                f"канал @{username} не найден"
            ) from exc
        except ChannelPrivateError as exc:
            raise TelegramChannelNotFound(
                f"канал @{username} приватный"
            ) from exc
        except ChatAdminRequiredError as exc:
            raise TelegramChannelNotFound(
                f"нет доступа к каналу @{username}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - network/timeout
            logger.warning("Telegram get_entity error for %s: %s", username, exc)
            raise TelegramClientError(f"Telegram API error: {exc}") from exc

    async def get_channel_info(self, username: str) -> ChannelInfo:
        """Fetch channel metadata for a public channel."""
        entity = await self.get_entity(username)

        if isinstance(entity, User):
            raise TelegramChannelNotFound(
                f"@{username} — это пользователь, а не канал"
            )
        if isinstance(entity, Channel):
            if entity.broadcast is False:
                raise TelegramChannelNotFound(
                    f"@{username} — это группа, а не канал"
                )
            # A channel without a public username is accessible only via
            # invite link and is effectively private.
            is_private = not bool(getattr(entity, "username", None))
            return ChannelInfo(
                username=username,
                title=getattr(entity, "title", None),
                description=getattr(entity, "about", None),
                url=f"https://t.me/{username}",
                subscriber_count=getattr(entity, "participants_count", None),
                telegram_channel_id=getattr(entity, "id", None),
                is_group=False,
                is_bot=False,
                is_private=is_private,
            )
        if isinstance(entity, Chat):
            raise TelegramChannelNotFound(
                f"@{username} — это группа, а не канал"
            )
        raise TelegramChannelNotFound(
            f"@{username} не является публичным каналом"
        )

    async def get_recent_posts(
        self, username: str, limit: int = 100
    ) -> list[PostData]:
        """Fetch the latest ``limit`` public posts from a channel."""
        await self._ensure_connected()
        entity = await self.get_entity(username)
        try:
            messages: list[Message] = []
            async for msg in self._client.iter_messages(entity, limit=limit):
                messages.append(msg)
        except ChannelPrivateError as exc:
            raise TelegramChannelNotFound(
                f"канал @{username} приватный или недоступен"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram iter_messages error for %s: %s", username, exc)
            raise TelegramClientError(f"Telegram API error: {exc}") from exc

        posts: list[PostData] = []
        for msg in messages:
            post_url = (
                f"https://t.me/{username}/{msg.id}" if getattr(msg, "id", None) else None
            )
            posts.append(
                PostData(
                    telegram_message_id=msg.id,
                    text=_message_text(msg),
                    date=msg.date,
                    views=getattr(msg, "views", None),
                    reactions=_reaction_count(msg),
                    comments=getattr(msg, "replies", None).replies
                    if getattr(msg, "replies", None) is not None
                    else None,
                    forwards=getattr(msg, "forwards", None),
                    post_url=post_url,
                    media_type=_media_type(msg),
                )
            )
        return posts

    async def get_message_count(self, username: str) -> int | None:
        """Return the total number of messages (posts) in the channel."""
        try:
            entity = await self.get_entity(username)
            return getattr(entity, "messages", None)
        except TelegramChannelNotFound:
            return None

    async def disconnect(self) -> None:
        if self._connected:
            await self._client.disconnect()
            self._connected = False


def _message_text(msg: Message) -> str | None:
    try:
        text = msg.text or msg.message or None
        if text and isinstance(text, str):
            return text
        return None
    except Exception:  # noqa: BLE001
        return None


def _reaction_count(msg: Message) -> int | None:
    try:
        r = msg.reactions
        if r is None:
            return None
        results = getattr(r, "results", None)
        if results is None:
            return None
        return sum(getattr(item, "count", 0) or 0 for item in results)
    except Exception:  # noqa: BLE001
        return None


def _media_type(msg: Message) -> str | None:
    if getattr(msg, "media", None) is None:
        return "text"
    try:
        media = msg.media
        cls = type(media).__name__
        if "Photo" in cls:
            return "photo"
        if "Video" in cls or "Gif" in cls:
            return "video"
        if "Audio" in cls or "Voice" in cls:
            return "audio"
        if "Document" in cls:
            return "document"
        if "Sticker" in cls:
            return "sticker"
        return "media"
    except Exception:  # noqa: BLE001
        return "media"
