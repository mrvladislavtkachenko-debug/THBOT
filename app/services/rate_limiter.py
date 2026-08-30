"""User rate limiting for free analyses.

Counts analyses per user per day. When ``FREE_ANALYSES_PER_DAY`` is 0
the limit is unlimited.
"""

from __future__ import annotations

import time
from typing import Any

from app.config import get_settings


class RateLimitExceeded(Exception):
    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"daily analysis limit ({limit}) reached")


class RateLimiter:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._redis = None
        self._mem: dict[str, dict[str, int]] = {}
        self._limit = self._settings.free_analyses_per_day
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(self._settings.redis_url, decode_responses=True)
        except Exception:  # noqa: BLE001
            self._redis = None

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def unlimited(self) -> bool:
        return self._limit == 0

    def _key(self, telegram_id: int) -> str:
        day = time.strftime("%Y-%m-%d")
        return f"tgchan:rate:{day}:{telegram_id}"

    async def usage(self, telegram_id: int) -> int:
        key = self._key(telegram_id)
        if self._redis is not None:
            try:
                val = await self._redis.get(key)
                return int(val or 0)
            except Exception:  # noqa: BLE001
                pass
        return self._mem.get(key, {}).get("count", 0)

    async def check(self, telegram_id: int) -> None:
        if self.unlimited:
            return
        used = await self.usage(telegram_id)
        if used >= self._limit:
            raise RateLimitExceeded(self._limit)

    async def consume(self, telegram_id: int) -> int:
        """Increment the usage counter and return the new count."""
        key = self._key(telegram_id)
        if self._redis is not None:
            try:
                pipe = self._redis.pipeline()
                pipe.incr(key)
                pipe.expire(key, 60 * 60 * 25)
                result = await pipe.execute()
                return int(result[0])
            except Exception:  # noqa: BLE001
                pass
        bucket = self._mem.setdefault(key, {"count": 0})
        bucket["count"] += 1
        return bucket["count"]
