"""Application context — shared singletons.

Provides lazy access to shared services (Telegram client, cache, rate
limiter, job queue) so handlers can build an :class:`AnalysisService`
per request without re-initializing heavy objects.
"""

from __future__ import annotations

from app.services.cache_service import AnalysisCache
from app.services.job_queue import JobQueue
from app.services.rate_limiter import RateLimiter
from app.telegram.channel_service import ChannelService
from app.telegram.client import TelegramClientWrapper


class AppContext:
    """Holds shared services and lazily builds the Telegram client."""

    def __init__(self) -> None:
        self._telegram_client: TelegramClientWrapper | None = None
        self._channel_service: ChannelService | None = None
        self._cache: AnalysisCache | None = None
        self._rate_limiter: RateLimiter | None = None
        self._job_queue: JobQueue | None = None

    @property
    def channel_service(self) -> ChannelService:
        if self._channel_service is None:
            if self._telegram_client is None:
                self._telegram_client = TelegramClientWrapper()
            self._channel_service = ChannelService(self._telegram_client)
        return self._channel_service

    @property
    def cache(self) -> AnalysisCache:
        if self._cache is None:
            self._cache = AnalysisCache()
        return self._cache

    @property
    def rate_limiter(self) -> RateLimiter:
        if self._rate_limiter is None:
            self._rate_limiter = RateLimiter()
        return self._rate_limiter

    @property
    def job_queue(self) -> JobQueue:
        if self._job_queue is None:
            self._job_queue = JobQueue()
        return self._job_queue

    async def shutdown(self) -> None:
        if self._telegram_client is not None:
            await self._telegram_client.disconnect()
        await self._job_queue.shutdown()


_context: AppContext | None = None


def get_context() -> AppContext:
    """Return the process-wide AppContext singleton."""
    global _context
    if _context is None:
        _context = AppContext()
    return _context
