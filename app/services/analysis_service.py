"""Central AnalysisService.

Orchestrates the full analysis pipeline described in the spec:

    validate channel -> collect metadata -> collect posts -> check cache
    -> analyze posts -> aggregate -> analyze channel -> analyze scam risk
    -> calculate scores -> select best posts -> save analysis -> report

Telegram handlers never perform this logic themselves; they call into
this service and receive a :class:`AnalysisOutcome`.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from statistics import mean, median
from typing import Any, Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIError, AIProvider
from app.ai.channel_analyzer import ChannelAnalyzer
from app.ai.factory import get_ai_provider
from app.ai.post_analyzer import PostAnalyzer
from app.ai.scam_analyzer import ScamAnalyzer
from app.config import get_settings
from app.database.models import (
    AnalysisJob,
    Channel,
    ChannelAnalysis,
    ChannelSnapshot,
    JobStatus,
    Post,
    PostAnalysis,
)
from app.database.repositories.analyses import AnalysisRepository
from app.database.repositories.channels import ChannelRepository
from app.database.repositories.posts import PostRepository
from app.scoring.advertising import AdvertisingInput, compute_advertising_load
from app.scoring.quality import compute_quality, QualityInput
from app.scoring.scam import compute_scam_risk, ScamInput, score_to_level
from app.scoring.trust import compute_trust, TrustInput
from app.scoring.verdict import compute_verdict, VerdictInput
from app.schemas import (
    ChannelAnalysisResult,
    ChannelInfo,
    PostAnalysisResult,
    PostData,
    ScamReport,
)
from app.services.cache_service import AnalysisCache
from app.services.report_service import AnalysisOutcome, BestPostView, ReportService
from app.services.url_analyzer import (
    aggregate_url_analyses,
    analyze_text,
)
from app.telegram.channel_service import ChannelService
from app.telegram.client import TelegramChannelNotFound, TelegramClientError
from app.telegram.post_service import PostService, post_content_hash
from app.utils.logger import get_logger
from app.utils.text import first_line

logger = get_logger("analysis")

ProgressCallback = Callable[[str], Awaitable[None]]
StageCallback = Callable[[str], Awaitable[None]]

ANALYSIS_VERSION = "1.0"
PROMPT_VERSION = "1.0"


class ChannelAnalysisError(Exception):
    """Raised for user-facing analysis failures."""


@dataclass
class AnalysisResult:
    outcome: AnalysisOutcome
    analysis_id: UUID
    cached: bool = False
    analysis: ChannelAnalysis | None = None


class AnalysisService:
    """Main entry point for analyzing Telegram channels."""

    def __init__(
        self,
        session: AsyncSession,
        channel_service: ChannelService,
        provider: AIProvider | None = None,
        cache: AnalysisCache | None = None,
    ) -> None:
        self._session = session
        self._channel_service = channel_service
        self._provider = provider or get_ai_provider()
        self._cache = cache or AnalysisCache()
        self._settings = get_settings()
        self._reports = ReportService()

        self._channel_repo = ChannelRepository(session)
        self._post_repo = PostRepository(session)
        self._analysis_repo = AnalysisRepository(session)
        self._post_service = PostService(self._post_repo)

        self._post_analyzer = PostAnalyzer(self._provider)
        self._channel_analyzer = ChannelAnalyzer(self._provider)
        self._scam_analyzer = ScamAnalyzer(self._provider)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def analyze(
        self,
        username: str,
        user_id: UUID | None,
        force_refresh: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> AnalysisResult:
        """Run the full analysis pipeline for ``username``."""
        username = username.lower().lstrip("@")
        started = time.monotonic()

        async def progress(msg: str) -> None:
            if on_progress:
                await on_progress(msg)

        await progress("🔎 Получаю информацию о канале...")

        # 1. Validate + collect metadata
        try:
            info = await self._channel_service.validate_and_get_info(username)
        except TelegramChannelNotFound as exc:
            raise ChannelAnalysisError(str(exc))
        except TelegramClientError as exc:
            raise ChannelAnalysisError(f"❌ Не удалось получить данные канала.\n\n{exc}")

        if info.is_private:
            raise ChannelAnalysisError(
                "🔒 Этот канал приватный.\n\n"
                "Я могу анализировать только публично доступные каналы."
            )
        if info.is_group:
            raise ChannelAnalysisError(
                "🔒 Это группа, а не канал. Я анализирую только публичные каналы."
            )

        # 2. Cache check
        if not force_refresh:
            cached = await self._cache.get(username)
            if cached is not None:
                outcome = _outcome_from_dict(cached)
                await progress("✅ Анализ получен из кэша (без повторного AI-запроса).")
                return AnalysisResult(
                    outcome=outcome,
                    analysis_id=UUID(cached.get("analysis_id", "")),
                    cached=True,
                )

        # 3. Upsert channel record
        channel, _ = await self._channel_repo.get_or_create_by_username(username)
        await self._channel_repo.update(
            channel,
            title=info.title,
            description=info.description,
            subscriber_count=info.subscriber_count,
            telegram_channel_id=info.telegram_channel_id,
            channel_url=info.url,
        )

        # 4. Collect posts
        limit = min(
            self._settings.analysis_post_limit, self._settings.max_posts_per_analysis
        )
        try:
            posts_data = await self._channel_service.get_posts(username, limit)
        except (TelegramChannelNotFound, TelegramClientError) as exc:
            raise ChannelAnalysisError(f"❌ Не удалось получить посты канала.\n\n{exc}")

        await progress(f"📥 Получено {len(posts_data)} постов.")

        # 5. Persist posts
        posts = await self._post_service.persist(channel.id, posts_data)
        if not posts:
            raise ChannelAnalysisError("❌ В канале нет доступных публикаций.")

        # 6. Analyze posts (concurrency-limited)
        await progress("🧠 Анализирую содержание...")
        post_results, analyzed, failed = await self._analyze_posts(channel.id, posts, progress)

        await progress("🛡 Проверяю потенциальные риски...")

        # 7. URL analysis (rule-based)
        url_analyses = [analyze_text(p.text) for p in posts]
        url_summary = aggregate_url_analyses(url_analyses)

        # 8. Build post payloads + channel-level AI analysis
        post_payloads = []
        for p, (res, ok) in zip(posts, post_results):
            norm = res.normalized() if ok and res else {}
            post_payloads.append({
                "message_id": p.telegram_message_id,
                "text": p.text or "",
                "post_type": norm.get("post_type"),
                "topic": norm.get("topic"),
                "quality_score": norm.get("quality_score"),
                "scam_signals": norm.get("scam_signals", []),
                "summary": norm.get("summary"),
            })

        channel_result = await self._safe_channel_analyze(
            info, post_payloads, post_results
        )

        # 9. Aggregation + metrics
        metrics = _aggregate_metrics(post_results, posts, posts_data)

        # 10. Scam risk (AI + rule-based combined)
        scam = await self._safe_scam_analyze(post_payloads, post_results)
        scam_input = ScamInput(
            signal_counts=metrics["scam_signals"],
            total_posts=max(len(posts), 1),
            suspicious_links=url_summary.suspicious_count,
            payment_requests=metrics["payment_requests"],
            manipulation_avg=metrics["manipulation_avg"],
        )
        scam_score = compute_scam_risk(scam_input)
        # Blend with AI-provided scam report if present
        if scam is not None and scam.score > 0:
            blended = (scam_score.score + scam.score) / 2
            if blended > scam_score.score:
                scam_score.score = round(blended, 1)
                scam_score.level = score_to_level(scam_score.score)

        # 11. Compute scores
        quality_in = QualityInput(
            quality_avg=metrics["quality_avg"],
            originality_avg=metrics["originality_avg"],
            source_quality=metrics["source_quality"] * 10.0,
            consistency=metrics["consistency"],
            info_density=metrics["info_density"],
            depth_avg=metrics["depth_avg"],
            failed_ratio=metrics["failed_ratio"],
        )
        quality_score = compute_quality(quality_in)

        trust_in = TrustInput(
            source_quality=metrics["source_quality"] * 10.0,
            factual_support=metrics["factual_support_avg"] * 10.0,
            originality=metrics["originality_pct"],
            content_consistency=metrics["consistency"],
            transparency=metrics["transparency"],
            advertising_behavior=metrics["advertising_pct"],
            manipulation=metrics["manipulation_avg"] * 10.0,
            external_risk=scam_score.score,
        )
        trust_score = compute_trust(trust_in)

        ad_input = AdvertisingInput(
            advertising_ratio=metrics["advertising_ratio"],
            avg_advertising_score=metrics["advertising_score_avg"],
        )
        advertising_score, ad_level = compute_advertising_load(ad_input)

        originality_score = metrics["originality_pct"]
        activity_posts_day, activity_level = metrics["activity"]
        info_density_pct = metrics["info_density"]

        # 12. Select best / concerning posts
        best_posts = _select_best_posts(posts, post_results)
        concerning = _select_concerning_posts(posts, post_results, metrics)

        # 13. Verdict
        verdict = compute_verdict(VerdictInput(
            quality=quality_score.score,
            trust=trust_score.score,
            scam_risk=scam_score.score,
            advertising=advertising_score,
        ))

        channel_analysis = await self._save_analysis(
            channel=channel,
            user_id=user_id,
            username=username,
            info=info,
            channel_result=channel_result,
            metrics=metrics,
            quality=quality_score.score,
            trust=trust_score.score,
            scam=scam_score,
            advertising=advertising_score,
            ad_level=ad_level,
            originality=originality_score,
            activity_posts_day=activity_posts_day,
            activity_level=activity_level,
            verdict=verdict.value,
            best_posts=best_posts,
            concerning=concerning,
            analyzed=analyzed,
            failed=failed,
            total=len(posts),
            duration_ms=int((time.monotonic() - started) * 1000),
        )

        # 14. Build outcome
        outcome = _build_outcome(
            username=username,
            info=info,
            channel_result=channel_result,
            metrics=metrics,
            quality=quality_score,
            trust=trust_score,
            scam=scam_score,
            advertising=advertising_score,
            ad_level=ad_level,
            originality=originality_score,
            activity_posts_day=activity_posts_day,
            activity_level=activity_level,
            verdict=verdict,
            best_posts=best_posts,
            concerning=concerning,
            analyzed=analyzed,
            failed=failed,
            total=len(posts),
        )

        # 15. Cache
        await self._cache.set(username, _outcome_to_dict(outcome, channel_analysis.id))

        await self._channel_repo.update(channel, last_analyzed_at=_now())
        await progress("✅ Готово!")
        return AnalysisResult(outcome=outcome, analysis_id=channel_analysis.id)

    # ------------------------------------------------------------------
    async def _analyze_posts(
        self, channel_id: UUID, posts: list[Post], progress: ProgressCallback
    ) -> tuple[list[tuple[PostAnalysisResult | None, bool]], int, int]:
        """Analyze all posts sequentially, tolerating failures.

        Sequential processing shares one SQLAlchemy session (which is not
        safe for concurrent writers). AI calls are async, so the event
        loop is never blocked. Bounded parallelism can be added later by
        giving each worker its own session.
        """
        limit = self._settings.max_posts_per_analysis
        results: list[tuple[PostAnalysisResult | None, bool]] = []
        analyzed = 0
        failed = 0

        for post in posts[:limit]:
            # skip posts already analyzed (unchanged text) — cost control
            existing = await self._post_repo.get_analysis(post.id)
            if existing is not None and existing.status == "success":
                try:
                    result = PostAnalysisResult.model_validate_json(
                        _reconstruct_json(existing)
                    )
                    results.append((result, True))
                    analyzed += 1
                    continue
                except Exception:  # noqa: BLE001
                    pass
            try:
                result = await self._post_analyzer.analyze(post.text)
                await self._save_post_analysis(post.id, result)
                results.append((result, True))
                analyzed += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "post analysis failed for msg %s: %s", post.telegram_message_id, exc
                )
                results.append((None, False))
                failed += 1

        return results, analyzed, failed

    async def _save_post_analysis(self, post_id: UUID, result: PostAnalysisResult) -> None:
        norm = result.normalized()
        analysis = PostAnalysis(
            post_id=post_id,
            topic=norm["topic"],
            subtopic=norm["subtopic"],
            post_type=norm["post_type"],
            language=norm["language"],
            quality_score=norm["quality_score"],
            originality_score=norm["originality_score"],
            factual_support=norm["factual_support"],
            source_quality=norm["source_quality"],
            advertising_score=norm["advertising_score"],
            manipulation_score=norm["manipulation_score"],
            scam_signals=json.dumps(norm["scam_signals"], ensure_ascii=False),
            summary=norm["summary"],
            why_valuable=norm["why_valuable"],
            status="success",
        )
        await self._post_repo.save_analysis(analysis)

    async def _safe_channel_analyze(
        self, info: ChannelInfo, payloads: list[dict], post_results
    ) -> ChannelAnalysisResult:
        try:
            meta = {
                "username": info.username,
                "title": info.title,
                "description": info.description,
                "subscriber_count": info.subscriber_count,
                "url": info.url,
            }
            return await self._channel_analyzer.analyze(meta, payloads)
        except AIError as exc:
            logger.warning("channel analysis AI failed: %s", exc)
            return ChannelAnalysisResult()

    async def _safe_scam_analyze(self, payloads: list[dict], post_results) -> ScamReport | None:
        try:
            return await self._scam_analyzer.analyze(payloads)
        except AIError as exc:
            logger.warning("scam analysis AI failed: %s", exc)
            return None

    async def _save_analysis(self, **kwargs) -> ChannelAnalysis:
        analysis = ChannelAnalysis(
            channel_id=kwargs["channel"].id,
            user_id=kwargs["user_id"],
            quality_score=kwargs["quality"],
            trust_score=kwargs["trust"],
            scam_risk_score=kwargs["scam"].score,
            advertising_score=kwargs["advertising"],
            originality_score=kwargs["originality"],
            activity_score=kwargs["activity_posts_day"],
            main_topic=kwargs["channel_result"].main_topic,
            topics=json.dumps(kwargs["metrics"]["topics"], ensure_ascii=False),
            audience=json.dumps(kwargs["channel_result"].audience, ensure_ascii=False),
            style=json.dumps(kwargs["channel_result"].style, ensure_ascii=False),
            verdict=kwargs["verdict"],
            summary=kwargs["channel_result"].summary,
            best_posts=json.dumps(kwargs["best_posts"], ensure_ascii=False, default=str),
            concerning_posts=json.dumps(kwargs["concerning"], ensure_ascii=False, default=str),
            posts_analyzed=kwargs["analyzed"],
            posts_failed=kwargs["failed"],
            analysis_version=ANALYSIS_VERSION,
            prompt_version=PROMPT_VERSION,
            ai_cost=0.0,
            duration_ms=kwargs["duration_ms"],
        )
        saved = await self._analysis_repo.create(analysis)

        # snapshot for history
        snapshot = ChannelSnapshot(
            channel_id=kwargs["channel"].id,
            analysis_id=saved.id,
            trust_score=kwargs["trust"],
            quality_score=kwargs["quality"],
            scam_risk_score=kwargs["scam"].score,
            advertising_score=kwargs["advertising"],
            data=json.dumps({
                "verdict": kwargs["verdict"],
                "activity": kwargs["activity_level"],
            }, ensure_ascii=False),
        )
        await self._analysis_repo.add_snapshot(snapshot)
        return saved


# ---------------------------------------------------------------------------
# Aggregation helpers (pure functions)
# ---------------------------------------------------------------------------
def _aggregate_metrics(
    post_results: list[tuple[PostAnalysisResult | None, bool]],
    posts: list[Post],
    posts_data: list[PostData],
) -> dict[str, Any]:
    ok = [res for res, ok in post_results if ok and res]
    total = len(posts)
    ok_n = len(ok)

    quality = [r.quality_score for r in ok]
    orig = [r.originality_score for r in ok]
    factual = [r.factual_support for r in ok if r.factual_support is not None]
    advertising_scores = [r.advertising_score for r in ok]
    manipulation = [r.manipulation_score for r in ok]

    def avg(vals: list[float]) -> float:
        return round(mean(vals), 1) if vals else 0.0

    quality_avg = avg(quality)
    originality_avg = avg(orig)
    factual_avg = avg(factual)
    advertising_avg = avg(advertising_scores)
    manipulation_avg = avg(manipulation)

    source_map = {"strong": 0.9, "medium": 0.6, "weak": 0.3, "none": 0.0}
    source_quality = avg([source_map.get(r.source_quality or "none", 0.0) for r in ok]) if ok else 0.0

    # topics histogram
    topics: dict[str, float] = {}
    for r in ok:
        t = (r.topic or "Разное").strip()
        topics[t] = topics.get(t, 0) + 1
    if topics:
        topics = {t: round(c / ok_n * 100, 1) for t, c in
                  sorted(topics.items(), key=lambda x: -x[1])}
    else:
        topics = {"Разное": 100.0}

    # content mix
    counts = {"news": 0, "advertisement": 0, "repost": 0, "original": 0}
    for r in ok:
        pt = r.post_type
        if pt == "advertisement":
            counts["advertisement"] += 1
        elif pt == "repost":
            counts["repost"] += 1
        elif pt == "news":
            counts["news"] += 1
        else:
            counts["original"] += 1
    denom = max(ok_n, 1)
    content_mix = {
        "advertisement_percent": round(counts["advertisement"] / denom * 100, 1),
        "reposts_percent": round(counts["repost"] / denom * 100, 1),
        "news_percent": round(counts["news"] / denom * 100, 1),
        "original_content_percent": round(counts["original"] / denom * 100, 1),
    }

    # scam signal aggregation
    scam_signals: dict[str, int] = {}
    payment_requests = 0
    for r in ok:
        for sig in r.scam_signals:
            scam_signals[sig] = scam_signals.get(sig, 0) + 1
        if any(s in r.scam_signals for s in ("payment_request", "crypto_transfer")):
            payment_requests += 1

    # activity
    dates = [p.date for p in posts if p.date]
    posts_per_day, activity_level = _activity_metrics(dates, total)

    # consistency = topic concentration of top topic
    consistency = topics[list(topics.keys())[0]] if topics else 50.0
    info_density = avg([1.0 if (r.summary or "").strip() else 0.0 for r in ok]) * 100
    depth_avg = avg([r.factual_support or 5.0 for r in ok])

    failed_ratio = round((total - ok_n) / total * 100, 1) if total else 0.0
    transparency = _transparency(ok, content_mix)

    return {
        "quality_avg": quality_avg,
        "originality_avg": originality_avg,
        "factual_support_avg": factual_avg,
        "source_quality": source_quality,
        "advertising_score_avg": advertising_avg,
        "manipulation_avg": manipulation_avg,
        "topics": topics,
        "content_mix": content_mix,
        "scam_signals": scam_signals,
        "payment_requests": payment_requests,
        "advertising_ratio": counts["advertisement"] / denom,
        "advertising_pct": round(counts["advertisement"] / denom * 100, 1),
        # Originality is derived from per-post AI originality scores (0-100),
        # not from post-type category shares.
        "originality_pct": round(originality_avg * 10.0, 1),
        "consistency": consistency,
        "info_density": info_density,
        "depth_avg": depth_avg,
        "failed_ratio": failed_ratio,
        "transparency": transparency,
        "activity": (posts_per_day, activity_level),
    }


def _activity_metrics(dates, total) -> tuple[float, str]:
    if len(dates) < 2:
        return 0.0, "—"
    newest = max(dates)
    oldest = min(dates)
    span_days = max((newest - oldest).total_seconds() / 86400.0, 1.0)
    per_day = round(total / span_days, 2)
    if per_day == 0:
        level = "Низкая"
    elif per_day < 1:
        level = "Низкая"
    elif per_day < 3:
        level = "Средняя"
    elif per_day < 10:
        level = "Высокая"
    else:
        level = "Очень высокая"
    return per_day, level


def _transparency(post_results, content_mix) -> float:
    if not post_results:
        return 50.0
    disclosed = sum(
        1 for r in post_results
        if (r.source_quality in ("medium", "strong")) or r.advertising_score >= 6
    )
    base = disclosed / len(post_results) * 100
    # penalize undisclosed ads
    ad_pct = content_mix.get("advertisement_percent", 0)
    if ad_pct > 15:
        base = base * 0.7
    return round(max(0.0, min(100.0, base)), 1)


def _select_best_posts(posts, post_results) -> list[BestPostView]:
    scored = []
    for post, (res, ok) in zip(posts, post_results):
        if not ok or res is None:
            continue
        combined = (
            res.quality_score * 0.4
            + res.originality_score * 0.3
            + (res.factual_support or 5.0) * 0.3
        )
        scored.append((combined, post, res))
    scored.sort(key=lambda x: x[0], reverse=True)
    views = []
    for rank, (_, post, res) in enumerate(scored[:5], start=1):
        views.append(BestPostView(
            rank=rank,
            title=first_line(post.text, 120) or f"Пост #{post.telegram_message_id}",
            why_read=res.why_valuable or res.summary or "Информативный пост",
            quality=res.quality_score,
            originality=res.originality_score,
            url=post.post_url or f"https://t.me/c/{post.telegram_message_id}",
        ))
    return views


def _select_concerning_posts(posts, post_results, metrics) -> list[dict]:
    concerning = []
    for post, (res, ok) in zip(posts, post_results):
        if not ok or res is None:
            continue
        reasons = []
        if (res.factual_support or 0) < 4:
            reasons.append("отсутствуют источники / слабая фактическая основа")
        if res.advertising_score >= 7:
            reasons.append("агрессивная реклама")
        if res.manipulation_score >= 7:
            reasons.append("манипулятивные приёмы")
        if res.scam_signals:
            reasons.append("потенциальные scam-признаки: " + ", ".join(res.scam_signals))
        if reasons:
            concerning.append({
                "post_id": post.telegram_message_id,
                "title": first_line(post.text, 100),
                "url": post.post_url,
                "reason": "; ".join(reasons),
                "severity": 2 if res.scam_signals else 1,
            })
    concerning.sort(key=lambda x: -x["severity"])
    return concerning[:5]


def _build_outcome(**kw) -> AnalysisOutcome:
    metrics = kw["metrics"]
    return AnalysisOutcome(
        username=kw["username"],
        title=kw["info"].title,
        subscriber_count=kw["info"].subscriber_count,
        posts_count=kw["total"],
        analyzed=kw["analyzed"],
        failed=kw["failed"],
        quality=kw["quality"].score,
        trust=kw["trust"].score,
        scam_risk=kw["scam"].score,
        advertising=kw["advertising"],
        originality=kw["originality"],
        verdict=kw["verdict"].value,
        main_topic=kw["channel_result"].main_topic or "Разное",
        topics=metrics["topics"],
        audience=kw["channel_result"].audience or ["Широкая аудитория"],
        audience_not_for=kw["channel_result"].audience_not_for,
        style=kw["channel_result"].style or ["neutral"],
        tone=kw["channel_result"].tone or "neutral",
        content_mix=metrics["content_mix"],
        posts_per_day=kw["activity_posts_day"],
        activity_level=kw["activity_level"],
        best_posts=kw["best_posts"],
        concerning=kw["concerning"],
        trust_positive=kw["trust"].positive_factors,
        trust_risk=kw["trust"].risk_factors,
        scam_reasons=kw["scam"].reasons,
        scam_level=kw["scam"].level,
        quality_factors=kw["quality"].factors,
        advertiser_level=kw["ad_level"],
        verdict_explanation=kw["channel_result"].verdict_reasoning or "",
        summary=kw["channel_result"].summary or "",
    )


# ---------------------------------------------------------------------------
# Cache serialization
# ---------------------------------------------------------------------------
def _outcome_to_dict(o: AnalysisOutcome, analysis_id) -> dict:
    return {
        "analysis_id": str(analysis_id),
        "username": o.username,
        "title": o.title,
        "subscriber_count": o.subscriber_count,
        "posts_count": o.posts_count,
        "analyzed": o.analyzed,
        "failed": o.failed,
        "quality": o.quality,
        "trust": o.trust,
        "scam_risk": o.scam_risk,
        "advertising": o.advertising,
        "originality": o.originality,
        "verdict": o.verdict,
        "main_topic": o.main_topic,
        "topics": o.topics,
        "audience": o.audience,
        "audience_not_for": o.audience_not_for,
        "style": o.style,
        "tone": o.tone,
        "content_mix": o.content_mix,
        "posts_per_day": o.posts_per_day,
        "activity_level": o.activity_level,
        "best_posts": [vars(bp) for bp in o.best_posts],
        "concerning": o.concerning,
        "trust_positive": o.trust_positive,
        "trust_risk": o.trust_risk,
        "scam_reasons": o.scam_reasons,
        "scam_level": o.scam_level,
        "quality_factors": o.quality_factors,
        "advertiser_level": o.advertiser_level,
        "verdict_explanation": o.verdict_explanation,
        "summary": o.summary,
    }


def _outcome_from_dict(d: dict) -> AnalysisOutcome:
    return AnalysisOutcome(
        username=d.get("username", ""),
        title=d.get("title"),
        subscriber_count=d.get("subscriber_count"),
        posts_count=d.get("posts_count", 0),
        analyzed=d.get("analyzed", 0),
        failed=d.get("failed", 0),
        quality=d.get("quality", 0),
        trust=d.get("trust", 0),
        scam_risk=d.get("scam_risk", 0),
        advertising=d.get("advertising", 0),
        originality=d.get("originality", 0),
        verdict=d.get("verdict", "NEUTRAL"),
        main_topic=d.get("main_topic", ""),
        topics=d.get("topics", {}),
        audience=d.get("audience", []),
        audience_not_for=d.get("audience_not_for", []),
        style=d.get("style", []),
        tone=d.get("tone", "neutral"),
        content_mix=d.get("content_mix", {}),
        posts_per_day=d.get("posts_per_day", 0),
        activity_level=d.get("activity_level", "—"),
        best_posts=[BestPostView(**bp) for bp in d.get("best_posts", [])],
        concerning=d.get("concerning", []),
        trust_positive=d.get("trust_positive", []),
        trust_risk=d.get("trust_risk", []),
        scam_reasons=d.get("scam_reasons", []),
        scam_level=d.get("scam_level", "low"),
        quality_factors=d.get("quality_factors", []),
        advertiser_level=d.get("advertiser_level", "low"),
        verdict_explanation=d.get("verdict_explanation", ""),
        summary=d.get("summary", ""),
    )


def _reconstruct_json(existing: PostAnalysis) -> str:
    """Reconstruct a JSON payload from a stored PostAnalysis row."""
    return json.dumps({
        "topic": existing.topic,
        "subtopic": existing.subtopic,
        "post_type": existing.post_type,
        "language": existing.language,
        "quality_score": existing.quality_score,
        "originality_score": existing.originality_score,
        "factual_support": existing.factual_support,
        "source_quality": existing.source_quality,
        "advertising_score": existing.advertising_score,
        "manipulation_score": existing.manipulation_score,
        "scam_signals": json.loads(existing.scam_signals or "[]"),
        "summary": existing.summary,
        "why_valuable": existing.why_valuable,
    }, ensure_ascii=False)


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
