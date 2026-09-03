"""Кнопки: поделиться постом, участие в конкурсе, капча."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from content import share_url


def channel_post_kb(channel_url: str, teaser: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться", url=share_url(channel_url, teaser))],
        [InlineKeyboardButton(text="🎲 Участвовать в розыгрыше", url=f"{channel_url}?utm=contest")],
    ])


def plain_share_kb(channel_url: str, teaser: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться", url=share_url(channel_url, teaser))],
    ])


def contest_kb(cid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Участвую!", callback_data=f"join_{cid}")],
    ])


def captcha_kb(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я человек", callback_data=f"captcha_{uid}")],
    ])


def to_channel_kb(channel_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Перейти в канал", url=channel_url)],
    ])
