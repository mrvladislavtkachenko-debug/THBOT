"""Application configuration.

All runtime configuration lives here and is loaded from environment
variables / the ``.env`` file. Nothing in the codebase hardcodes tokens,
keys, limits or AI model names — everything is configurable.

Uses pydantic-settings so that every value is validated and typed.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Typed application settings loaded from environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "TG Channel Analyzer"
    app_language: str = "en_US"

    # --- Telegram Bot ---
    bot_token: str = ""

    # --- Telegram MTProto ---
    telegram_api_id: int = 0
    telegram_api_hash: str = ""

    # --- AI ---
    ai_provider: str = "openai"  # openai | mock
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # --- Database ---
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/tg_analyzer"
    )

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Admin ---
    admin_ids: str = ""

    # --- Analysis behaviour ---
    analysis_post_limit: int = Field(default=100, ge=1, le=5000)
    max_posts_per_analysis: int = Field(default=100, ge=1, le=5000)
    analysis_cache_hours: int = Field(default=24, ge=1)

    # --- Rate limiting ---
    free_analyses_per_day: int = Field(default=3, ge=0)

    # --- Job queue ---
    job_queue_backend: str = "asyncio"  # asyncio | redis

    # --- Logging ---
    log_level: str = "INFO"

    # --- Locale ---
    default_language: str = "ru"

    # --- Derived helpers ---

    @field_validator("admin_ids")
    @classmethod
    def _parse_admin_ids(cls, value: str) -> str:
        return (value or "").strip()

    @property
    def admin_id_list(self) -> list[int]:
        """Parsed list of administrator Telegram IDs."""
        ids: list[int] = []
        for part in self.admin_ids.split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
        return ids

    @property
    def prompts_dir(self) -> Path:
        return BASE_DIR / "prompts"

    @property
    def locales_dir(self) -> Path:
        return BASE_DIR / "locales"

    @property
    def telegram_enabled(self) -> bool:
        """True when MTProto credentials are configured."""
        return bool(self.telegram_api_id and self.telegram_api_hash)

    @property
    def ai_enabled(self) -> bool:
        """True when a real AI provider is configured."""
        if self.ai_provider == "mock":
            return False
        return bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
