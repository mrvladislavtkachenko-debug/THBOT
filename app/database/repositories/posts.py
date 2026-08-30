"""Post repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Post, PostAnalysis


class PostRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, post_id: UUID) -> Post | None:
        return await self._session.get(Post, post_id)

    async def get_by_message_id(
        self, channel_id: UUID, message_id: int
    ) -> Post | None:
        result = await self._session.execute(
            select(Post).where(
                Post.channel_id == channel_id,
                Post.telegram_message_id == message_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(self, post: Post) -> Post:
        existing = await self.get_by_message_id(post.channel_id, post.telegram_message_id)
        if existing is not None:
            for field in ("text", "date", "views", "reactions", "comments", "forwards",
                          "post_url", "media_type"):
                setattr(existing, field, getattr(post, field))
            await self._session.flush()
            return existing
        self._session.add(post)
        await self._session.flush()
        return post

    async def list_by_channel(self, channel_id: UUID, limit: int = 100) -> list[Post]:
        result = await self._session.execute(
            select(Post)
            .where(Post.channel_id == channel_id)
            .order_by(Post.date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_analysis(self, post_id: UUID) -> PostAnalysis | None:
        result = await self._session.execute(
            select(PostAnalysis).where(PostAnalysis.post_id == post_id)
        )
        return result.scalar_one_or_none()

    async def save_analysis(self, analysis: PostAnalysis) -> None:
        self._session.add(analysis)
        await self._session.flush()
