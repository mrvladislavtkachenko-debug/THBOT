"""Bot entry point.

Wires together the dispatcher, routers, middlewares and a lightweight
monitoring loop, then starts polling.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers import (
    admin,
    analysis,
    channel,
    compare,
    favorites,
    monitoring,
    settings,
    start,
)
from app.bot.middlewares.db import DbSessionMiddleware
from app.config import get_settings
from app.context import get_context
from app.database.session import init_db
from app.utils.logger import configure_logging, get_logger


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(DbSessionMiddleware())

    # register routers
    dp.include_router(start.router)
    dp.include_router(channel.router)
    dp.include_router(analysis.router)
    dp.include_router(favorites.router)
    dp.include_router(monitoring.router)
    dp.include_router(settings.router)
    dp.include_router(admin.router)
    dp.include_router(compare.router)
    return dp


async def _monitoring_loop(interval_seconds: int = 3600) -> None:
    """Periodically check monitored channels and notify owners."""
    from aiogram import Bot

    from app.database.repositories.users import UserRepository
    from app.database.session import get_session_factory
    from app.services.monitoring_service import MonitoringService

    ctx = get_context()
    bot = Bot(token=get_settings().bot_token)

    while True:
        await asyncio.sleep(interval_seconds)
        try:
            async with get_session_factory()() as session:
                service = MonitoringService(session)
                notifications = await service.check_due()
                # send each notification to its owner
                for notif in notifications:
                    owner = await UserRepository(session).get(notif["user_id"])
                    if owner is None:
                        continue
                    text = service.format_notification(notif)
                    try:
                        await bot.send_message(owner.telegram_id, text)
                    except Exception as exc:  # noqa: BLE001
                        get_logger("monitoring").warning(
                            "notify failed: %s", exc
                        )
        except Exception as exc:  # noqa: BLE001
            get_logger("monitoring").exception("monitoring loop error: %s", exc)


async def main() -> None:
    configure_logging()
    settings = get_settings()
    logger = get_logger("main")

    if not settings.bot_token:
        logger.error("BOT_TOKEN is not set. Add it to .env and restart.")
        return

    # Start background job queue
    ctx = get_context()
    ctx.job_queue.start(workers=2)

    # create tables if not present (dev convenience; use alembic in prod)
    try:
        await init_db()
    except Exception as exc:  # noqa: BLE001
        logger.warning("init_db skipped (use alembic in production): %s", exc)

    dp = build_dispatcher()
    bot = Bot(token=settings.bot_token)

    # start monitoring loop as a background task
    mon_task = asyncio.create_task(_monitoring_loop())

    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        mon_task.cancel()
        await ctx.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
