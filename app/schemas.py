"""Pydantic schemas used across the analysis pipeline.

These are the structured, validated data shapes passed between the AI
layer, the scoring engine, and the report generator. Keeping them as
Pydantic models guarantees type-safety at every boundary.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class PostType(str, enum.Enum):
    NEWS = "news"
    ANALYSIS = "analysis"
    OPINION = "opinion"
    EDUCATIONAL = "educational"
    ADVERTISEMENT = "advertisement"
    PROMOTION = "promotion"
    PERSONAL = "personal"
    ANNOUNCEMENT = "announcement"
    REPOST = "repost"
    ENTERTAINMENT = "entertainment"
    REVIEW = "review"
    CASE_STUDY = "case_study"
    PREDICTION = "prediction"
    OTHER = "other"


class SourceQuality(str, enum.Enum):
    NONE = "none"
    WEAK = "weak"
    MEDIUM = "medium"
    STRONG = "strong"


class Verdict(str, enum.Enum):
    STRONGLY_RECOMMEND = "STRONGLY_RECOMMEND"
    RECOMMEND = "RECOMMEND"
    NEUTRAL = "NEUTRAL"
    CAUTION = "CAUTION"
    NOT_RECOMMENDED = "NOT_RECOMMENDED"


class ScamRiskLevel(str, enum.Enum):
    LOW = "low"
    MODERATE = "moderate"
    ELEVATED = "elevated"
    HIGH = "high"
    CRITICAL = "critical"


class AdvertisingLevel(str, enum.Enum):
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


# ---------------------------------------------------------------------------
# Raw collected channel / post data
# ---------------------------------------------------------------------------
class ChannelInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    username: str
    title: str | None = None
    description: str | None = None
    url: str = ""
    subscriber_count: int | None = None
    created_date: datetime | None = None
    telegram_channel_id: int | None = None
    is_group: bool = False
    is_bot: bool = False
    is_private: bool = False
    available_posts: int | None = None
    exists: bool = True


class PostData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    telegram_message_id: int
    text: str | None = None
    date: datetime | None = None
    views: int | None = None
    reactions: int | None = None
    comments: int | None = None
    forwards: int | None = None
    post_url: str | None = None
    media_type: str | None = None


# ---------------------------------------------------------------------------
# AI outputs
# ---------------------------------------------------------------------------
class PostAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    topic: str | None = None
    subtopic: str | None = None
    post_type: str = PostType.OTHER.value
    language: str | None = None
    quality_score: float = 0.0
    originality_score: float = 0.0
    factual_support: float | None = None  # 0-10, unverified when None
    source_quality: str = SourceQuality.NONE.value
    advertising_score: float = 0.0
    manipulation_score: float = 0.0
    scam_signals: list[str] = Field(default_factory=list)
    summary: str | None = None
    why_valuable: str | None = None

    # ------------------------------------------------------------------
    def normalized(self) -> dict:
        """Return a clamped / validated dict safe for storage."""
        return {
            "topic": self.topic,
            "subtopic": self.subtopic,
            "post_type": _norm_enum(self.post_type, PostType, PostType.OTHER),
            "language": self.language,
            "quality_score": _clamp_score(self.quality_score),
            "originality_score": _clamp_score(self.originality_score),
            "factual_support": _clamp_score(self.factual_support)
            if self.factual_support is not None
            else None,
            "source_quality": _norm_enum(
                self.source_quality, SourceQuality, SourceQuality.NONE
            ),
            "advertising_score": _clamp_score(self.advertising_score),
            "manipulation_score": _clamp_score(self.manipulation_score),
            "scam_signals": _norm_scam_signals(self.scam_signals),
            "summary": self.summary,
            "why_valuable": self.why_valuable,
        }


class ChannelAnalysisResult(BaseModel):
    """Aggregated channel-level analysis produced by the AI channel analyzer."""

    model_config = ConfigDict(extra="allow")

    main_topic: str | None = None
    topics: dict[str, float] = Field(default_factory=dict)  # topic -> percent
    audience: list[str] = Field(default_factory=list)
    audience_not_for: list[str] = Field(default_factory=list)
    style: list[str] = Field(default_factory=list)
    tone: str | None = None  # positive|neutral|negative|mixed
    content_mix: dict[str, float] = Field(default_factory=dict)
    author_style_summary: str | None = None
    quality_factors: list[str] = Field(default_factory=list)
    quality_risks: list[str] = Field(default_factory=list)
    summary: str | None = None
    verdict_reasoning: str | None = None


class ScamReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    score: float = 0.0
    level: str = ScamRiskLevel.LOW.value
    findings: list[str] = Field(default_factory=list)
    signals: dict[str, int] = Field(default_factory=dict)
    evidence: list[dict] = Field(default_factory=list)  # {post_id, signals, snippet}


class ReportSection(BaseModel):
    title: str
    body: str
    rows: Optional[list[str]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clamp_score(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, min(10.0, v)), 1)


def _norm_enum(value: Any, enum_cls, default) -> str:
    if isinstance(value, enum_cls):
        return value.value
    if isinstance(value, str):
        for member in enum_cls:
            if value.lower() == member.value:
                return member.value
    return default.value


def _norm_scam_signals(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
    return out
