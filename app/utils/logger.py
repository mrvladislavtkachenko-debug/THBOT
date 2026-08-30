"""Logging configuration.

Provides a module-level ``get_logger`` factory and an ``analysis`` logger
namespace used to trace per-analysis progress.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from app.config import get_settings


def configure_logging() -> None:
    """Configure root logging from settings."""
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    logging.basicConfig(
        level=level,
        format=(
            "%(asctime)s | %(levelname)-8s | %(name)s | "
            "%(message)s"
        ),
        handlers=handlers,
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger.

    Never logs sensitive data — the analysis logger accepts structured
    ``extra`` context (user_id, channel, analysis_id, stage, duration)
    but the formatter deliberately ignores arbitrary keys.
    """
    return logging.getLogger(name)


def log_analysis(
    analysis_id: str,
    stage: str,
    channel: str | None = None,
    user_id: int | None = None,
    error: str | None = None,
    duration: float | None = None,
    **extra: Any,
) -> None:
    """Emit a structured, safe analysis-log record."""
    logger = get_logger("analysis")
    ctx = {
        "analysis_id": analysis_id,
        "stage": stage,
    }
    if channel:
        ctx["channel"] = channel
    if user_id:
        ctx["user_id"] = user_id
    if error:
        ctx["error"] = error
    if duration is not None:
        ctx["duration_ms"] = round(duration * 1000, 1)
    # Only include allow-listed keys — never arbitrary user payloads.
    logger.info(
        "%s stage=%s %s",
        analysis_id[:8],
        stage,
        " ".join(f"{k}={v}" for k, v in ctx.items() if k not in ("stage",)),
    )
