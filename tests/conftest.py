"""Shared pytest configuration.

Tests do not require a real AI API or a Telegram connection. Configuration
is overridden to use an in-memory SQLite database and the deterministic
MockAIProvider.
"""

from __future__ import annotations

import os
import sys

# Ensure the project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Override config BEFORE app modules are imported
os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault(
    "DATABASE_URL", "sqlite+aiosqlite:///:memory:"
)
os.environ.setdefault("ANALYSIS_POST_LIMIT", "20")
os.environ.setdefault("MAX_POSTS_PER_ANALYSIS", "20")
os.environ.setdefault("FREE_ANALYSES_PER_DAY", "3")
os.environ.setdefault("LOG_LEVEL", "ERROR")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_session_factory, get_engine  # noqa: E402

# Reset the settings cache so env overrides apply
get_settings.cache_clear()


@pytest.fixture()
def settings():
    return get_settings()


@pytest_asyncio.fixture
async def db_session():
    """Fresh in-memory SQLite session with schema created."""
    from app.database import models  # noqa: F401
    from app.database.session import _engine, _session_factory

    # reset singletons so a new in-memory DB is created per test
    if _engine is not None:
        await _engine.dispose()
    import app.database.session as session_module

    session_module._engine = None
    session_module._session_factory = None

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
