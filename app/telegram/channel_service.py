"""Channel metadata + posts collection service.

Thin layer over the MTProto client that turns raw channel/username input
into validated :class:`ChannelInfo` and post payloads. If MTProto is not
configured it falls back to raising a clear configuration error.
"""

from __future__ import annotations

import logging

from app.config import get_settings
from app.schemas import ChannelInfo, PostData
from app.telegram.client import (
    TelegramChannelNotFound,
    TelegramClientError,
    TelegramClientWrapper,
)
from app.utils.validators import is_valid_username

logger = logging.getLogger("telegram.service")


class ChannelService:
    """Collects channel information and recent posts."""

    def __init__(self, client: TelegramClientWrapper | None = None) -> None:
        self._client = client

    def _get_client(self) -> TelegramClientWrapper:
        if self._client is None:
            if not get_settings().telegram_enabled:
                raise TelegramClientError(
                    "Telegram API не настроен (TELEGRAM_API_ID / TELEGRAM_API_HASH)"
                )
            self._client = TelegramClientWrapper()
        return self._client

    async def validate_and_get_info(self, username: str) -> ChannelInfo:
        if not is_valid_username(username):
            raise TelegramChannelNotFound(f"некорректное имя канала: @{username}")
        client = self._get_client()
        return await client.get_channel_info(username)

    async def get_posts(self, username: str, limit: int) -> list[PostData]:
        client = self._get_client()
        return await client.get_recent_posts(username, limit=limit)

    async def get_message_count(self, username: str) -> int | None:
        client = self._get_client()
        return await client.get_message_count(username)

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
