"""AI provider factory.

Selects the concrete provider from configuration so callers never know
which backend is used. Currently supports ``openai`` and ``mock``; new
providers (Anthropic, Google, local) are added here without changing
business logic.
"""

from __future__ import annotations

from functools import lru_cache

from app.ai.base import AIError, AIProvider
from app.config import get_settings


@lru_cache
def get_ai_provider() -> AIProvider:
    """Return the configured AI provider singleton."""
    settings = get_settings()
    kind = settings.ai_provider.lower().strip()

    if kind == "mock":
        from app.ai.mock_provider import MockAIProvider

        return MockAIProvider()
    if kind == "openai":
        from app.ai.openai_provider import OpenAIProvider

        return OpenAIProvider()

    raise AIError(f"Unknown AI provider: {settings.ai_provider!r}")
