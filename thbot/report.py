"""Сборка текста отчёта в новом формате: «карточка» + «разбор».

- Сообщение 1 — карточка: тир, слоган, визуальные шкалы, как читать, кому.
- Сообщение 2 — разбор: автор как человек, голос, что происходило, честный
  вывод, что забрать себе, лучшие посты.

Формат — HTML, поддерживаемый Telegram. Возвращаем список сообщений,
чтобы не упереться в лимит 4096 символов.
"""
from __future__ import annotations

import html
from typing import Any

from .parser import ChannelData, Post

TELEGRAM_LIMIT = 4000
BAR_LEN = 14


def _esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=False)


# --------------------------------- тир и шкалы ------------------------------

def _tier(index: int) -> tuple[str, str]:
    """Тир назначает код по индексу (единообразие). → (эмодзи+название, пояснение)."""
    if index >= 85:
        return "💎 МАСТ-ХЭВ", "подписываться не глядя, читать целиком"
    if index >= 70:
        return "🟢 КРЕПКИЙ ЭКСПЕРТ", "подписаться, читать выборочно"
    if index >= 50:
        return "🟡 НА ЛЮБИТЕЛЯ", "польза есть, но ленту придётся фильтровать"
    if index >= 30:
        return "🟠 ФОНОВЫЙ ШУМ", "можно не подписываться, теряется мало"
    return "🔴 МИМО", "реклама/копипаста/пустышка — время тратить не стоит"


def _bar(ratio: float) -> str:
    filled = round(ratio * BAR_LEN)
    filled = max(0, min(BAR_LEN, filled))
    return "█" * filled + "░" * (BAR_LEN - filled)


def _engagement_label(rate: float) -> str:
    if rate >= 0.03:
        return "очень высокая (аудитория живая)"
    if rate >= 0.015:
        return "высокая"
    if rate >= 0.007:
        return "средняя"
    if rate > 0:
        return "низкая (реакций мало)"
    return "не измерить"


_READING_RU = {
    "целиком": "📖 Читать целиком",
    "выборочно": "🎯 Читать выборочно",
    "только избранное": "⭐ Только избранные посты",
    "не читать": "🙈 Лучше не читать",
}


def _post_link(post: Post, label: str | None = None) -> str:
    label = label or f"пост #{post.id}"
    return f'<a href="{_esc(post.url)}">{_esc(label)}</a>'


# --------------------------------- сборка -----------------------------------

def build_report(
    channel: ChannelData,
    metrics: dict[str, Any],
    synthesis: dict[str, Any],
) -> list[str]:
    by_id = {p.id: p for p in channel.posts}
    messages: list[str] = []

    # ════════════════ Сообщение 1: КАРТОЧКА ════════════════
    index = int(metrics.get("usefulness_index", 0))
    tier, tier_hint = _tier(index)
    subs = f"{channel.subscribers:,}".replace(",", " ") if channel.subscribers else "н/д"

    card = [f"📡 <b>{_esc(channel.title.upper())} — разбор канала</b>"]
    card.append(f"🔗 @{_esc(channel.username)} · 👥 {subs} подписчиков")
    if metrics.get("posts_per_week"):
        card.append(
            f"🗓 ~{metrics['posts_per_week']} постов/нед · разобрано {metrics['n_posts']} постов"
        )
    else:
        card.append(f"🗓 разобрано {metrics['n_posts']} постов")
    card.append("")
    card.append(f"<b>{tier}</b> · {index}/100")
    card.append(f"<i>{tier_hint}</i>")
    card.append("")

    tagline = synthesis.get("tagline")
    if tagline:
        card.append(f"«{_esc(tagline)}»")
        card.append("")

    # визуальные шкалы
    useful = metrics.get("useful_ratio", 0)
    ad = metrics.get("ad_ratio", 0)
    filler = metrics.get("filler_ratio", 0)
    card.append(
        f"👍 Полезное        {_bar(useful)} {round(useful * 100)}%"
    )
    card.append(
        f"📢 Реклама/запуски {_bar(ad)} {round(ad * 100)}%"
    )
    card.append(
        f"🔁 Репосты/шум    {_bar(filler)} {round(filler * 100)}%"
    )
    card.append(
        f"💬 Вовлечённость: {_engagement_label(metrics.get('engagement_rate', 0))}"
    )
    card.append("")

    reading = _READING_RU.get(synthesis.get("reading_mode"), "🎯 Читать выборочно")
    card.append(f"<b>👉 Как читать:</b> {reading}")
    if synthesis.get("for_you"):
        card.append(f"✅ <b>Вам сюда</b>, если {_lcfirst(_esc(synthesis['for_you']))}")
    if synthesis.get("not_for_you"):
        card.append(f"🚫 <b>Мимо</b>, если {_lcfirst(_esc(synthesis['not_for_you']))}")
    card.append("")
    card.append("<i>Подробный разбор — в следующем сообщении 👇</i>")

    # ════════════════ Сообщение 2+: РАЗБОР ════════════════
    parts: list[str] = []

    # автор
    author = synthesis.get("author", {})
    if author:
        a = ["👤 <b>АВТОР КАК ЧЕЛОВЕК</b>"]
        name = author.get("name")
        if name:
            a.append(f"<b>{_esc(name)}</b>")
        if author.get("sketch"):
            a.append(_esc(author["sketch"]))
        if author.get("voice_quote"):
            a.append(f"🗣 <i>«{_esc(author['voice_quote'])}»</i>")
        if author.get("signature"):
            a.append(f"✨ <b>Фирменная фишка:</b> {_esc(author['signature'])}")
        if author.get("expertise_evidence"):
            a.append(f"🔎 Экспертность: {_esc(author['expertise_evidence'])}")
        parts.append("\n".join(a))

    # о чём
    about = ["📚 <b>О ЧЁМ КАНАЛ</b>"]
    niche = synthesis.get("niche") or []
    if niche:
        about.append("🏷 " + ", ".join(_esc(t) for t in niche))
    if synthesis.get("channel_about"):
        about.append(_esc(synthesis["channel_about"]))
    parts.append("\n".join(about))

    # история
    if synthesis.get("arc"):
        parts.append("📈 <b>ЧТО ПРОИСХОДИЛО</b> (за последние недели)\n" + _esc(synthesis["arc"]))

    # честный вывод
    if synthesis.get("hot_take"):
        parts.append("🌶 <b>ЧЕСТНО, БЕЗ ПОЛИТЕСА</b>\n" + _esc(synthesis["hot_take"]))

    # что забрать
    swipe = synthesis.get("swipe_file") or []
    if swipe:
        s = ["🧰 <b>ЧТО МОЖНО ЗАБРАТЬ СЕБЕ</b> (по-хорошему — подсмотреть)"]
        for i, item in enumerate(swipe[:5], 1):
            line = f"{i}. <b>{_esc(item.get('format', ''))}</b>"
            if item.get("why_it_works"):
                line += f"\n   — {_esc(item['why_it_works'])}"
            pid = item.get("example_post_id")
            if pid and int(pid) in by_id:
                line += f"\n   🔗 {_post_link(by_id[int(pid)], 'пример в канале')}"
            s.append(line)
        parts.append("\n".join(s))

    # чего не делать
    if synthesis.get("anti_pattern"):
        parts.append(f"🙅 <b>А вот так лучше не надо:</b> {_esc(synthesis['anti_pattern'])}")

    # посты-роли
    expl = synthesis.get("explainer_posts") or {}
    expl_rows = [
        ("📜 Манифест канала (о чём он вообще)", expl.get("manifesto")),
        ("🛠 Самый практичный гайд", expl.get("best_guide")),
        ("🔥 Самый живой пост", expl.get("most_viral")),
    ]
    seen: set[int] = set()
    expl_lines = ["🔎 <b>3 ПОСТА, КОТОРЫЕ ОБЪЯСНЯЮТ КАНАЛ</b>"]
    for label, pid in expl_rows:
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            continue
        if pid in by_id and pid not in seen:
            seen.add(pid)
            p = by_id[pid]
            title = (p.text or "медиа-пост").strip().split("\n")[0][:70]
            expl_lines.append(f"• {_esc(label)} → {_post_link(p, _esc(title))}")
    if len(seen) > 0:
        parts.append("\n".join(expl_lines))

    # вердикт
    if synthesis.get("verdict"):
        parts.append("✅ <b>ВЕРДИКТ</b>\n" + _esc(synthesis["verdict"]))

    # карточка — всегда отдельным сообщением, разбор — следующими
    breakdown = _split_long(parts)
    return ["\n".join(card)] + breakdown


def _split_long(messages: list[str]) -> list[str]:
    out: list[str] = []
    buf = ""
    for chunk in messages:
        if len(buf) + len(chunk) + 2 > TELEGRAM_LIMIT:
            if buf:
                out.append(buf)
            buf = chunk
        else:
            buf = f"{buf}\n\n{chunk}" if buf else chunk
    if buf:
        out.append(buf)
    return out


def _lcfirst(text: str) -> str:
    """Строчная первая буква (для стыковки «если …»)."""
    if not text:
        return text
    return text[0].lower() + text[1:]
