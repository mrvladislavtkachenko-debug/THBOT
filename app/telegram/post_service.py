"""Post persistence and hashing service.

Responsible for turning collected :class:`PostData` into database
``Post`` records, computing content hashes (to skip re-analysis of
unchanged posts) and building the payloads used for AI analysis.
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.database.models import Post
from app.database.repositories.posts import PostRepository
from app.schemas import PostData
from app.utils.text import clean_text


def post_content_hash(text: str | None, date_iso: str | None = None) -> str:
    """Return a stable hash of a post's content (for cache reuse)."""
    payload = f"{clean_text(text)}|{date_iso}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def post_to_payload(post: Post, analysis: Any = None) -> dict[str, Any]:
    """Build the dictionary used for AI channel/scam analysis."""
    return {
        "message_id": post.telegram_message_id,
        "text": post.text or "",
        "date": post.date.isoformat() if post.date else None,
        "views": post.views,
        "reactions": post.reactions,
        "post_type": getattr(analysis, "post_type", None) if analysis else None,
        "topic": getattr(analysis, "topic", None) if analysis else None,
        "quality_score": getattr(analysis, "quality_score", None) if analysis else None,
        "scam_signals": getattr(analysis, "scam_signals", None) if analysis else None,
        "summary": getattr(analysis, "summary", None) if analysis else None,
    }


class PostService:
    """Persists posts and manages analysis payloads."""

    def __init__(self, repository: PostRepository) -> None:
        self._repo = repository

    async def persist(self, channel_id: Any, posts: list[PostData]) -> list[Post]:
        """Upsert collected posts into the database and return them."""
        saved: list[Post] = []
        for data in posts:
            post = Post(
                channel_id=channel_id,
                telegram_message_id=data.telegram_message_id,
                text=data.text,
                date=data.date,
                views=data.views,
                reactions=data.reactions,
                comments=data.comments,
                forwards=data.forwards,
                post_url=data.post_url,
                media_type=data.media_type,
            )
            saved.append(await self._repo.upsert(post))
        return saved
