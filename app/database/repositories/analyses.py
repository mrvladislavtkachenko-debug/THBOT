"""Channel-analysis and job repository."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    AnalysisJob,
    ChannelAnalysis,
    ChannelSnapshot,
    JobStatus,
    Monitoring,
)
from app.database.models import User


class AnalysisRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- ChannelAnalysis -----------------------------------------------
    async def get(self, analysis_id: UUID) -> ChannelAnalysis | None:
        return await self._session.get(ChannelAnalysis, analysis_id)

    async def latest_for_channel(self, channel_id: UUID) -> ChannelAnalysis | None:
        result = await self._session.execute(
            select(ChannelAnalysis)
            .where(ChannelAnalysis.channel_id == channel_id)
            .order_by(ChannelAnalysis.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(self, analysis: ChannelAnalysis) -> ChannelAnalysis:
        self._session.add(analysis)
        await self._session.flush()
        return analysis

    async def update(self, analysis: ChannelAnalysis, **fields) -> None:
        for key, value in fields.items():
            setattr(analysis, key, value)
        await self._session.flush()

    async def count(self) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(ChannelAnalysis)
        )
        return int(result.scalar_one())

    async def count_success(self) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(ChannelAnalysis)
            .where(ChannelAnalysis.verdict.is_not(None))
        )
        return int(result.scalar_one())

    async def count_since(self, since: datetime) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(ChannelAnalysis)
            .where(ChannelAnalysis.created_at >= since)
        )
        return int(result.scalar_one())

    async def avg_duration_ms(self) -> float | None:
        result = await self._session.execute(
            select(func.avg(ChannelAnalysis.duration_ms))
        )
        return result.scalar_one()

    async def avg_posts_analyzed(self) -> float | None:
        result = await self._session.execute(
            select(func.avg(ChannelAnalysis.posts_analyzed))
        )
        return result.scalar_one()

    async def total_ai_cost(self) -> float:
        result = await self._session.execute(
            select(func.coalesce(func.sum(ChannelAnalysis.ai_cost), 0.0))
        )
        return float(result.scalar_one())

    # -- Snapshots -----------------------------------------------------
    async def add_snapshot(self, snapshot: ChannelSnapshot) -> None:
        self._session.add(snapshot)
        await self._session.flush()

    async def list_snapshots(self, channel_id: UUID, limit: int = 30) -> list[ChannelSnapshot]:
        result = await self._session.execute(
            select(ChannelSnapshot)
            .where(ChannelSnapshot.channel_id == channel_id)
            .order_by(ChannelSnapshot.snapshot_date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    # -- Jobs ----------------------------------------------------------
    async def get_job(self, job_id: UUID) -> AnalysisJob | None:
        return await self._session.get(AnalysisJob, job_id)

    async def get_job_by_user_and_channel(
        self, user_id: UUID, username: str, statuses: list[str] | None = None
    ) -> AnalysisJob | None:
        stmt = select(AnalysisJob).where(
            AnalysisJob.user_id == user_id,
            AnalysisJob.channel_username == username.lower(),
        )
        if statuses:
            stmt = stmt.where(AnalysisJob.status.in_(statuses))
        stmt = stmt.order_by(AnalysisJob.created_at.desc()).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_job(self, user_id: UUID | None, username: str) -> AnalysisJob:
        job = AnalysisJob(
            user_id=user_id,
            channel_username=username.lower(),
            status=JobStatus.PENDING.value,
        )
        self._session.add(job)
        await self._session.flush()
        return job

    async def update_job(self, job: AnalysisJob, **fields) -> None:
        for key, value in fields.items():
            setattr(job, key, value)
        await self._session.flush()

    async def count_jobs(self) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(AnalysisJob)
        )
        return int(result.scalar_one())

    async def count_jobs_failed(self) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(AnalysisJob)
            .where(AnalysisJob.status == JobStatus.FAILED.value)
        )
        return int(result.scalar_one())

    # -- Monitoring ----------------------------------------------------
    async def list_monitoring(self, channel_id: UUID | None = None) -> list[Monitoring]:
        stmt = select(Monitoring)
        if channel_id is not None:
            stmt = stmt.where(Monitoring.channel_id == channel_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_monitoring(self, user_id: UUID, channel_id: UUID) -> Monitoring | None:
        result = await self._session.execute(
            select(Monitoring).where(
                Monitoring.user_id == user_id,
                Monitoring.channel_id == channel_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_monitoring(self, user_id: UUID, channel_id: UUID, interval: str) -> Monitoring:
        mon = Monitoring(user_id=user_id, channel_id=channel_id, interval=interval)
        self._session.add(mon)
        await self._session.flush()
        return mon

    async def count_active_users(self) -> int:
        result = await self._session.execute(
            select(func.count(func.distinct(ChannelAnalysis.user_id)))
            .where(ChannelAnalysis.user_id.is_not(None))
        )
        return int(result.scalar_one())

    async def recent_activity(self) -> list[tuple[int, int]]:
        """Return [(telegram_id, analyses_today)] for active users."""
        since = datetime.utcnow() - timedelta(hours=24)
        stmt = (
            select(User.telegram_id, func.count(ChannelAnalysis.id))
            .join(User, ChannelAnalysis.user_id == User.id)
            .where(ChannelAnalysis.created_at >= since)
            .group_by(User.telegram_id)
        )
        result = await self._session.execute(stmt)
        return list(result.all())
