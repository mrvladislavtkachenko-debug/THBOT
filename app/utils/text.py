"""Text formatting helpers."""

from __future__ import annotations

import re
from typing import Iterable


def truncate(text: str | None, limit: int = 300, suffix: str = "…") -> str:
    """Truncate text to ``limit`` characters, preserving whole words."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - len(suffix)]
    # cut at the last space to avoid splitting a word
    space = cut.rfind(" ")
    if space > limit // 2:
        cut = cut[:space]
    return cut + suffix


def clean_text(text: str | None) -> str:
    """Normalise whitespace / control characters for display."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text.strip()


def format_percent(value: float, digits: int = 0) -> str:
    return f"{value:.{digits}f}%"


def join(items: Iterable[str], sep: str = ", ") -> str:
    return sep.join(x for x in items if x)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def first_line(text: str | None, limit: int = 120) -> str:
    if not text:
        return ""
    text = clean_text(text)
    first = text.split("\n")[0]
    return truncate(first, limit)


def escape_markdown(text: str) -> str:
    """Escape aiogram MarkdownV2 special characters."""
    specials = r"_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in specials else c for c in str(text))
