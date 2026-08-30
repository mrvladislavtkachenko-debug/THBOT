"""LLM-анализ канала через OpenRouter (только бесплатные модели).

Пайплайн (экономим запросы — у free-ключа ~50 запросов/день):
1. classify_posts  — посты батчами отправляются дешёвой/свободной модели,
   каждый пост получает категорию и оценку полезности 0/1/2;
2. synthesize      — один запрос сильной модели: метаданные канала,
   агрегаты (считает код) и лучшие посты → структурированная сводка.

Модели перебираются по порядку: если одна отдаёт 429/ошибку — идём к следующей.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from openai import AsyncOpenAI

from .config import settings
from .parser import ChannelData, Post

# ----------------------------- метрики (считает код, не LLM) ----------------

CATEGORIES_RU = {
    "guide": "гайд/инструкция",
    "case": "кейс/разбор",
    "insight": "инсайт/мнение",
    "news": "новость",
    "ad": "реклама",
    "repost": "репост",
    "meme": "мем/развлечение",
    "quote": "цитата/мотивация",
    "announcement": "анонс/организационное",
    "offtop": "оффтоп/флуд",
    "poll": "опрос",
    "other": "другое",
}


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def compute_metrics(posts: list[Post], classified: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Чистая арифметика по постам и вердиктам классификатора."""
    n = len(posts) or 1
    useful = [c for c in classified.values()]
    useful_weight = sum(
        max(c.get("usefulness", 0), 0) for c in useful
    )  # 0/1/2 на пост
    useful_index = round(100 * useful_weight / (2 * n))

    ad_ids = {pid for pid, c in classified.items() if c.get("is_ad")}
    repost_ids = {
        pid for pid, c in classified.items() if c.get("is_repost")
    } | {p.id for p in posts if p.is_repost}

    er_values = [
        p.reactions_total / p.views
        for p in posts
        if p.views and p.views > 0
    ]
    engagement = median(er_values)

    # частота: постов в неделю по диапазону дат
    posts_per_week: float | None = None
    dated = [p for p in posts if p.date_iso]
    if len(dated) >= 4:
        from datetime import datetime

        def _dt(iso: str) -> datetime:
            return datetime.fromisoformat(iso.replace("Z", "+00:00"))

        span_days = max((_dt(dated[-1].date_iso) - _dt(dated[0].date_iso)).days, 1)
        posts_per_week = round(len(dated) / span_days * 7, 1)

    return {
        "n_posts": len(posts),
        "usefulness_index": min(max(useful_index, 0), 100),
        "ad_ratio": round(len(ad_ids) / n, 2),
        "repost_ratio": round(len(repost_ids & {p.id for p in posts}) / n, 2),
        "originality_ratio": round(1 - len(repost_ids & {p.id for p in posts}) / n, 2),
        "engagement_rate": round(engagement, 4),
        "posts_per_week": posts_per_week,
        "category_counts": _category_counts(classified),
    }


def _category_counts(classified: dict[int, dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for c in classified.values():
        cat = c.get("category", "other")
        counts[cat] = counts.get(cat, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def rank_posts(
    posts: list[Post], classified: dict[int, dict[str, Any]], top_n: int = 15
) -> list[Post]:
    """Кандидаты на «лучшие посты»: полезные, отсортированы по вовлечённости."""

    def score(p: Post) -> float:
        c = classified.get(p.id, {})
        usefulness = c.get("usefulness", 0)
        if usefulness < 2 or c.get("is_ad"):
            return -1
        reactions = p.reactions_total
        forwards_proxy = reactions  # точные форварды t.me/s не показывает
        views = p.views or 1
        return reactions + forwards_proxy * 2 + views * 0.01

    ranked = sorted(posts, key=score, reverse=True)
    return [p for p in ranked if score(p) >= 0][:top_n]


# --------------------------------- LLM-слой --------------------------------

def _client() -> AsyncOpenAI:
    if not settings.openrouter_api_key:
        raise RuntimeError(
            "Не задан OPENROUTER_API_KEY. Получите бесплатный ключ на "
            "https://openrouter.ai/keys и впишите его в .env"
        )
    return AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
    )


def _extract_json(text: str) -> dict[str, Any]:
    """Достаёт JSON из ответа модели (срезает ```json ... ``` и прочий текст)."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


async def _chat_json(
    models: list[str],
    system: str,
    user: str,
    *,
    temperature: float = 0.3,
    retries: int = 2,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Вызывает модели по очереди, пока одна не вернёт валидный JSON."""
    client = _client()
    errors: list[str] = []
    for model in models:
        for attempt in range(retries):
            try:
                kwargs: dict[str, Any] = dict(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                # не все бесплатные модели принимают response_format —
                # на первом повторе пробуем с ним, на следующих без него
                if attempt == 0:
                    kwargs["response_format"] = {"type": "json_object"}
                resp = await client.chat.completions.create(**kwargs)
                content = resp.choices[0].message.content or ""
                return _extract_json(content)
            except Exception as exc:  # noqa: BLE001 — разбираем любые сбои API
                status = getattr(exc, "status_code", None)
                errors.append(f"{model} (попытка {attempt + 1}): {type(exc).__name__} {exc}")
                # 404 = модель больше не бесплатна/не существует — сразу к следующей,
                # повтор бессмыслен и жжёт дневной лимит запросов
                if status == 404:
                    break
                # 429/5xx/таймаут/пустой ответ — ждём дольше и пробуем снова
                await asyncio.sleep(6 * (attempt + 1))
    raise RuntimeError("Все бесплатные модели сейчас недоступны:\n- " + "\n- ".join(errors))


CLASSIFIER_SYSTEM = """Ты — аналитик Telegram-каналов. Тебе дают посты канала (JSON с полями id и text).
Для КАЖДОГО поста верни вердикт строго в JSON.

category — одна из:
- guide        — гайд, инструкция, туториал, чек-лист, шаблон, как что-то сделать;
- case         — разбор реального кейса, опыта, ошибки, результата;
- insight      — оригинальное мнение, инсайт, аналитика, наблюдение автора;
- news         — новость ниши/общая;
- ad           — реклама, нативная интеграция, взаимопиар, продажа своего продукта;
- repost       — репост/цитирование чужого поста без существенного комментария;
- meme         — мем, шутка, развлечение;
- quote        — цитата/мотивация без своей сути;
- announcement — анонс, организационное сообщение, опрос-аукцион;
- offtop       — оффтоп, флуд, бессодержательное;
- poll         — опрос;
- other        — другое.

usefulness — оценка пользы для читателя:
- 2 — ПОЛЕЗНОЕ: прикладная информация, которую можно применить (гайды, кейсы, инсайты, инструменты с пояснением);
- 1 — НЕЙТРАЛЬНОЕ: анонсы, новости ниши, личное/организационное;
- 0 — ШУМ: реклама, репосты без добавленной ценности, мемы, пустые цитаты, флуд.

is_ad — true, если пост рекламный/продающий (включая продажу продуктов автора).
is_repost — true, если это репост чужого контента.
tags — до 3 коротких тегов темы на русском (например ["нейросети", "маркетинг"]).

Опирайся ТОЛЬКО на текст поста. Посты на медиа без текста классифицируй как other/0.
Верни ровно: {"posts": [{"id": <id поста>, "category": "...", "usefulness": 0|1|2, "is_ad": bool, "is_repost": bool, "tags": ["..."]}]}
Никаких пояснений вне JSON."""


async def classify_posts(
    posts: list[Post], batch_size: int | None = None
) -> dict[int, dict[str, Any]]:
    """Батчами прогоняет посты через классификатор → {post_id: вердикт}."""
    batch_size = batch_size or settings.classify_batch_size
    result: dict[int, dict[str, Any]] = {}

    batches = [posts[i : i + batch_size] for i in range(0, len(posts), batch_size)]
    for batch in batches:
        payload = [
            {"id": p.id, "text": (p.text or f"[медиа: {p.media_type or 'пост'}]")[:1500]}
            for p in batch
        ]
        data = await _chat_json(
            settings.classifier_models,
            CLASSIFIER_SYSTEM,
            "Посты для классификации:\n"
            + json.dumps(payload, ensure_ascii=False)
            + "\n/no_think",  # qwen3-модели: отвечать сразу, без «размышлений»
            temperature=0.2,
            max_tokens=8192,
        )
        for item in data.get("posts", []):
            try:
                pid = int(item["id"])
            except (KeyError, TypeError, ValueError):
                continue
            result[pid] = {
                "category": str(item.get("category", "other")),
                "usefulness": int(item.get("usefulness", 0)),
                "is_ad": bool(item.get("is_ad", False)),
                "is_repost": bool(item.get("is_repost", False)),
                "tags": [str(t) for t in item.get("tags", [])][:3],
            }
    return result


SYNTHESIS_SYSTEM = """Ты — опытный редактор-аналитик, который готовит для читателя сжатую, честную сводку
о Telegram-канале. Тебе дают: описание канала, агрегированные метрики (посчитаны кодом —
не выдумывай свои цифры) и подборку самых полезных постов с их текстами.

Напиши разбор строго в JSON со следующими полями:
{
  "niche": ["ниша/тема на русском", "..."],
  "author": {
    "name": "имя/псевдоним автора как в канале",
    "type": "personal_expert | personal_anon | team | media | unknown",
    "background": "кто автор по роду деятельности, бэкграунд — 1-3 предложения; если данных нет — 'неизвестен'",
    "expertise_evidence": "чем подтверждается экспертность: личные кейсы, детали, инсайды; или признаки пересказа/копипасты — 1-3 предложения"
  },
  "channel_about": "о чём канал, стиль и формат подачи — 2-4 предложения",
  "development": {
    "summary": "как канал развивался/менялся, что видно по контенту и метрикам — 2-4 предложения",
    "trend": "growing | stable | declining | unknown"
  },
  "red_flags": ["кратко: реклама, накрутка, копипаста, падение активности и т.п.; пустой список если всё чисто"],
  "takeaways": [
    {"title": "что конкретно можно забрать/применить (формат поста, практика, инструмент, подход)",
     "how_to_use": "как это применить — 1-2 предложения",
     "example_post_id": <id поста из подборки, который это иллюстрирует, или null>}
  ],
  "best_post_ids": [<3-5 id постов из подборки, самых ценных для читателя>],
  "verdict": "итоговый вердикт 2-4 предложения: стоит ли подписываться/читать, кому и как — выборочно или полностью"
}

Правила:
- Пиши на русском языке, живо и по делу, без воды и канцелярита.
- Опирайся ТОЛЬКО на предоставленные данные. Цифры бери из метрик, своих не придумывай.
- takeaways — это практичные вещи, которые читатель может применить у себя (форматы контента,
  рубрики, инструменты, подходы), а не пересказ тем.
- example_post_id и best_post_ids — только из id, которые есть в подборке постов.
- Верни ровно JSON, без текста вокруг."""


async def synthesize(
    channel: ChannelData,
    metrics: dict[str, Any],
    classified: dict[int, dict[str, Any]],
    top_posts: list[Post],
) -> dict[str, Any]:
    """Финальный синтез: сводка об авторе, развитии, пользе и вердикт."""
    top_ids = {p.id for p in top_posts}
    posts_payload = [
        {
            "id": p.id,
            "date": p.date_iso[:10] if p.date_iso else None,
            "views": p.views,
            "reactions": p.reactions_total,
            "category": classified.get(p.id, {}).get("category"),
            "text": (p.text or f"[медиа: {p.media_type}]")[:1800],
        }
        for p in top_posts
    ]

    user_payload = {
        "channel": {
            "title": channel.title,
            "username": channel.username,
            "subscribers": channel.subscribers,
            "description": channel.description[:1000],
        },
        "metrics": metrics,
        "useful_posts": posts_payload,
        "all_useful_post_ids": sorted(top_ids),
    }

    data = await _chat_json(
        settings.synthesis_models,
        SYNTHESIS_SYSTEM,
        json.dumps(user_payload, ensure_ascii=False),
        temperature=0.4,
        max_tokens=32768,
    )
    data.setdefault("red_flags", [])
    data.setdefault("takeaways", [])
    data.setdefault("best_post_ids", [])
    return data
