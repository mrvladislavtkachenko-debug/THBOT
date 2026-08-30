"""Tests for the scoring modules (trust, quality, scam, advertising)."""

from app.scoring.advertising import compute_advertising_load, AdvertisingInput
from app.scoring.quality import compute_quality, QualityInput
from app.scoring.scam import compute_scam_risk, ScamInput, score_to_level
from app.scoring.trust import compute_trust, TrustInput


def test_trust_high():
    t = compute_trust(TrustInput(
        source_quality=90, factual_support=90, originality=80,
        content_consistency=90, transparency=80, advertising_behavior=10,
        manipulation=5, external_risk=10,
    ))
    assert 0 <= t.score <= 100
    assert t.score >= 70
    assert t.positive_factors


def test_trust_low():
    t = compute_trust(TrustInput(
        source_quality=0, factual_support=0, originality=10,
        content_consistency=20, transparency=10, advertising_behavior=90,
        manipulation=90, external_risk=80,
    ))
    assert t.score <= 40
    assert t.risk_factors


def test_trust_bounds():
    t = compute_trust(TrustInput())
    assert 0 <= t.score <= 100


def test_quality():
    q = compute_quality(QualityInput(
        quality_avg=8.0, originality_avg=8.0, source_quality=80,
        consistency=90, info_density=90, depth_avg=8.0, failed_ratio=0,
    ))
    assert 0 <= q.score <= 100
    assert q.score >= 70


def test_quality_with_failures():
    q = compute_quality(QualityInput(failed_ratio=50))
    assert q.score <= 100


def test_scam_levels():
    assert score_to_level(10) == "low"
    assert score_to_level(30) == "moderate"
    assert score_to_level(50) == "elevated"
    assert score_to_level(70) == "high"
    assert score_to_level(90) == "critical"


def test_scam_score():
    s = compute_scam_risk(ScamInput(
        signal_counts={"guaranteed_profit": 3, "urgency": 2, "payment_request": 1},
        total_posts=10, suspicious_links=2, payment_requests=1, manipulation_avg=8.0,
    ))
    assert s.score > 40
    assert s.reasons


def test_scam_clean():
    s = compute_scam_risk(ScamInput(signal_counts={}, total_posts=10))
    assert s.score <= 20
    assert s.level == "low"


def test_advertising():
    score, level = compute_advertising_load(AdvertisingInput(
        advertising_ratio=0.5, avg_advertising_score=8.0,
    ))
    assert score > 50
    assert level in ("high", "very_high")
