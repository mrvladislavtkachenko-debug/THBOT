"""Fake Telegram channel and post data used by tests.

These fixture channels model typical cases: a content channel, a channel
with heavy advertising, and one with scam-style signals.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.schemas import ChannelInfo, PostData


def sample_channel_info(username: str = "example") -> ChannelInfo:
    return ChannelInfo(
        username=username,
        title="Example Channel",
        description="Тестовый канал",
        url=f"https://t.me/{username}",
        subscriber_count=12000,
        telegram_channel_id=123456789,
        is_group=False,
        is_bot=False,
        is_private=False,
        available_posts=200,
    )


def sample_posts(
    count: int = 10, *, ad_keywords: bool = False, scam_style: bool = False
) -> list[PostData]:
    """Generate a list of fake posts."""
    now = datetime.now(timezone.utc)
    posts: list[PostData] = []
    base_text = (
        "Разбираем, как искусственный интеллект меняет рынок инвестиций. "
        "Нейросети теперь прогнозируют тренды лучше аналитиков. "
        "Подробный анализ в посте."
    )
    ad_text = (
        "🔥 Только сегодня скидка 50%! Оформи подписку и получи "
        "доступ к закрытым сигналам. Успей, предложение ограничено."
    )
    scam_text = (
        "Гарантируем доходность 100% без риска! Переведи средства на "
        "кошелёк и начни зарабатывать уже сегодня. Срочно, только для "
        "первых 10 человек!"
    )
    for i in range(count):
        if scam_style and i % 2 == 0:
            text = scam_text
        elif ad_keywords and i % 2 == 0:
            text = ad_text
        else:
            text = base_text
        posts.append(PostData(
            telegram_message_id=1000 + i,
            text=text,
            date=now - timedelta(hours=i),
            views=500 + i * 10,
            reactions=10 + i,
            comments=1,
            forwards=2,
            post_url=f"https://t.me/example/{1000 + i}",
            media_type="text",
        ))
    return posts
