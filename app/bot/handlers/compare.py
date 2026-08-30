"""Channel comparison (/compare).

MVP implementation: analyzes two channels and presents a score table.
This can be disabled by simply not registering the router.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.deps import build_analysis_service
from app.context import get_context
from app.database.session import get_session_factory
from app.services.analysis_service import ChannelAnalysisError
from app.services.localization import t
from app.utils.validators import InvalidChannelLinkError, parse_channel_link

router = Router(name="compare")

ENABLED = True  # set False to disable /compare in MVP


@router.message(Command("compare"))
async def cmd_compare(message: Message) -> None:
    if not ENABLED:
        await message.answer("Сравнение каналов недоступно в этой версии.")
        return
    parts = [p.strip() for p in message.text.split() if p.strip()]
    links = parts[1:]
    if len(links) < 2:
        await message.answer(t("compare_prompt"))
        return
    # only take the first two
    links = links[:2]
    usernames: list[str] = []
    try:
        for link in links:
            usernames.append(parse_channel_link(link).username)
    except InvalidChannelLinkError:
        await message.answer(t("invalid_link"))
        return

    status = await message.answer("🔎 Анализирую каналы для сравнения...")
    ctx = get_context()
    outcomes = []
    async with get_session_factory()() as session:
        service = build_analysis_service(session, ctx)
        for username in usernames:
            try:
                result = await service.analyze(username, user_id=None)
                outcomes.append(result.outcome)
            except ChannelAnalysisError as exc:
                await status.edit_text(str(exc))
                return
            except Exception as exc:  # noqa: BLE001
                await status.edit_text(t("error_channel") + f" ({type(exc).__name__})")
                return

    a, b = outcomes[0], outcomes[1]
    lines = [t("compare_title"), ""]
    lines.append(f"{'':<16}{'Канал A':<12}{'Канал B':<12}")
    lines.append(f"{'Quality':<16}{a.quality:<12.0f}{b.quality:<12.0f}")
    lines.append(f"{'Trust':<16}{a.trust:<12.0f}{b.trust:<12.0f}")
    lines.append(f"{'Scam Risk':<16}{a.scam_risk:<12.0f}{b.scam_risk:<12.0f}")
    lines.append(f"{'Originality':<16}{a.originality:<12.0f}{b.originality:<12.0f}")
    lines.append(f"{'Advertising':<16}{a.advertising:<12.0f}{b.advertising:<12.0f}")
    lines.append("")
    # decide better
    def rank(o):
        return o.quality * 0.4 + o.trust * 0.4 - o.scam_risk * 0.2
    winner = a if rank(a) >= rank(b) else b
    lines.append(f"Лучший для вас: 🏆 @{winner.username}")
    await status.edit_text("\n".join(lines))
