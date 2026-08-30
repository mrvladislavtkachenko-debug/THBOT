"""Monitoring handlers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.menu import CB, monitoring_intervals_kb
from app.database.repositories.analyses import AnalysisRepository
from app.database.repositories.channels import ChannelRepository
from app.database.repositories.users import UserRepository
from app.database.session import get_session_factory
from app.services.localization import t
from app.services.session_store import get_outcome

router = Router(name="monitoring")


@router.callback_query(F.data == "mon:start")
async def cb_mon_start(callback: CallbackQuery) -> None:
    await callback.answer()
    outcome, _ = get_outcome(callback.from_user.id)
    if outcome is None:
        await callback.message.edit_text(t("no_analyses"))
        return
    kb = monitoring_intervals_kb(outcome.username)
    await callback.message.edit_text(
        f"🔔 Выберите интервал мониторинга для @{outcome.username}",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("mon:interval:"))
async def cb_mon_interval(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    interval = parts[2]
    username = parts[3]
    await callback.answer()
    async with get_session_factory()() as session:
        user_repo = UserRepository(session)
        db_user, _ = await user_repo.get_or_create(callback.from_user.id)
        channel_repo = ChannelRepository(session)
        channel = await channel_repo.get_or_create_by_username(username)
        repo = AnalysisRepository(session)
        existing = await repo.get_monitoring(db_user.id, channel[0].id)
        if existing is not None:
            await repo.update(existing, interval=interval, enabled=True)
        else:
            await repo.add_monitoring(db_user.id, channel[0].id, interval)
    await callback.message.edit_text(
        t("monitoring_on", channel=username), reply_markup=_menu()
    )


@router.callback_query(F.data.startswith("mon:stop:"))
async def cb_mon_stop(callback: CallbackQuery) -> None:
    username = callback.data.split(":", 2)[2]
    await callback.answer()
    async with get_session_factory()() as session:
        user_repo = UserRepository(session)
        db_user, _ = await user_repo.get_or_create(callback.from_user.id)
        channel_repo = ChannelRepository(session)
        channel = await channel_repo.get_by_username(username)
        if channel is not None:
            repo = AnalysisRepository(session)
            existing = await repo.get_monitoring(db_user.id, channel.id)
            if existing is not None:
                await repo.update(existing, enabled=False)
    await callback.message.edit_text(
        t("monitoring_off", channel=username), reply_markup=_menu()
    )


@router.callback_query(F.data == CB["monitoring"])
async def cb_monitoring_list(callback: CallbackQuery) -> None:
    await callback.answer()
    async with get_session_factory()() as session:
        user_repo = UserRepository(session)
        db_user, _ = await user_repo.get_or_create(callback.from_user.id)
        repo = AnalysisRepository(session)
        # list monitoring for this user
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.database.models import Monitoring
        result = await session.execute(
            select(Monitoring)
            .options(selectinload(Monitoring.channel))
            .where(Monitoring.user_id == db_user.id, Monitoring.enabled.is_(True))
            .order_by(Monitoring.created_at.desc())
        )
        monitored = list(result.scalars().all())
        if not monitored:
            await callback.message.edit_text(t("monitoring_empty"), reply_markup=_menu())
            return
        lines = [t("monitoring_title"), ""]
        for mon in monitored:
            lines.append(f"🔔 @{mon.channel.username} · {mon.interval}")
        await callback.message.edit_text("\n".join(lines), reply_markup=_menu())


def _menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ В меню", callback_data=CB["main_menu"])]
    ])
