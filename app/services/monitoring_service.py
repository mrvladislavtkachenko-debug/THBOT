"""Monitoring service.

Periodically re-analyzes monitored channels and notifies the owner when
meaningful metrics change (trust, advertising, scam risk, topics).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.analyses import AnalysisRepository
from app.services.analysis_service import AnalysisService, ChannelAnalysisError
from app.utils.logger import get_logger

logger = get_logger("monitoring")

INTERVAL_DAYS = {
    "daily": 1,
    "every_3_days": 3,
    "weekly": 7,
}

METRIC_THRESHOLDS = {
    "trust": 8.0,
    "scam_risk": 8.0,
    "advertising": 10.0,
    "quality": 8.0,
}

MEASURE_LABELS = {
    "trust": "Trust",
    "scam_risk": "Scam Risk",
    "advertising": "Advertising",
    "quality": "Quality",
}


class MonitoringService:
    def __init__(
        self, session: AsyncSession, analysis_service: AnalysisService | None = None
    ) -> None:
        self._session = session
        self._repo = AnalysisRepository(session)
        self._analysis_service = analysis_service

    def set_analysis_service(self, service: AnalysisService) -> None:
        self._analysis_service = service

    async def check_due(self) -> list[dict]:
        """Run due monitoring checks. Returns notifications."""
        if self._analysis_service is None:
            return []
        monitored = await self._repo.list_monitoring()
        notifications: list[dict] = []
        now = datetime.now(timezone.utc)

        for mon in monitored:
            if not mon.enabled:
                continue
            days = INTERVAL_DAYS.get(mon.interval, 7)
            last = mon.last_checked_at
            if last and (now - last).total_seconds() < days * 86400:
                continue
            try:
                result = await self._analysis_service.analyze(
                    mon.channel.username, user_id=None, force_refresh=True
                )
                prev = await self._latest_snapshot_scores(mon.channel_id)
                changes = self._detect_changes(result.outcome, prev)
                if changes:
                    notifications.append({
                        "user_id": mon.user_id,
                        "channel": mon.channel.username,
                        "changes": changes,
                        "outcome": result.outcome,
                    })
                await self._repo.update(mon, last_checked_at=now)
            except ChannelAnalysisError as exc:
                logger.warning("monitoring failed for %s: %s", mon.channel.username, exc)
            except Exception as exc:  # noqa: BLE001
                logger.exception("monitoring error: %s", exc)
        return notifications

    async def _latest_snapshot_scores(self, channel_id: UUID) -> dict:
        snapshots = await self._repo.list_snapshots(channel_id, limit=2)
        if len(snapshots) < 2:
            return {}
        prev = snapshots[1]  # second latest
        return {
            "trust": prev.trust_score,
            "scam_risk": prev.scam_risk_score,
            "advertising": prev.advertising_score,
            "quality": prev.quality_score,
        }

    def _detect_changes(self, outcome, prev: dict) -> list[dict]:
        if not prev:
            return []
        changes = []
        current = {
            "trust": outcome.trust,
            "scam_risk": outcome.scam_risk,
            "advertising": outcome.advertising,
            "quality": outcome.quality,
        }
        for metric, label in MEASURE_LABELS.items():
            if prev.get(metric) is None:
                continue
            diff = current[metric] - prev[metric]
            if abs(diff) >= METRIC_THRESHOLDS.get(metric, 10):
                changes.append({
                    "metric": label,
                    "from": round(prev[metric], 0),
                    "to": round(current[metric], 0),
                    "delta": round(diff, 0),
                })
        return changes

    def format_notification(self, notification: dict) -> str:
        lines = ["⚠️ КАНАЛ ИЗМЕНИЛСЯ", ""]
        lines.append(f"@{notification['channel']}")
        lines.append("")
        for ch in notification["changes"]:
            direction = "↑" if ch["delta"] > 0 else "↓"
            lines.append(f"{ch['metric']}:\n{ch['from']:.0f} → {ch['to']:.0f} ({direction})")
        lines.append("")
        lines.append("Проверьте актуальный отчёт.")
        return "\n".join(lines)
