"""Scam Risk Score computation (0-100) and level mapping.

This engine works independently from the general AI rating. It aggregates
scam signals detected in individual posts (both via AI and via rule-based
URL/link analysis) into a single risk score with level bands:

    0-20     Low
    21-40    Moderate
    41-60    Elevated
    61-80    High
    81-100   Critical
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.utils.text import clamp

# Signal -> severity weight (higher = more severe)
SIGNAL_WEIGHTS: dict[str, float] = {
    "guaranteed_profit": 6.0,
    "financial_pressure": 5.0,
    "urgency": 3.0,
    "payment_request": 8.0,
    "crypto_transfer": 7.0,
    "suspicious_link": 6.0,
    "impersonation": 8.0,
    "fake_authority": 6.0,
    "unrealistic_claim": 5.0,
    "income_promise": 6.0,
    "get_rich_quick": 6.0,
    "no_risk_claim": 5.0,
    "limited_offer": 4.0,
    "personal_data_request": 7.0,
}


@dataclass
class ScamInput:
    """Signals aggregated from all analyzed posts."""

    signal_counts: dict[str, int] = field(default_factory=dict)
    total_posts: int = 0
    suspicious_links: int = 0
    payment_requests: int = 0
    manipulation_avg: float = 0.0  # 0-10


@dataclass
class ScamRiskScore:
    score: float = 0.0
    level: str = "low"
    reasons: list[str] = field(default_factory=list)


def score_to_level(score: float) -> str:
    if score <= 20:
        return "low"
    if score <= 40:
        return "moderate"
    if score <= 60:
        return "elevated"
    if score <= 80:
        return "high"
    return "critical"


def _signal_label(signal: str) -> str:
    labels = {
        "guaranteed_profit": "обещания гарантированной доходности",
        "financial_pressure": "давление через финансовые стимулы",
        "urgency": "агрессивные призывы к срочному действию",
        "payment_request": "просьбы о переводе средств",
        "crypto_transfer": "криптовалютные переводы",
        "suspicious_link": "подозрительные внешние ссылки",
        "impersonation": "попытки выдать себя за официальный аккаунт",
        "fake_authority": "ложный авторитет",
        "unrealistic_claim": "нереалистичные обещания",
        "income_promise": "обещания быстрого дохода",
        "get_rich_quick": "схемы быстрого обогащения",
        "no_risk_claim": "заявления «без риска»",
        "limited_offer": "искусственный дефицит",
        "personal_data_request": "запросы персональных данных",
    }
    return labels.get(signal, signal.replace("_", " "))


def compute_scam_risk(data: ScamInput) -> ScamRiskScore:
    """Aggregate scam signals into a risk score and reasons."""
    total = max(data.total_posts, 1)
    raw = 0.0

    for signal, count in data.signal_counts.items():
        weight = SIGNAL_WEIGHTS.get(signal, 3.0)
        # nonlinear: presence scaled by count, capped
        raw += weight * min(count, 5) ** 0.5

    raw += data.suspicious_links * 4.0
    raw += data.payment_requests * 5.0

    # manipulation contribution (0-10 -> up to 15 points)
    raw += clamp(data.manipulation_avg) * 1.5

    # normalize roughly into 0-100 scale
    score = round(clamp(raw, 0, 100), 1)
    level = score_to_level(score)

    reasons: list[str] = []
    if score <= 20:
        reasons.append("Явных признаков повышенного риска не обнаружено")
    else:
        for signal, count in data.signal_counts.items():
            if count > 0:
                severity = "🔴" if count >= 3 else "🟠"
                reasons.append(
                    f"{severity} {count} постов содержат {_signal_label(signal)}"
                )
        if data.payment_requests > 0:
            reasons.append(f"🟠 обнаружено {data.payment_requests} просьб о переводе средств")
        if data.suspicious_links > 0:
            reasons.append(f"🟠 обнаружено {data.suspicious_links} подозрительных ссылок")

    return ScamRiskScore(score=score, level=level, reasons=reasons)
