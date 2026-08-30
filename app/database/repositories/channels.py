"""Channel repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Channel


class ChannelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, channel_id: UUID) -> Channel | None:
        return await self._session.get(Channel, channel_id)

    async def get_by_username(self, username: str) -> Channel | None:
        result = await self._session.execute(
            select(Channel).where(Channel.username == username.lower())
        )
        return result.scalar_one_or_none()

    async def get_or_create_by_username(self, username: str) -> tuple[Channel, bool]:
        username = username.lower()
        channel = await self.get_by_username(username)
        if channel is None:
            channel = Channel(
                username=username,
                channel_url=f"https://t.me/{username}",
            )
            self._session.add(channel)
            await self._session.flush()
            return channel, True
        return channel, False

    async def update(self, channel: Channel, **fields) -> None:
        for key, value in fields.items():
            setattr(channel, key, value)
        await self._session.flush()

    async def count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(Channel))
        return int(result.scalar_one())

    async def most_analyzed(self, limit: int = 10) -> list[tuple[Channel, int]]:
        from app.database.models import ChannelAnalysis

        stmt = (
            select(Channel, func.count(ChannelAnalysis.id).label("cnt"))
            .join(ChannelAnalysis, ChannelAnalysis.channel_id == Channel.id)
            .group_by(Channel.id)
            .order_by(func.count(ChannelAnalysis.id).desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.all())
