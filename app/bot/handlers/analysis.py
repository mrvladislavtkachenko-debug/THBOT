"""Report-section handlers and the "my analyses" list."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.menu import back_to_menu_kb
from app.services.localization import t
from app.services.report_service import ReportService
from app.services.session_store import get_outcome

router = Router(name="analysis")


def _get_outcome(callback: CallbackQuery):
    outcome, analysis_id = get_outcome(callback.from_user.id)
    return outcome


@router.callback_query(F.data == "report:show")
async def cb_show(callback: CallbackQuery) -> None:
    await callback.answer()
    outcome = _get_outcome(callback)
    if outcome is None:
        await callback.message.edit_text(t("no_analyses"))
        return
    from app.bot.keyboards.menu import report_kb

    report = ReportService().compact(outcome)
    await callback.message.edit_text(report, reply_markup=report_kb(outcome.username))


@router.callback_query(F.data == "report:best")
async def cb_best(callback: CallbackQuery) -> None:
    await callback.answer()
    outcome = _get_outcome(callback)
    if outcome is None:
        await callback.message.edit_text(t("no_analyses"))
        return
    text = ReportService().best_posts(outcome)
    await callback.message.edit_text(text, reply_markup=_back())


@router.callback_query(F.data == "report:trust")
async def cb_trust(callback: CallbackQuery) -> None:
    await callback.answer()
    outcome = _get_outcome(callback)
    if outcome is None:
        await callback.message.edit_text(t("no_analyses"))
        return
    text = ReportService().trust_explanation(outcome)
    await callback.message.edit_text(text, reply_markup=_back())


@router.callback_query(F.data == "report:risk")
async def cb_risk(callback: CallbackQuery) -> None:
    await callback.answer()
    outcome = _get_outcome(callback)
    if outcome is None:
        await callback.message.edit_text(t("no_analyses"))
        return
    text = ReportService().risk_report(outcome)
    await callback.message.edit_text(text, reply_markup=_back())


@router.callback_query(F.data == "report:full")
async def cb_full(callback: CallbackQuery) -> None:
    await callback.answer()
    outcome = _get_outcome(callback)
    if outcome is None:
        await callback.message.edit_text(t("no_analyses"))
        return
    text = ReportService().full(outcome)
    await callback.message.edit_text(text, reply_markup=_back())


async def show_my_analyses(callback: CallbackQuery) -> None:
    """Show the user's recent analyses (from in-memory state)."""
    outcome, _ = get_outcome(callback.from_user.id)
    if outcome is None:
        await callback.message.edit_text(t("no_analyses"), reply_markup=_back())
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"@{outcome.username}", callback_data="report:show"
            )
        ],
        [InlineKeyboardButton(text="◀️ В меню", callback_data="menu:main")],
    ])
    await callback.message.edit_text(
        f"📊 Ваш последний анализ:\n\n@{outcome.username} · "
        f"Trust {outcome.trust:.0f} · Quality {outcome.quality:.0f}",
        reply_markup=kb,
    )


def _back() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Полный анализ", callback_data="report:full")],
        [InlineKeyboardButton(text="◀️ В меню", callback_data="menu:main")],
    ])
    return kb
