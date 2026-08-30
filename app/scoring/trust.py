"""Trust Score computation (0-100).

The Trust Score is a weighted combination of several factors defined in
the technical specification. Weights and factor formulas are isolated here
so they can be tuned without touching the rest of the system.

Weights:
    source_quality            25%
    factual_support           20%
    originality               15%
    content_consistency       10%
    transparency              10%
    advertising_behavior       5%
    manipulation               5%
    external_risk_signals     10%
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.utils.text import clamp


@dataclass
class TrustInput:
    """Aggregated inputs needed to compute trust."""

    source_quality: float = 0.0          # 0-100 (averaged across posts)
    factual_support: float = 0.0         # 0-100 (averaged; None -> 0)
    originality: float = 0.0             # 0-100 (original content share)
    content_consistency: float = 0.0     # 0-100 (topic concentration)
    transparency: float = 0.0            # 0-100 (discloses ads, uses sources)
    advertising_behavior: float = 0.0    # 0-100 (higher = more ads => lower trust)
    manipulation: float = 0.0            # 0-100 (higher = more manipulation => lower)
    external_risk: float = 0.0           # 0-100 (higher = more scam signals => lower)


@dataclass
class TrustScore:
    score: float = 0.0
    positive_factors: list[str] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)


WEIGHTS: dict[str, float] = {
    "source_quality": 0.25,
    "factual_support": 0.20,
    "originality": 0.15,
    "content_consistency": 0.10,
    "transparency": 0.10,
    "advertising_behavior": 0.05,
    "manipulation": 0.05,
    "external_risk": 0.10,
}

# Advertising and manipulation are *penalty* factors: higher raw value
# should lower the trust score, so we invert them.
INVERTED_FACTORS = {"advertising_behavior", "manipulation", "external_risk"}


def compute_trust(data: TrustInput) -> TrustScore:
    """Compute the trust score and collect explainability factors."""
    weighted = 0.0
    positive: list[str] = []
    risk: list[str] = []

    for name, weight in WEIGHTS.items():
        raw = getattr(data, name)
        if name in INVERTED_FACTORS:
            # higher raw = lower contribution
            contribution = weight * (100.0 - clamp(raw))
        else:
            contribution = weight * clamp(raw)
        weighted += contribution

    score = round(clamp(weighted), 1)

    # --- Explainability ---
    if data.source_quality >= 60:
        positive.append("Автор часто использует источники")
    elif data.source_quality < 30:
        risk.append("Большинство утверждений не имеют источников")

    if data.factual_support >= 60:
        positive.append("Утверждения хорошо фактически обоснованы")
    elif data.factual_support < 30:
        risk.append("Слабая фактическая обоснованность публикаций")

    if data.originality >= 60:
        positive.append("Высокая доля оригинального контента")
    else:
        risk.append("Много перепостов или пересказов")

    if data.content_consistency >= 60:
        positive.append("Стабильная тематика канала")
    else:
        risk.append("Нестабильная тематика")

    if data.transparency >= 60:
        positive.append("Канал достаточно прозрачен (источники, пометки рекламы)")
    else:
        risk.append("Недостаточная прозрачность (реклама без пометок)")

    if data.advertising_behavior >= 60:
        risk.append("Высокая рекламная нагрузка")
    else:
        positive.append("Умеренная рекламная нагрузка")

    if data.manipulation >= 60:
        risk.append("Присутствуют манипулятивные приёмы")

    if data.external_risk >= 40:
        risk.append("Обнаружены внешние сигналы риска")

    # Cap risk factors shown
    return TrustScore(score=score, positive_factors=positive, risk_factors=risk)
