"""SQLAlchemy ORM models.

Maps the tables described in the technical specification:
users, channels, posts, post_analysis, channel_analysis,
channel_snapshots, favorites, monitoring, analysis_jobs.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import (
    Base,
    created_at_column,
    updated_at_column,
    utcnow,
    uuid_pk,
)


# ---------------------------------------------------------------------------
# Enums / constants
# ---------------------------------------------------------------------------
class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    COLLECTING = "COLLECTING"
    ANALYZING_POSTS = "ANALYZING_POSTS"
    ANALYZING_CHANNEL = "ANALYZING_CHANNEL"
    CALCULATING_SCORES = "CALCULATING_SCORES"
    GENERATING_REPORT = "GENERATING_REPORT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Verdict(str, enum.Enum):
    STRONGLY_RECOMMEND = "STRONGLY_RECOMMEND"
    RECOMMEND = "RECOMMEND"
    NEUTRAL = "NEUTRAL"
    CAUTION = "CAUTION"
    NOT_RECOMMENDED = "NOT_RECOMMENDED"


class MonitoringInterval(str, enum.Enum):
    DAILY = "daily"
    EVERY_3_DAYS = "every_3_days"
    WEEKLY = "weekly"


class Plan(str, enum.Enum):
    FREE = "FREE"
    PRO = "PRO"
    ADMIN = "ADMIN"


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str] = mapped_column(String(8), default="ru")
    plan: Mapped[str] = mapped_column(String(16), default=Plan.FREE.value)
    interests: Mapped[list | None] = mapped_column(
        String(512), nullable=True
    )  # comma-separated interests (future personalisation)
    occupation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preferred_topics: Mapped[str | None] = mapped_column(String(512), nullable=True)
    max_daily_posts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    favorites = relationship(
        "Favorite", back_populates="user", cascade="all, delete-orphan"
    )
    monitorings = relationship(
        "Monitoring", back_populates="user", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------
class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[uuid.UUID] = uuid_pk()
    telegram_channel_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    subscriber_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    channel_url: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
    last_analyzed_at: Mapped[datetime | None] = mapped_column(
        default=None, nullable=True
    )

    posts = relationship("Post", back_populates="channel", cascade="all, delete-orphan")


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        UniqueConstraint(
            "channel_id", "telegram_message_id", name="uq_posts_channel_message"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True
    )
    telegram_message_id: Mapped[int] = mapped_column(BigInteger)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reactions: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    comments: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    forwards: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    post_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = created_at_column()

    channel = relationship("Channel", back_populates="posts")
    analysis = relationship(
        "PostAnalysis", back_populates="post", uselist=False, cascade="all, delete-orphan"
    )


class PostAnalysis(Base):
    __tablename__ = "post_analysis"

    id: Mapped[uuid.UUID] = uuid_pk()
    post_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), unique=True, index=True
    )
    topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subtopic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    post_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    originality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    factual_support: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_quality: Mapped[str | None] = mapped_column(String(16), nullable=True)
    advertising_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    manipulation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    scam_signals: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    why_valuable: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="success")  # success|failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = created_at_column()

    post = relationship("Post", back_populates="analysis")


class ChannelAnalysis(Base):
    __tablename__ = "channel_analysis"

    id: Mapped[uuid.UUID] = uuid_pk()
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    trust_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    scam_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    advertising_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    originality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    activity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    main_topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    topics: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    audience: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    style: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    best_posts: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    concerning_posts: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    report_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON full report
    posts_analyzed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    posts_failed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    analysis_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ai_cost: Mapped[float | None] = mapped_column(Float, nullable=True, default=0.0)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = created_at_column()


class ChannelSnapshot(Base):
    __tablename__ = "channel_snapshots"

    id: Mapped[uuid.UUID] = uuid_pk()
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True
    )
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("channel_analysis.id", ondelete="SET NULL"), nullable=True
    )
    snapshot_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    trust_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    scam_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    advertising_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "channel_id", name="uq_favorites_user_channel"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = created_at_column()

    user = relationship("User", back_populates="favorites")
    channel = relationship("Channel")


class Monitoring(Base):
    __tablename__ = "monitoring"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True
    )
    interval: Mapped[str] = mapped_column(String(32), default=MonitoringInterval.DAILY.value)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = created_at_column()

    user = relationship("User", back_populates="monitorings")
    channel = relationship("Channel")


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    channel_username: Mapped[str] = mapped_column(String(255), index=True)
    channel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default=JobStatus.PENDING.value, index=True
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total_posts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    analyzed_posts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_posts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("channel_analysis.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


# Useful composite indexes (declarative).
Index("ix_posts_channel_date", Post.channel_id, Post.date)
Index("ix_channel_analysis_channel_created", ChannelAnalysis.channel_id, ChannelAnalysis.created_at)
