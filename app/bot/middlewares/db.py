"""Database-session middleware.

Provides an :class:`AsyncSession` to handlers via ``event.data["session"]``
and ensures the user row exists / is created.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.database.repositories.users import UserRepository
from app.database.session import get_session_factory


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        factory = get_session_factory()
        async with factory() as session:
            data["session"] = session
            user = data.get("event_from_user")
            if user is not None:
                repo = UserRepository(session)
                db_user, _ = await repo.get_or_create(
                    user.id,
                    username=user.username,
                    first_name=user.first_name,
                )
                data["db_user"] = db_user
            return await handler(event, data)
