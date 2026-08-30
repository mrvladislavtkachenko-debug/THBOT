"""Favorites handlers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.menu import CB
from app.database.repositories.channels import ChannelRepository
from app.database.repositories.favorites import FavoriteRepository
from app.database.session import get_session_factory
from app.services.localization import t
from app.services.session_store import get_outcome

router = Router(name="favorites")


@router.callback_query(F.data == "fav:add")
async def cb_add_favorite(callback: CallbackQuery) -> None:
    await callback.answer()
    outcome, _ = get_outcome(callback.from_user.id)
    if outcome is None:
        await callback.message.edit_text(t("no_analyses"))
        return
    async with get_session_factory()() as session:
        channel_repo = ChannelRepository(session)
        channel = await channel_repo.get_by_username(outcome.username)
        if channel is None:
            await callback.answer("Канал ещё не сохранён", show_alert=True)
            return
        user_repo = FavoriteRepository(session)
        # resolve db user by telegram id
        from app.database.repositories.users import UserRepository
        db_user, _ = await UserRepository(session).get_or_create(callback.from_user.id)
        added = await user_repo.add(db_user.id, channel.id)
    if added:
        await callback.answer("⭐ Добавлено в избранное", show_alert=True)
    else:
        await callback.answer("Уже в избранном", show_alert=True)


@router.callback_query(F.data == CB["favorites"])
async def cb_favorites(callback: CallbackQuery) -> None:
    await callback.answer()
    async with get_session_factory()() as session:
        from app.database.repositories.users import UserRepository
        db_user, _ = await UserRepository(session).get_or_create(callback.from_user.id)
        favs = await FavoriteRepository(session).list_for_user(db_user.id)
        if not favs:
            await callback.message.edit_text(t("favorites_empty"), reply_markup=_menu())
            return
        buttons = [
            [InlineKeyboardButton(
                text=f"⭐ @{fav.channel.username}", callback_data="fav:show"
            )] for fav in favs
        ]
        kb = InlineKeyboardMarkup(inline_keyboard=buttons + [
            [InlineKeyboardButton(text="◀️ В меню", callback_data=CB["main_menu"])]
        ])
        await callback.message.edit_text(t("favorites_title"), reply_markup=kb)


def _menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ В меню", callback_data=CB["main_menu"])]
    ])
