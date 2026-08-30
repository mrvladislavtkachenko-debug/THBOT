"""Content Quality Score computation (0-100).

Factors: usefulness, depth, originality, structure, sources,
informativeness and consistency. Quality is derived from per-post AI
scores aggregated across the analyzed sample.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.utils.text import clamp


@dataclass
class QualityInput:
    quality_avg: float = 0.0        # 0-10 avg per-post quality
    originality_avg: float = 0.0    # 0-10 avg per-post originality
    source_quality: float = 0.0     # 0-100 averaged
    consistency: float = 0.0        # 0-100
    info_density: float = 0.0       # 0-100 (postings/topic density)
    depth_avg: float = 0.0          # 0-10 (approximated from factual_support)
    failed_ratio: float = 0.0       # 0-100 share of failed analyses


@dataclass
class QualityScore:
    score: float = 0.0
    factors: list[str] = field(default_factory=list)


def compute_quality(data: QualityInput) -> QualityScore:
    """Compute the content quality score."""
    # Normalize each component to 0-100.
    quality_c = clamp(data.quality_avg * 10.0)
    originality_c = clamp(data.originality_avg * 10.0)
    depth_c = clamp(data.depth_avg * 10.0)
    source_c = clamp(data.source_quality)
    consistency_c = clamp(data.consistency)
    info_c = clamp(data.info_density)
    fail_penalty = clamp(data.failed_ratio) * 0.5  # penalize failed analyses

    score = round(clamp(
        0.30 * quality_c
        + 0.15 * originality_c
        + 0.10 * depth_c
        + 0.20 * source_c
        + 0.10 * consistency_c
        + 0.15 * info_c
        - fail_penalty,
        0, 100,
    ), 1)

    factors = []
    if score >= 80:
        factors.append("Высокое качество и информативность контента")
    elif score >= 60:
        factors.append("Хорошее качество контента")
    elif score >= 40:
        factors.append("Среднее качество контента")
    else:
        factors.append("Низкое качество контента")

    if source_c >= 60:
        factors.append("Хорошая опора на источники")
    if originality_c >= 60:
        factors.append("Контент в основном оригинальный")
    if data.failed_ratio > 20:
        factors.append(f"Не удалось проанализировать {round(data.failed_ratio)}% постов")

    return QualityScore(score=score, factors=factors)
