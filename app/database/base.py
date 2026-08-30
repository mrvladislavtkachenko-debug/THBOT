"""SQLAlchemy declarative base and shared column helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, MetaData
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base with a fixed naming convention."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def uuid_pk() -> Mapped[uuid.UUID]:
    """Return a mapped UUID primary-key column."""
    return mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


def jsonb_column(default: dict | list | None = None) -> Mapped:
    """Return a JSONB column usable on PostgreSQL."""
    return mapped_column(JSONB, nullable=True, default=default)


def ts_column(default: bool = True) -> Mapped[datetime]:
    """Return a UTC timestamp column (server default NOW when requested)."""
    if default:
        return mapped_column(
            DateTime(timezone=True), nullable=False, default=utcnow, server_default=None
        )
    return mapped_column(DateTime(timezone=True), nullable=True, default=None)


def created_at_column() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


def updated_at_column() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
