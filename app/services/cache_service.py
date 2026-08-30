"""Analysis caching.

If a channel was analyzed recently (within ``ANALYSIS_CACHE_HOURS``) the
cached analysis is returned instead of triggering a fresh, expensive AI
run. Uses Redis when available; otherwise falls back to an in-process
TTL cache (suitable for a single worker).
"""

from __future__ import annotations

import json
import time
from typing import Any

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger("cache")


class AnalysisCache:
    """TTL cache keyed by ``channel:username``."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._redis = None
        self._mem: dict[str, tuple[float, Any]] = {}
        self._ttl = self._settings.analysis_cache_hours * 3600
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(self._settings.redis_url, decode_responses=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis unavailable, using in-memory cache: %s", exc)
            self._redis = None

    def _key(self, username: str) -> str:
        return f"tgchan:analysis:{username.lower()}"

    async def get(self, username: str) -> dict[str, Any] | None:
        key = self._key(username)
        if self._redis is not None:
            try:
                raw = await self._redis.get(key)
                if raw:
                    return json.loads(raw)
            except Exception as exc:  # noqa: BLE001
                logger.warning("redis get failed: %s", exc)
        # fallback to memory
        item = self._mem.get(key)
        if item:
            expires, value = item
            if time.time() < expires:
                return value
            del self._mem[key]
        return None

    async def set(self, username: str, payload: dict[str, Any]) -> None:
        key = self._key(username)
        if self._redis is not None:
            try:
                await self._redis.setex(key, self._ttl, json.dumps(payload, default=str))
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("redis set failed: %s", exc)
        self._mem[key] = (time.time() + self._ttl, payload)

    async def invalidate(self, username: str) -> None:
        key = self._key(username)
        if self._redis is not None:
            try:
                await self._redis.delete(key)
            except Exception as exc:  # noqa: BLE001
                logger.warning("redis delete failed: %s", exc)
        self._mem.pop(key, None)
