"""AI provider abstraction.

All AI providers implement this interface. The rest of the application
depends only on these methods, never on a concrete SDK.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.schemas import (
    ChannelAnalysisResult,
    PostAnalysisResult,
    ScamReport,
)


class AIError(Exception):
    """Raised when an AI call fails (network, API, timeout, bad output)."""


class AIProvider(ABC):
    """Interface all AI providers must implement."""

    #: Provider name, e.g. "openai", "mock".
    name: str = "base"

    @abstractmethod
    async def analyze_post(self, text: str | None) -> PostAnalysisResult:
        """Return a structured analysis for a single post."""

    @abstractmethod
    async def analyze_channel(
        self,
        channel_meta: dict[str, Any],
        posts_summary: list[dict[str, Any]],
    ) -> ChannelAnalysisResult:
        """Return aggregated channel-level analysis."""

    @abstractmethod
    async def analyze_scam_risk(self, posts: list[dict[str, Any]]) -> ScamReport:
        """Return a scam-focused report over the analyzed posts."""
