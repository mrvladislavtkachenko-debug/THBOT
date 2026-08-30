"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-30

Creates all tables from the SQLAlchemy metadata. For subsequent schema
changes, use `alembic revision --autogenerate -m "..."`.
"""

from alembic import op
import sqlalchemy as sa  # noqa: F401

from app.database.base import Base
from app.database import models  # noqa: F401  (register all tables)

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
