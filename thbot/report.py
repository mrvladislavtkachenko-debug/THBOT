"""Сборка текста отчёта из метрик (код) и сводки (LLM).

Формат — HTML, поддерживаемый Telegram (<b>, <i>, <a>, <blockquote> ...).
Возвращаем список сообщений: одно длинное не влезает в лимит 4096 символов.
"""
from __future__ import annotations

import html
from typing import Any

from .analyzer import CATEGORIES_RU
from .parser import ChannelData, Post

TELEGRAM_LIMIT = 4000  # запас под разметку


def _esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=False)


def _post_link(post: Post, label: str | None = None) -> str:
    label = label or f"пост #{post.id}"
    return f'<a href="{_esc(post.url)}">{_esc(label)}</a>'


def _usefulness_badge(index: int) -> str:
    if index >= 70:
        return "🟢 высокая"
    if index >= 45:
        return "🟡 средняя"
    return "🔴 низкая"


def _pct(ratio: float, digits: int = 0) -> str:
    return f"{round(ratio * 100, digits)}%"


def build_report(
    channel: ChannelData,
    metrics: dict[str, Any],
    synthesis: dict[str, Any],
) -> list[str]:
    posts_by_id = {p.id: p for p in channel.posts}
    parts: list[str] = []

    # ── Шапка + метрики ──────────────────────────────────────────────────────
    author = synthesis.get("author", {})
    subs = f"{channel.subscribers:,}".replace(",", " ") if channel.subscribers else "н/д"
    head = [
        f"📊 <b>СВОДКА ПО КАНАЛУ «{_esc(channel.title)}»</b>",
        f"🔗 @{_esc(channel.username)} · 👥 {subs} подписчиков",
    ]
    if metrics.get("posts_per_week"):
        head.append(f"📈 ~{metrics['posts_per_week']} постов в неделю · проанализировано постов: {metrics['n_posts']}")
    else:
        head.append(f"📈 проанализировано постов: {metrics['n_posts']}")
    head.append("")

    ui = metrics.get("usefulness_index", 0)
    scores = [
        f"🎯 <b>Индекс полезности: {ui}/100</b> ({_usefulness_badge(ui)})",
        f"📢 Реклама/продажи: {_pct(metrics.get('ad_ratio', 0))} · "
        f"🔁 Репосты: {_pct(1 - metrics.get('originality_ratio', 1))} · "
        f"💬 Вовлечённость (реакции/просмотры): {_pct(metrics.get('engagement_rate', 0), 1)}",
    ]

    # топ категорий — чтобы пользователь видел, из чего состоит лента
    cat_counts = metrics.get("category_counts", {})
    total = sum(cat_counts.values()) or 1
    cat_line = " · ".join(
        f"{CATEGORIES_RU.get(cat, cat)} {round(cnt / total * 100)}%"
        for cat, cnt in list(cat_counts.items())[:4]
    )
    if cat_line:
        scores.append(f"🧩 Лента: {cat_line}")
    head.append("\n".join(scores))
    parts.append("\n".join(head))

    # ── Автор ────────────────────────────────────────────────────────────────
    author_lines = ["👤 <b>АВТОР</b>"]
    author_lines.append(f"<b>{_esc(author.get('name') or 'Имя не указано')}</b>")
    type_ru = {
        "personal_expert": "личный канал эксперта",
        "personal_anon": "личный анонимный канал",
        "team": "канал команды",
        "media": "медиа/издание",
        "unknown": "тип не ясен",
    }.get(author.get("type"), "")
    if type_ru:
        author_lines.append(f"<i>{type_ru}</i>")
    if author.get("background"):
        author_lines.append(_esc(author["background"]))
    if author.get("expertise_evidence"):
        author_lines.append(f"🔎 Подтверждение экспертности: {_esc(author['expertise_evidence'])}")
    parts.append("\n".join(author_lines))

    # ── О чём канал + развитие ───────────────────────────────────────────────
    about_lines = ["📚 <b>О ЧЁМ КАНАЛ</b>"]
    niche = synthesis.get("niche") or []
    if niche:
        about_lines.append("🏷 " + ", ".join(_esc(t) for t in niche))
    about_lines.append(_esc(synthesis.get("channel_about", "")))

    dev = synthesis.get("development", {})
    if dev.get("summary"):
        about_lines.append("")
        about_lines.append("📈 <b>РАЗВИТИЕ</b>")
        trend_ru = {"growing": "📈 растущий", "stable": "➡️ стабильный",
                    "declining": "📉 снижается", "unknown": ""}.get(dev.get("trend"), "")
        if trend_ru:
            about_lines.append(f"<i>Тренд: {trend_ru}</i>")
        about_lines.append(_esc(dev["summary"]))
    parts.append("\n".join(about_lines))

    # ── Красные флаги ────────────────────────────────────────────────────────
    flags = synthesis.get("red_flags") or []
    if flags:
        flag_lines = ["🚩 <b>НА ЧТО ОБРАТИТЬ ВНИМАНИЕ</b>"]
        flag_lines.extend(f"• {_esc(f)}" for f in flags)
        parts.append("\n".join(flag_lines))

    # ── Что забрать себе ─────────────────────────────────────────────────────
    takeaways = synthesis.get("takeaways") or []
    if takeaways:
        t_lines = ["🧰 <b>ЧТО МОЖНО ЗАБРАТЬ СЕБЕ</b>"]
        for i, t in enumerate(takeaways[:6], 1):
            line = f"{i}. <b>{_esc(t.get('title', ''))}</b>"
            if t.get("how_to_use"):
                line += f"\n   {_esc(t['how_to_use'])}"
            pid = t.get("example_post_id")
            if pid and int(pid) in posts_by_id:
                line += f"\n   🔗 {_post_link(posts_by_id[int(pid)], 'пример в канале')}"
            t_lines.append(line)
        parts.append("\n".join(t_lines))

    # ── Лучшие посты ─────────────────────────────────────────────────────────
    best_ids = [pid for pid in (synthesis.get("best_post_ids") or []) if int(pid) in posts_by_id]
    if best_ids:
        b_lines = ["🔥 <b>ЛУЧШИЕ ПОСТЫ</b>"]
        for pid in best_ids[:5]:
            p = posts_by_id[int(pid)]
            title = (p.text or "медиа-пост").strip().split("\n")[0][:80]
            views = f"{p.views:,}".replace(",", " ") if p.views else "?"
            b_lines.append(f"• {_post_link(p, _esc(title))} — 👁 {views}")
        parts.append("\n".join(b_lines))

    # ── Вердикт ──────────────────────────────────────────────────────────────
    if synthesis.get("verdict"):
        parts.append("✅ <b>ВЕРДИКТ</b>\n" + _esc(synthesis["verdict"]))

    # склеиваем части, не превышая лимит Telegram
    messages: list[str] = []
    buf = ""
    for chunk in parts:
        if not chunk:
            continue
        if len(buf) + len(chunk) + 2 > TELEGRAM_LIMIT:
            messages.append(buf)
            buf = chunk
        else:
            buf = f"{buf}\n\n{chunk}" if buf else chunk
    if buf:
        messages.append(buf)
    return messages
