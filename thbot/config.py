"""Настройки приложения. Все значения читаются из .env / окружения."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _models(env_name: str, default: list[str]) -> list[str]:
    raw = os.getenv(env_name, "")
    return [m.strip() for m in raw.split(",") if m.strip()] or default


@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")

    classifier_models: list[str] = field(
        default_factory=lambda: _models(
            "CLASSIFIER_MODELS",
            [
                "deepseek/deepseek-chat-v3.1:free",
                "meta-llama/llama-3.3-70b-instruct:free",
                "qwen/qwen-2.5-72b-instruct:free",
            ],
        )
    )
    synthesis_models: list[str] = field(
        default_factory=lambda: _models(
            "SYNTHESIS_MODELS",
            [
                "deepseek/deepseek-chat-v3.1:free",
                "meta-llama/llama-3.3-70b-instruct:free",
                "qwen/qwen-2.5-72b-instruct:free",
            ],
        )
    )

    fetch_posts_limit: int = int(os.getenv("FETCH_POSTS_LIMIT", "100"))
    classify_batch_size: int = int(os.getenv("CLASSIFY_BATCH_SIZE", "25"))
    cache_ttl_hours: int = int(os.getenv("CACHE_TTL_HOURS", "168"))
    user_daily_limit: int = int(os.getenv("USER_DAILY_LIMIT", "5"))
    db_path: str = os.getenv("DB_PATH", "thbot.db")


settings = Settings()
