"""Клавиатуры бота."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from config import config


def sub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=config.channel_url)],
        [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")],
    ])


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎁 Мой подарок"), KeyboardButton(text="👥 Пригласить друзей")],
            [KeyboardButton(text="🏆 Рейтинг"), KeyboardButton(text="ℹ️ Как это работает")],
        ],
        resize_keyboard=True,
    )


def gift_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пригласить друзей", callback_data="go_invite")],
        [InlineKeyboardButton(text="🏆 Рейтинг", callback_data="go_rating")],
    ])


def invite_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 Смотреть рейтинг", callback_data="go_rating")],
    ])


def back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Открыть канал", url=config.channel_url)],
    ])
