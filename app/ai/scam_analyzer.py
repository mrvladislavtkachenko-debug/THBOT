"""Scam-focused AI analysis over posts."""

from __future__ import annotations

from typing import Any

from app.ai.base import AIProvider
from app.schemas import ScamReport


class ScamAnalyzer:
    """Produces a scam risk report from analyzed posts."""

    def __init__(self, provider: AIProvider) -> None:
        self._provider = provider

    async def analyze(self, posts: list[dict[str, Any]]) -> ScamReport:
        return await self._provider.analyze_scam_risk(posts)
