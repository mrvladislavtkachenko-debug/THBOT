"""Background job queue.

Provides a simple in-process async queue by default. The interface is
designed so it can be swapped for a Redis-backed worker (RQ/Celery)
without changing callers. A Redis-based ``enqueue`` is provided too.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from typing import Any, Awaitable, Callable

from app.config import get_settings

logger = logging.getLogger("jobs")

JobCallable = Callable[..., Awaitable[Any]]


class JobQueue:
    """Interface-compatible queue dispatcher."""

    def __init__(self, backend: str | None = None) -> None:
        settings = get_settings()
        self._backend = backend or settings.job_queue_backend
        self._asyncio_queue: asyncio.Queue | None = None
        self._redis = None
        self._worker_tasks: list[asyncio.Task] = []

    def start(self, workers: int = 1) -> None:
        if self._backend == "redis":
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(
                get_settings().redis_url, decode_responses=True
            )
            return
        self._asyncio_queue = asyncio.Queue()
        for _ in range(workers):
            task = asyncio.create_task(self._worker_loop())
            self._worker_tasks.append(task)

    async def _worker_loop(self) -> None:
        assert self._asyncio_queue is not None
        while True:
            job = await self._asyncio_queue.get()
            try:
                func = job["func"]
                args = job.get("args", [])
                kwargs = job.get("kwargs", {})
                result = func(*args, **kwargs)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:  # noqa: BLE001
                logger.exception("job failed: %s", exc)
            finally:
                self._asyncio_queue.task_done()

    async def enqueue(self, func: JobCallable, *args: Any, **kwargs: Any) -> None:
        """Schedule ``func`` to run in the background."""
        if self._backend == "redis":
            assert self._redis is not None
            payload = {
                "module": func.__module__,
                "name": func.__name__,
                "args": args,
                "kwargs": kwargs,
            }
            await self._redis.lpush(
                "tgchan:jobs", json.dumps(payload, default=str)
            )
            return
        assert self._asyncio_queue is not None
        await self._asyncio_queue.put(
            {"func": func, "args": args, "kwargs": kwargs}
        )

    async def shutdown(self) -> None:
        for task in self._worker_tasks:
            task.cancel()
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:  # noqa: BLE001
                pass
