"""Settings handlers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.menu import CB
from app.database.repositories.users import UserRepository
from app.database.session import get_session_factory
from app.services.localization import set_language, t

router = Router(name="settings")


@router.callback_query(F.data == CB["settings"])
async def cb_settings(callback: CallbackQuery) -> None:
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
        ],
        [InlineKeyboardButton(text="◀️ В меню", callback_data=CB["main_menu"])],
    ])
    await callback.message.edit_text(t("settings_title"), reply_markup=kb)


@router.callback_query(F.data.startswith("lang:"))
async def cb_lang(callback: CallbackQuery) -> None:
    lang = callback.data.split(":")[1]
    await callback.answer()
    set_language(lang)
    async with get_session_factory()() as session:
        repo = UserRepository(session)
        db_user, _ = await repo.get_or_create(callback.from_user.id)
        await repo.update(db_user, language=lang)
    await callback.message.edit_text(t("language_set", language=lang))
