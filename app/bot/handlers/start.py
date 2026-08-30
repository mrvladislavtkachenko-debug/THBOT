"""Start / menu handlers and general navigation."""

from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.menu import (
    CB,
    back_to_menu_kb,
    main_menu_kb,
)
from app.context import get_context
from app.services.localization import t

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    ctx = get_context()
    try:
        usage = await ctx.rate_limiter.usage(message.from_user.id)
    except Exception:  # noqa: BLE001
        usage = 0
    limit = ctx.rate_limiter.limit
    extra = f"\n\n📊 Сегодня использовано: {usage}/{limit} анализов." if limit else ""
    await message.answer(
        t("welcome") + extra,
        reply_markup=main_menu_kb(),
    )


@router.message(Command("menu"))
@router.message(Command("help"))
async def cmd_menu(message: Message) -> None:
    await message.answer(t("main_menu"), reply_markup=main_menu_kb())


@router.callback_query(F.data == CB["main_menu"])
async def cb_main_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(t("main_menu"), reply_markup=main_menu_kb())


@router.callback_query(F.data == CB["analyze"])
async def cb_analyze(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    from app.bot.states import AnalyzeStates

    await state.set_state(AnalyzeStates.waiting_for_link)
    await callback.message.edit_text(t("send_channel_link"))
    await callback.message.answer(
        "Нажми «◀️ В меню», если передумал.",
        reply_markup=back_to_menu_kb(),
    )


@router.callback_query(F.data == CB["how"])
async def cb_how(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(t("how_it_works"), reply_markup=back_to_menu_kb())


@router.callback_query(F.data == CB["my_analyses"])
async def cb_my_analyses(callback: CallbackQuery) -> None:
    from .analysis import show_my_analyses
    await callback.answer()
    await show_my_analyses(callback)
