"""Menu keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

CB = {
    "main_menu": "menu:main",
    "analyze": "menu:analyze",
    "my_analyses": "menu:my_analyses",
    "favorites": "menu:favorites",
    "monitoring": "menu:monitoring",
    "how": "menu:how",
    "settings": "menu:settings",
}


def main_menu_kb() -> InlineKeyboardMarkup:
    """The main menu grid described in the spec."""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 Проверить канал", callback_data=CB["analyze"])],
        [
            InlineKeyboardButton(text="📊 Мои анализы", callback_data=CB["my_analyses"]),
            InlineKeyboardButton(text="⭐ Избранные каналы", callback_data=CB["favorites"]),
        ],
        [
            InlineKeyboardButton(text="🔔 Мониторинг", callback_data=CB["monitoring"]),
            InlineKeyboardButton(text="❓ Как это работает", callback_data=CB["how"]),
        ],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data=CB["settings"])],
    ])
    return kb


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ В меню", callback_data=CB["main_menu"])],
    ])


def report_kb(channel_username: str) -> InlineKeyboardMarkup:
    """Buttons shown under the compact report."""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Лучшие посты", callback_data="report:best")],
        [InlineKeyboardButton(text="🛡 Почему такой рейтинг?", callback_data="report:trust")],
        [InlineKeyboardButton(text="🚨 Проверка риска", callback_data="report:risk")],
        [InlineKeyboardButton(text="📊 Полный анализ", callback_data="report:full")],
        [
            InlineKeyboardButton(
                text="⭐ Добавить в избранное", callback_data="fav:add"
            ),
            InlineKeyboardButton(text="🔔 Следить", callback_data="mon:start"),
        ],
        [InlineKeyboardButton(text="◀️ В меню", callback_data=CB["main_menu"])],
    ])
    return kb


def cache_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👁 Показать анализ", callback_data="report:show"),
            InlineKeyboardButton(text="🔄 Обновить", callback_data="report:refresh"),
        ],
        [InlineKeyboardButton(text="◀️ В меню", callback_data=CB["main_menu"])],
    ])


def monitoring_intervals_kb(channel_username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Каждый день", callback_data=f"mon:interval:daily:{channel_username}")],
        [InlineKeyboardButton(text="Каждые 3 дня", callback_data=f"mon:interval:every_3_days:{channel_username}")],
        [InlineKeyboardButton(text="Раз в неделю", callback_data=f"mon:interval:weekly:{channel_username}")],
        [InlineKeyboardButton(text="Отключить", callback_data=f"mon:stop:{channel_username}")],
        [InlineKeyboardButton(text="◀️ В меню", callback_data=CB["main_menu"])],
    ])
