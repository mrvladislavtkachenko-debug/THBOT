"""THBOT — Telegram-бот для анализа каналов (MVP).

Модули:
- config: настройки из окружения
- parser: сбор постов с публичной веб-версии t.me/s/<username>
- analyzer: классификация и синтез через бесплатные модели OpenRouter
- report: сборка текста отчёта
- storage: SQLite-кэш, лимиты, фидбек
- bot: aiogram-бот (точка входа)
"""
