"""Channel-level aggregation analysis through AI."""

from __future__ import annotations

from typing import Any

from app.ai.base import AIProvider
from app.schemas import ChannelAnalysisResult


class ChannelAnalyzer:
    """Analyzes a channel as a whole from per-post summaries."""

    def __init__(self, provider: AIProvider) -> None:
        self._provider = provider

    async def analyze(
        self, channel_meta: dict[str, Any], posts_summary: list[dict[str, Any]]
    ) -> ChannelAnalysisResult:
        return await self._provider.analyze_channel(channel_meta, posts_summary)
