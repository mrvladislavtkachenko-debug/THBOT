"""LLM-анализ канала через OpenRouter (только бесплатные модели).

Пайплайн (экономим запросы — у free-ключа ~50 запросов/день):
1. classify_posts  — посты батчами отправляются модели,
   каждый пост получает категорию и оценку полезности 0/1/2;
2. synthesize      — один запрос сильной модели: метаданные канала,
   агрегаты (считает код) и лучшие посты → структурированная сводка.

Бесплатные модели OpenRouter постоянно ротируются и отключаются, поэтому
список НЕ хардкодим: при старте бот сам запрашивает актуальный список
бесплатных моделей через /api/v1/models, сортирует их по пригодности
для анализа текста и запоминает первую рабочую («sticky»), чтобы не жечь
дневной лимит на переборе. Модели перебираются по очереди при сбоях.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

import httpx
from openai import AsyncOpenAI

from .config import settings
from .parser import ChannelData, Post

log = logging.getLogger("thbot")

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
    useful = list(classified.values())
    useful_weight = sum(max(c.get("usefulness", 0), 0) for c in useful)  # 0/1/2 на пост
    useful_index = round(100 * useful_weight / (2 * n))

    ad_ids = {pid for pid, c in classified.items() if c.get("is_ad")}
    repost_ids = {pid for pid, c in classified.items() if c.get("is_repost")} | {
        p.id for p in posts if p.is_repost
    }

    er_values = [p.reactions_total / p.views for p in posts if p.views and p.views > 0]
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

_openai_client: AsyncOpenAI | None = None


def _client() -> AsyncOpenAI:
    global _openai_client
    if not settings.openrouter_api_key:
        raise RuntimeError(
            "Не задан OPENROUTER_API_KEY. Получите бесплатный ключ на "
            "https://openrouter.ai/keys и впишите его в .env"
        )
    if _openai_client is None:
        # max_retries=0: ретраи контролируем сами (встроенные в SDK бьют пачками
        # и впустую жгут дневной лимит при 429)
        _openai_client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key,
            max_retries=0,
            timeout=120.0,
        )
    return _openai_client


# ---- динамический список бесплатных моделей ----

_models_cache: list[str] | None = None
_models_cache_ts: float = 0.0
_MODELS_TTL = 1800  # обновляем список раз в 30 минут
_sticky_model: str | None = None  # последняя модель, которая реально ответила

# запасной список на случай, если API /models недоступен (сетевой сбой)
_FALLBACK_FREE_MODELS = settings.classifier_models + [
    "openrouter/free",
]

# модели/семейства, не подходящие для анализа текста постов
_BAD_KEYWORDS = (
    "lyria", "safety", "content-safety", "embedding", "tts",
    "music", "audio", "voice", "speech", "image-gen",
)

# предпочтительные семейства (по убыванию «силы» для анализа и синтеза)
_PREFERRED = (
    "nemotron-3-ultra",
    "nemotron-3-super",
    "hermes",
    "gpt-oss-120",
    "qwen3-next",
    "gemma-4-26b",
    "gemma-4-31b",
    "qwen3-coder",
    "gpt-oss-20",
    "nemotron-3-nano",
    "llama-3.3",
    "gemma-3",
    "llama-3.2",
    "openrouter/free",
)


async def discover_free_models(limit: int = 9) -> list[str]:
    """Список живых бесплатных моделей через /api/v1/models.

    Результат кэшируется на 30 минут; первая успешная модель становится
    «sticky» и пробуется первой во всех последующих запросах (экономия лимита).
    """
    global _models_cache, _models_cache_ts, _sticky_model

    now = time.monotonic()
    models = _models_cache
    if models is None or now - _models_cache_ts > _MODELS_TTL:
        models = await _fetch_free_models()
        _models_cache = models
        _models_cache_ts = now

    ordered = list(models)
    if _sticky_model and _sticky_model in ordered:
        ordered.remove(_sticky_model)
        ordered.insert(0, _sticky_model)

    # авто-роутер всегда последним шансом
    if "openrouter/free" not in ordered:
        ordered.append("openrouter/free")
    result = ordered[:limit]
    if "openrouter/free" not in result:
        result.append("openrouter/free")
    return result


async def _fetch_free_models() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=25) as hc:
            resp = await hc.get("https://openrouter.ai/api/v1/models")
            resp.raise_for_status()
            data = resp.json().get("data", [])

        free: list[tuple[str, int]] = []
        for m in data:
            mid = m.get("id", "") or ""
            if not mid:
                continue
            pricing = m.get("pricing", {})
            try:
                if float(pricing.get("prompt", 0)) != 0 or float(pricing.get("completion", 0)) != 0:
                    continue  # платная
            except (TypeError, ValueError):
                continue
            arch = m.get("architecture", {})
            out_mods = arch.get("output_modalities")
            if out_mods and out_mods != ["text"]:
                continue  # аудио/музыка и прочий не-текст
            low = mid.lower()
            if any(k in low for k in _BAD_KEYWORDS):
                continue
            free.append((mid, m.get("context_length", 0) or 0))

        def rank(item: tuple[str, int]) -> tuple[int, int]:
            mid, ctx = item
            pref = next((i for i, p in enumerate(_PREFERRED) if p in mid.lower()), len(_PREFERRED))
            return (pref, -ctx)

        free.sort(key=rank)
        models = [mid for mid, _ in free]
        log.info("OpenRouter: живых бесплатных моделей: %d; топ: %s", len(models), models[:6])
        return models or list(_FALLBACK_FREE_MODELS)
    except Exception as exc:  # noqa: BLE001
        log.warning("Не удалось получить список моделей OpenRouter (%s) — беру запасной список", exc)
        return list(_FALLBACK_FREE_MODELS)


class _EmptyResponse(Exception):
    """Модель ответила пустым content (обычно весь лимит токенов ушёл в reasoning)."""


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
    max_tokens: int = 8192,
) -> dict[str, Any]:
    """Вызывает модели по очереди, пока одна не вернёт валидный JSON."""
    global _sticky_model
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
                # response_format принимают не все провайдеры; на первом повторе
                # пробуем с ним, на втором — без (для openrouter/free не шлём вовсе)
                if attempt == 0 and model != "openrouter/free":
                    kwargs["response_format"] = {"type": "json_object"}

                resp = await client.chat.completions.create(**kwargs)
                choice = resp.choices[0]
                content = choice.message.content or ""
                if not content.strip():
                    finish = getattr(choice, "finish_reason", "?")
                    raise _EmptyResponse(f"пустой content (finish_reason={finish})")
                result = _extract_json(content)
                _sticky_model = model  # запомнили рабочую — следующие запросы сразу на неё
                log.info("OpenRouter: модель %s ответила успешно", model)
                return result
            except _EmptyResponse as exc:
                errors.append(f"{model}: пустой ответ")
                log.info("OpenRouter: %s — пустой ответ, пробую следующую модель", model)
                break  # пустые ответы повторять смысла нет — к следующей модели
            except Exception as exc:  # noqa: BLE001 — разбираем любые сбои API
                status = getattr(exc, "status_code", None)
                errors.append(f"{model} (попытка {attempt + 1}): {type(exc).__name__} {exc}")
                if status == 404:
                    # модель больше не бесплатна/не существует — сразу к следующей
                    if _sticky_model == model:
                        _sticky_model = None
                    log.info("OpenRouter: %s недоступна (404), следующая", model)
                    break
                # 429/5xx/таймаут — подождём и повторим/перейдём дальше
                await asyncio.sleep(6 * (attempt + 1))
    raise RuntimeError(
        "Все бесплатные модели сейчас недоступны (перегружены или отключены):\n- "
        + "\n- ".join(errors)
    )


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
    models = await discover_free_models()

    batches = [posts[i : i + batch_size] for i in range(0, len(posts), batch_size)]
    for bi, batch in enumerate(batches, 1):
        payload = [
            {"id": p.id, "text": (p.text or f"[медиа: {p.media_type or 'пост'}]")[:1500]}
            for p in batch
        ]
        log.info("Классификация батча %d/%d (%d постов)", bi, len(batches), len(batch))
        data = await _chat_json(
            models,
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

    models = await discover_free_models()
    data = await _chat_json(
        models,
        SYNTHESIS_SYSTEM,
        json.dumps(user_payload, ensure_ascii=False),
        temperature=0.4,
        max_tokens=16000,
    )
    data.setdefault("red_flags", [])
    data.setdefault("takeaways", [])
    data.setdefault("best_post_ids", [])
    return data


# --------------------------- диагностика (CLI) -------------------------------

async def _main_check() -> None:
    """python -m thbot.analyzer — показать живые бесплатные модели и проверить их.

    Не использует Telegram и парсинг: только OpenRouter.
    """
    models = await discover_free_models(limit=8)
    print(f"Отобрано {len(models)} бесплатных моделей (по порядку перебора):")
    for i, m in enumerate(models, 1):
        print(f"  {i}. {m}")
    print("\nПроверка реальным запросом (по очереди до первого успеха):")

    client = _client()
    ok = False
    for model in models:
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Ответь одним словом: работает."}],
                max_tokens=50,
            )
            text = (resp.choices[0].message.content or "").strip().replace("\n", " ")
            print(f"  ✅ {model} → {text[:60]!r}")
            ok = True
            break
        except Exception as exc:  # noqa: BLE001
            status = getattr(exc, "status_code", None)
            print(f"  ❌ {model} → {type(exc).__name__} (HTTP {status})")
    if not ok:
        print(
            "\nНи одна модель не ответила. Это бывает при перегрузке бесплатного "
            "пула — подождите 2-5 минут и попробуйте снова. За актуальным списком: "
            "https://openrouter.ai/models?max_price=0"
        )
    else:
        print("\nСвязь с OpenRouter есть — бот сможет анализировать каналы.")


if __name__ == "__main__":
    import sys

    if not settings.openrouter_api_key:
        print("OPENROUTER_API_KEY не задан в .env")
        sys.exit(1)
    asyncio.run(_main_check())
