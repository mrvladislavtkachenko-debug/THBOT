"""User repository."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get(self, user_id) -> User | None:
        return await self._session.get(User, user_id)

    async def get_or_create(self, telegram_id: int, **defaults) -> tuple[User, bool]:
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            user = User(telegram_id=telegram_id, **defaults)
            self._session.add(user)
            await self._session.flush()
            return user, True
        changed = False
        for key, value in defaults.items():
            current = getattr(user, key, None)
            if value is not None and value != current:
                setattr(user, key, value)
                changed = True
        if changed:
            await self._session.flush()
        return user, False

    async def update(self, user: User, **fields) -> None:
        for key, value in fields.items():
            setattr(user, key, value)
        await self._session.flush()

    async def count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(User))
        return int(result.scalar_one())
