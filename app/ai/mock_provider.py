"""Deterministic mock AI provider.

Used for local development and unit tests so no AI API is required. It
derives plausible values from the post text (topic heuristics, link
presence, ad keywords) so downstream services can be exercised end-to-end.
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.ai.base import AIProvider
from app.schemas import (
    ChannelAnalysisResult,
    PostAnalysisResult,
    ScamReport,
)
from app.services.url_analyzer import analyze_text

AD_KEYWORDS = ("реклам", "promo", "скидк", "сейл", "offer", "подпишись",
               "оформи", "купить", "buy", "купи", "партнер", "сотрудничество")
URGENCY_KEYWORDS = ("только сегодня", "успей", "последний шанс", "срочно",
                    "limited", "hurry", "ограничен", "пока не поздно")
PROFIT_KEYWORDS = ("гарантированн", "прибыл", "доход", "заработ", "без риска",
                   "100%", "вернет", "удво", "пассивный доход", "invest")


class MockAIProvider(AIProvider):
    """Rule-based mock provider with a fixed hash seed."""

    name = "mock"

    async def analyze_post(self, text: str | None) -> PostAnalysisResult:
        text = text or ""
        lower = text.lower()
        urls = analyze_text(text)

        topic = _guess_topic(lower)

        is_ad = any(k in lower for k in AD_KEYWORDS)
        advertising_score = 8.0 if is_ad else min(2.0 + len(urls.links) * 1.0, 6.0)

        scam_signals: list[str] = []
        if any(k in lower for k in PROFIT_KEYWORDS):
            scam_signals.append("guaranteed_profit")
        if any(k in lower for k in URGENCY_KEYWORDS):
            scam_signals.append("urgency")
        if ("перевести" in lower or "перевод" in lower or "перевед" in lower
                or "кошелек" in lower or "деньги" in lower):
            scam_signals.append("payment_request")
        if urls.shortener_count > 0 or urls.risky_tld_count > 0:
            scam_signals.append("suspicious_link")
        if "без риска" in lower:
            scam_signals.append("no_risk_claim")

        manipulation_score = min(3.0 + len(scam_signals) * 1.5, 10.0)
        factual_support = 7.0 if urls.total > 0 else None
        quality_score = _quality_from_text(len(text), urls.total, is_ad)

        return PostAnalysisResult(
            topic=topic,
            subtopic=None,
            post_type="advertisement" if is_ad else "news",
            language=_detect_language(lower),
            quality_score=quality_score,
            originality_score=6.0,
            factual_support=factual_support,
            source_quality="strong" if urls.total >= 2 else ("weak" if urls.total else "none"),
            advertising_score=advertising_score,
            manipulation_score=round(manipulation_score, 1),
            scam_signals=scam_signals,
            summary=text[:80] or "(пустой пост)",
            why_valuable="Демо-анализ (mock provider)",
        )

    async def analyze_channel(
        self,
        channel_meta: dict[str, Any],
        posts_summary: list[dict[str, Any]],
    ) -> ChannelAnalysisResult:
        total = len(posts_summary) or 1
        ads = sum(1 for p in posts_summary if p.get("post_type") == "advertisement")
        return ChannelAnalysisResult(
            main_topic="Разное",
            topics={"Разное": 100.0},
            audience=["Широкой аудитории"],
            audience_not_for=[],
            style=["neutral"],
            tone="neutral",
            content_mix={
                "original_content_percent": 70.0,
                "reposts_percent": 10.0,
                "advertisement_percent": round(ads / total * 100, 1),
                "news_percent": round((total - ads) / total * 100, 1),
            },
            author_style_summary="Демо-режим (mock provider).",
            quality_factors=["Оригинальный контент"],
            quality_risks=[],
            summary="Демо-анализ канала без подключения AI.",
            verdict_reasoning="Mock-режим.",
        )

    async def analyze_scam_risk(self, posts: list[dict[str, Any]]) -> ScamReport:
        signal_counts: dict[str, int] = {}
        for p in posts:
            for sig in p.get("scam_signals", []) or []:
                signal_counts[sig] = signal_counts.get(sig, 0) + 1
        score = sum(
            min(c, 5) * 4.0 for c in signal_counts.values()
        )
        from app.scoring.scam import score_to_level
        level = score_to_level(min(score, 100))
        return ScamReport(
            score=round(min(score, 100), 1),
            level=level,
            findings=[f"{k}: {v}" for k, v in signal_counts.items()],
            signals=signal_counts,
            evidence=[],
        )


def _guess_topic(lower: str) -> str:
    topics = {
        "ai": ("AI", ("нейросет", "gpt", "ml", "ии", "чатгпт", "artificial")),
        "crypto": ("Криптовалюты", ("bitcoin", "btc", "крипт", "ton", "ethereum", "usdt")),
        "finance": ("Финансы", ("инвестиц", "финанс", "акци", "stock", "traiding", "трейд")),
        "business": ("Бизнес", ("бизнес", "предприним", "стартап", "startup")),
        "tech": ("Технологии", ("технолог", "гаджет", "software", "программ")),
    }
    for key, (label, kws) in topics.items():
        if any(k in lower for k in kws):
            return label
    return "Разное"


def _detect_language(lower: str) -> str:
    cyr = sum(1 for ch in lower if "\u0400" <= ch <= "\u04FF")
    lat = sum(1 for ch in lower if ch.isascii() and ch.isalpha())
    return "ru" if cyr >= lat else "en"


def _quality_from_text(length: int, links: int, is_ad: bool) -> float:
    base = 5.0
    base += min(length / 300, 3.0)
    base += min(links, 3) * 0.5
    if is_ad:
        base -= 2.0
    return round(max(1.0, min(10.0, base)), 1)
