"""Report generation — formatting structured analysis into user text.

Pure formatting: takes an :class:`AnalysisOutcome` and produces the
compact main report and the detailed sections. No AI is invoked here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.scoring.advertising import level_label
from app.scoring.scam import score_to_level
from app.scoring.verdict import VERDICT_LABELS, VERDICT_ICONS
from app.utils.text import format_percent, truncate

SEPARATOR = "━━━━━━━━━━━━━━━━━━━━"

DISCLAIMER = (
    "⚠️ AI-анализ является информационной оценкой и не гарантирует "
    "достоверность информации. Отсутствие обнаруженных рисков не означает, "
    "что канал безопасен. Перед финансовыми операциями самостоятельно "
    "проверяйте автора, компанию, ссылки и условия."
)


@dataclass
class BestPostView:
    rank: int
    title: str
    why_read: str
    quality: float
    originality: float
    url: str


@dataclass
class AnalysisOutcome:
    username: str
    title: str | None
    subscriber_count: int | None
    posts_count: int
    analyzed: int
    failed: int
    quality: float
    trust: float
    scam_risk: float
    advertising: float
    originality: float
    verdict: str
    main_topic: str
    topics: dict[str, float]
    audience: list[str]
    audience_not_for: list[str]
    style: list[str]
    tone: str
    content_mix: dict[str, float]
    posts_per_day: float
    activity_level: str
    best_posts: list[BestPostView]
    concerning: list[dict]
    trust_positive: list[str] = field(default_factory=list)
    trust_risk: list[str] = field(default_factory=list)
    scam_reasons: list[str] = field(default_factory=list)
    scam_level: str = "low"
    quality_factors: list[str] = field(default_factory=list)
    advertiser_level: str = "low"
    verdict_explanation: str = ""
    summary: str = ""


class ReportService:
    """Builds human-readable report texts from an outcome."""

    # ------------------------------------------------------------------
    def compact(self, o: AnalysisOutcome) -> str:
        """Main compact report shown immediately after analysis."""
        lines: list[str] = []
        lines.append(f"🔎 АНАЛИЗ КАНАЛА")
        lines.append("")
        lines.append(f"@{o.username}")
        topics_line = " • ".join(
            f"{t} — {format_percent(p)}"
            for t, p in list(o.topics.items())[:3]
        ) or "—"
        lines.append(topics_line)
        lines.append(SEPARATOR)
        lines.append("")
        lines.append(f"{VERDICT_ICONS.get(o.verdict, '')} Вердикт")
        lines.append(f"{VERDICT_LABELS.get(o.verdict, o.verdict)}")
        lines.append("")
        lines.append(SEPARATOR)
        lines.append("")
        lines.append(f"🧠 Качество       {o.quality:.0f}/100")
        lines.append(f"🛡 Доверие        {o.trust:.0f}/100")
        lines.append(f"🚨 Риск           {o.scam_risk:.0f}/100")
        lines.append(f"📢 Реклама        {o.advertising:.0f}/100")
        lines.append(f"💎 Оригинальность {o.originality:.0f}/100")
        lines.append("")
        lines.append(SEPARATOR)
        lines.append("")
        lines.append("🎯 Для кого")
        lines.append(" | ".join(o.audience[:4]) or "—")
        lines.append("")
        lines.append(SEPARATOR)
        lines.append("")
        lines.append("📚 Основные темы")
        for t, p in list(o.topics.items())[:3]:
            lines.append(f"{t} — {format_percent(p)}")
        lines.append("")
        lines.append(SEPARATOR)
        lines.append("")
        lines.append("⏱ Активность")
        lines.append(f"{o.posts_per_day:.1f} постов/день · {o.activity_level}")
        lines.append("")
        lines.append(SEPARATOR)
        lines.append("")
        if o.concerning:
            lines.append("⚠️ Что настораживает")
            for item in o.concerning[:3]:
                lines.append(f"• {item.get('reason', '—')}")
            lines.append("")
            lines.append(SEPARATOR)
            lines.append("")
        lines.append(
            "[⭐ Лучшие посты]\n[🛡 Почему такой рейтинг?]\n"
            "[🚨 Проверка риска]\n[📊 Полный анализ]"
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    def best_posts(self, o: AnalysisOutcome) -> str:
        if not o.best_posts:
            return "Лучшие посты не определены.\n\n" + DISCLAIMER
        lines = ["⭐ ЛУЧШИЕ ПОСТЫ", ""]
        for bp in o.best_posts:
            lines.append(f"⭐ #{bp.rank}")
            lines.append(bp.title or "—")
            lines.append("")
            lines.append(f"Почему стоит прочитать: {bp.why_read}")
            lines.append(f"Полезность: {bp.quality:.0f}/10 · Качество: {bp.originality:.0f}/10")
            lines.append(f"Ссылка: {bp.url}")
            lines.append("")
            lines.append(SEPARATOR)
            lines.append("")
        lines.append(DISCLAIMER)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    def trust_explanation(self, o: AnalysisOutcome) -> str:
        lines = [f"🛡 ПОЧЕМУ TRUST = {o.trust:.0f}?", ""]
        if o.trust_positive:
            lines.append("Положительные факторы:")
            lines.append("")
            for f in o.trust_positive:
                lines.append(f"🟢 {f}")
        if o.trust_risk:
            if o.trust_positive:
                lines.append("")
            lines.append("Факторы риска:")
            lines.append("")
            for f in o.trust_risk:
                lines.append(f"🟠 {f}")
        lines.append("")
        lines.append(f"Итог: {o.trust:.0f}/100")
        lines.append("")
        lines.append(DISCLAIMER)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    def risk_report(self, o: AnalysisOutcome) -> str:
        lines = [
            f"🚨 ПРОВЕРКА РИСКА",
            "",
            f"Риск: {o.scam_risk:.0f}/100",
            "",
            f"Уровень: {score_to_level(o.scam_risk).upper()} RISK",
            "",
            SEPARATOR,
            "",
        ]
        if o.scam_reasons:
            lines.append("Обнаруженные признаки:")
            lines.append("")
            for r in o.scam_reasons:
                lines.append(f"{r}")
        else:
            lines.append("Явных признаков повышенного риска не обнаружено.")
        lines.append("")
        lines.append(SEPARATOR)
        lines.append("")
        lines.append(DISCLAIMER)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    def full(self, o: AnalysisOutcome) -> str:
        lines: list[str] = []
        lines.append(f"📊 ПОЛНЫЙ АНАЛИЗ")
        lines.append("")
        lines.append(f"@{o.username}")
        lines.append(SEPARATOR)
        lines.append("")

        # 1. Channel info
        lines.append("ℹ️ О КАНАЛЕ")
        if o.title:
            lines.append(f"Название: {o.title}")
        lines.append(f"Подписчики: {o.subscriber_count if o.subscriber_count else '—'}")
        lines.append(f"Анализ основан на {o.analyzed} из {o.posts_count} доступных публикаций.")
        if o.failed:
            lines.append(f"(не удалось проанализировать {o.failed})")
        lines.append("")
        lines.append(SEPARATOR)

        # 2. Scores
        lines.append("")
        lines.append("📈 ПОКАЗАТЕЛИ")
        lines.append(f"🧠 Качество        {o.quality:.0f}/100")
        lines.append(f"🛡 Доверие         {o.trust:.0f}/100")
        lines.append(f"🚨 Риск            {o.scam_risk:.0f}/100")
        lines.append(f"📢 Реклама         {o.advertising:.0f}/100")
        lines.append(f"💎 Оригинальность  {o.originality:.0f}/100")
        lines.append("")
        lines.append(SEPARATOR)

        # 3. Verdict
        lines.append("")
        lines.append(f"{VERDICT_ICONS.get(o.verdict, '')} ВЕРДИКТ")
        lines.append(VERDICT_LABELS.get(o.verdict, o.verdict))
        if o.verdict_explanation:
            lines.append(o.verdict_explanation)
        lines.append("")
        lines.append(SEPARATOR)

        # 4. Topics
        lines.append("")
        lines.append("📚 ТЕМАТИКА")
        for t, p in sorted(o.topics.items(), key=lambda x: -x[1]):
            lines.append(f"{t} — {format_percent(p)}")
        lines.append("")
        lines.append(SEPARATOR)

        # 5. Audience
        lines.append("")
        lines.append("🎯 АУДИТОРИЯ")
        lines.append("Подходит: " + (", ".join(o.audience) or "—"))
        if o.audience_not_for:
            lines.append("Не подходит: " + ", ".join(o.audience_not_for))
        lines.append("")
        lines.append(SEPARATOR)

        # 6. Style
        lines.append("")
        lines.append("🎨 СТИЛЬ АВТОРА")
        lines.append("Стиль: " + (", ".join(o.style) or "—"))
        lines.append(f"Тональность: {o.tone or '—'}")
        if o.content_mix:
            lines.append("")
            lines.append("Контент:")
            for k, v in o.content_mix.items():
                lines.append(f"• {k}: {format_percent(v)}")
        lines.append("")
        lines.append(SEPARATOR)

        # 7. Activity
        lines.append("")
        lines.append("⏱ АКТИВНОСТЬ")
        lines.append(f"{o.posts_per_day:.1f} постов/день · {o.activity_level}")
        lines.append("")
        lines.append(SEPARATOR)

        # 8. Best posts
        lines.append("")
        lines.append("⭐ ЛУЧШИЕ ПОСТЫ")
        if o.best_posts:
            for bp in o.best_posts:
                lines.append(f"#{bp.rank} — {bp.title or '—'}")
                lines.append(f"   Ссылка: {bp.url}")
        else:
            lines.append("—")
        lines.append("")
        lines.append(SEPARATOR)

        # 9. Concerning
        lines.append("")
        lines.append("⚠️ СОМНИТЕЛЬНЫЕ ПУБЛИКАЦИИ")
        if o.concerning:
            for item in o.concerning[:5]:
                lines.append(f"• {item.get('reason', '—')}")
        else:
            lines.append("—")
        lines.append("")
        lines.append(SEPARATOR)

        # 10. Risk
        lines.append("")
        lines.append("🚨 RISK REPORT")
        lines.append(f"Риск: {o.scam_risk:.0f}/100 · {score_to_level(o.scam_risk).upper()}")
        for r in o.scam_reasons:
            lines.append(f"• {r}")
        lines.append("")
        lines.append(DISCLAIMER)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    def ad_level_line(self, o: AnalysisOutcome) -> str:
        ratio = o.content_mix.get("advertisement_percent", 0.0)
        return (
            f"Реклама: {format_percent(ratio)} публикаций\n\n"
            f"Уровень: {level_label(o.advertiser_level)}"
        )
