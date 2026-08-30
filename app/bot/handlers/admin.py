"""Administrator commands (protected by ADMIN_IDS)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.menu import CB, back_to_menu_kb
from app.config import get_settings
from app.database.repositories.analyses import AnalysisRepository
from app.database.repositories.channels import ChannelRepository
from app.database.repositories.users import UserRepository
from app.database.session import get_session_factory
from app.services.localization import t

router = Router(name="admin")


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in get_settings().admin_id_list


async def _require_admin(message: Message) -> bool:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Недостаточно прав.")
        return False
    return True


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not await _require_admin(message):
        return
    async with get_session_factory()() as session:
        user_repo = UserRepository(session)
        channel_repo = ChannelRepository(session)
        analysis_repo = AnalysisRepository(session)

        total_users = await user_repo.count()
        total_channels = await channel_repo.count()
        total_analyses = await analysis_repo.count()
        successful = await analysis_repo.count_success()
        failed_jobs = await analysis_repo.count_jobs_failed()
        total_jobs = await analysis_repo.count_jobs()
        avg_duration = await analysis_repo.avg_duration_ms()
        avg_posts = await analysis_repo.avg_posts_analyzed()
        ai_cost = await analysis_repo.total_ai_cost()
        active_users = await analysis_repo.count_active_users()

    lines = [
        "🛠 АДМИН-ПАНЕЛЬ",
        "",
        f"👥 Пользователи: {total_users}",
        f"📢 Каналы: {total_channels}",
        f"🧪 Всего анализов: {total_analyses}",
        f"✅ Успешных: {successful}",
        f"❌ Проваленных задач: {failed_jobs} из {total_jobs}",
        f"⚡ Среднее время анализа: "
        f"{round(avg_duration / 1000, 1) if avg_duration else '—'} с",
        f"📄 Среднее постов/анализ: {round(avg_posts) if avg_posts else '—'}",
        f"💸 Приблизительная стоимость AI: ${round(ai_cost, 4) if ai_cost else '0.00'}",
        f"🧑‍💻 Активных пользователей: {active_users}",
    ]
    await message.answer("\n".join(lines), reply_markup=back_to_menu_kb())


@router.callback_query(F.data == "admin:stats")
async def cb_admin_stats(callback: CallbackQuery) -> None:
    await callback.answer()
    if not _is_admin(callback.from_user.id):
        return
    await cmd_admin(callback.message)  # reuse
