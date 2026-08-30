"""Small dependency helpers shared by handlers."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.context import AppContext, get_context
from app.services.analysis_service import AnalysisService


def build_analysis_service(
    session: AsyncSession, ctx: AppContext | None = None
) -> AnalysisService:
    """Build an AnalysisService bound to a request session."""
    ctx = ctx or get_context()
    return AnalysisService(
        session=session,
        channel_service=ctx.channel_service,
        cache=ctx.cache,
    )
