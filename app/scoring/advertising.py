"""Advertising Load computation (0-100) and level mapping.

High advertising is *not* evidence of fraud — it's a separate dimension.
Level bands:

    very_low, low, medium, high, very_high
"""

from __future__ import annotations

from dataclasses import dataclass

from app.utils.text import clamp


@dataclass
class AdvertisingInput:
    advertising_ratio: float = 0.0   # 0-1 share of ad posts
    avg_advertising_score: float = 0.0  # 0-10 avg per-post ad score
    explicit_promotions: int = 0     # number of clearly promoted posts


def advertising_ratio_to_level(ratio: float) -> str:
    if ratio < 0.05:
        return "very_low"
    if ratio < 0.15:
        return "low"
    if ratio < 0.30:
        return "medium"
    if ratio < 0.50:
        return "high"
    return "very_high"


def level_label(level: str) -> str:
    labels = {
        "very_low": "Очень низкая",
        "low": "Низкая",
        "medium": "Средняя",
        "high": "Высокая",
        "very_high": "Очень высокая",
    }
    return labels.get(level, level)


def compute_advertising_load(data: AdvertisingInput) -> tuple[float, str]:
    """Return (score 0-100, level)."""
    ratio_score = clamp(data.advertising_ratio * 100.0)  # 0-100
    avg_score = clamp(data.advertising_ratio * 100.0) if data.advertising_ratio else 0.0

    # blend the ratio and per-post ad intensity
    score = round(clamp(
        0.6 * ratio_score + 0.4 * clamp(data.avg_advertising_score * 10.0)
    ), 1)
    level = advertising_ratio_to_level(data.advertising_ratio)
    return score, level
