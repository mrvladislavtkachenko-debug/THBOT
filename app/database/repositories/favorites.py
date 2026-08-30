"""Favorites repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import Channel, Favorite


class FavoriteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user_id: UUID, channel_id: UUID) -> bool:
        existing = await self.get(user_id, channel_id)
        if existing is not None:
            return False
        fav = Favorite(user_id=user_id, channel_id=channel_id)
        self._session.add(fav)
        await self._session.flush()
        return True

    async def remove(self, user_id: UUID, channel_id: UUID) -> bool:
        fav = await self.get(user_id, channel_id)
        if fav is None:
            return False
        await self._session.delete(fav)
        await self._session.flush()
        return True

    async def get(self, user_id: UUID, channel_id: UUID) -> Favorite | None:
        result = await self._session.execute(
            select(Favorite).where(
                Favorite.user_id == user_id,
                Favorite.channel_id == channel_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: UUID) -> list[Favorite]:
        result = await self._session.execute(
            select(Favorite)
            .options(selectinload(Favorite.channel))
            .where(Favorite.user_id == user_id)
            .order_by(Favorite.created_at.desc())
        )
        return list(result.scalars().all())
