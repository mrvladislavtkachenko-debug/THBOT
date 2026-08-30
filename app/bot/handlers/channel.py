"""Channel-link handling and analysis triggering.

The actual analysis runs in a background asyncio task so the Telegram
event loop is never blocked. Progress is pushed to the user by editing
a single message.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.deps import build_analysis_service
from app.bot.keyboards.menu import (
    CB,
    back_to_menu_kb,
    cache_kb,
    report_kb,
)
from app.bot.states import AnalyzeStates
from app.context import get_context
from app.database.session import get_session_factory
from app.services.analysis_service import ChannelAnalysisError
from app.services.localization import t
from app.services.rate_limiter import RateLimitExceeded
from app.services.session_store import save_outcome
from app.utils.logger import get_logger
from app.utils.validators import InvalidChannelLinkError, parse_channel_link

logger = get_logger("bot.channel")

router = Router(name="channel")


@router.message(F.text, AnalyzeStates.waiting_for_link)
async def on_link_received(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    telegram_id = message.from_user.id
    raw = message.text.strip()

    # Parse & validate
    try:
        ref = parse_channel_link(raw)
    except InvalidChannelLinkError:
        await message.answer(t("invalid_link"))
        return

    await state.clear()

    # Rate limiting
    if not ctx.rate_limiter.unlimited:
        try:
            await ctx.rate_limiter.check(telegram_id)
        except RateLimitExceeded as exc:
            await message.answer(t("rate_limit", limit=exc.limit))
            return

    status = await message.answer(t("analyzing"))

    # Cache check (cheap) before spawning a heavy job
    cached = await ctx.cache.get(ref.username)
    if cached is not None:
        from app.services.analysis_service import _outcome_from_dict

        outcome = _outcome_from_dict(cached)
        save_outcome(telegram_id, outcome, cached.get("analysis_id", ""))
        await status.edit_text(
            t("cached_options"),
            reply_markup=cache_kb(),
        )
        return

    asyncio.create_task(
        _run_analysis_task(
            bot=message.bot,
            chat_id=message.chat.id,
            message_id=status.message_id,
            telegram_id=telegram_id,
            username=ref.username,
        )
    )


async def _run_analysis_task(
    bot,
    chat_id: int,
    message_id: int,
    telegram_id: int,
    username: str,
) -> None:
    """Background analysis runner with live progress updates."""
    ctx = get_context()

    async def progress(text: str) -> None:
        try:
            await bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=message_id,
            )
        except Exception:  # noqa: BLE001
            pass

    async with get_session_factory()() as session:
        service = build_analysis_service(session, ctx)
        try:
            await ctx.rate_limiter.consume(telegram_id)
            result = await service.analyze(
                username,
                user_id=None,
                on_progress=progress,
            )
            save_outcome(telegram_id, result.outcome, str(result.analysis_id))
            from app.services.report_service import ReportService

            report = ReportService().compact(result.outcome)
            await bot.edit_message_text(
                report,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=report_kb(result.outcome.username),
            )
        except ChannelAnalysisError as exc:
            await bot.edit_message_text(
                f"{exc}",
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=back_to_menu_kb(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("analysis task failed")
            await bot.edit_message_text(
                t("error_channel") + f"\n\n({type(exc).__name__})",
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=back_to_menu_kb(),
            )


@router.callback_query(F.data == "report:refresh")
async def cb_refresh(callback: CallbackQuery) -> None:
    """Force a fresh analysis of the user's last channel."""
    await callback.answer()
    ctx = get_context()
    from app.services.session_store import get_outcome

    outcome, _ = get_outcome(callback.from_user.id)
    if outcome is None:
        await callback.message.edit_text(t("no_analyses"))
        return
    username = outcome.username
    status = await callback.message.edit_text(t("analyzing"))
    asyncio.create_task(
        _run_analysis_task(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            message_id=status.message_id,
            telegram_id=callback.from_user.id,
            username=username,
        )
    )
