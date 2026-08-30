"""Overall verdict computation.

Produces one of:
    STRONGLY_RECOMMEND, RECOMMEND, NEUTRAL, CAUTION, NOT_RECOMMENDED
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas import Verdict


@dataclass
class VerdictInput:
    quality: float = 0.0
    trust: float = 0.0
    scam_risk: float = 0.0
    advertising: float = 0.0


def compute_verdict(data: VerdictInput) -> Verdict:
    # Scam risk is the dominant gate: high risk overrides everything.
    if data.scam_risk >= 61:
        return Verdict.NOT_RECOMMENDED
    if data.scam_risk >= 41:
        return Verdict.CAUTION

    base = (data.quality + data.trust) / 2.0

    if data.advertising >= 70:
        # heavy advertising pulls the recommendation down
        base -= 12

    if base >= 80:
        return Verdict.STRONGLY_RECOMMEND
    if base >= 65:
        return Verdict.RECOMMEND
    if base >= 50:
        return Verdict.NEUTRAL
    return Verdict.CAUTION


VERDICT_LABELS: dict[Verdict, str] = {
    Verdict.STRONGLY_RECOMMEND: "👍 Стоит подписаться",
    Verdict.RECOMMEND: "👍 Можно подписаться",
    Verdict.NEUTRAL: "➖ Нейтрально — решайте сами",
    Verdict.CAUTION: "⚠️ Можно подписаться, но с осторожностью",
    Verdict.NOT_RECOMMENDED: "🚨 Не рекомендуется",
}

VERDICT_ICONS: dict[Verdict, str] = {
    Verdict.STRONGLY_RECOMMEND: "🏆",
    Verdict.RECOMMEND: "👍",
    Verdict.NEUTRAL: "➖",
    Verdict.CAUTION: "⚠️",
    Verdict.NOT_RECOMMENDED: "🚨",
}
