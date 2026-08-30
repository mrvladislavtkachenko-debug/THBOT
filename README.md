# THBOT

Telegram-бот: присылаешь ссылку на публичный канал — получаешь сводку:
кто автор, о чём канал и как развивался, сколько контента полезного, а сколько
рекламы/репостов/шума, и какие практики/форматы можно забрать себе.

📄 Документация:
- [docs/bot-spec.md](docs/bot-spec.md) — полная спецификация продукта и видение развития;
- [docs/mvp-plan.md](docs/mvp-plan.md) — что именно реализует первая версия.

## Как устроен MVP

1. **Сбор данных** — парсинг публичной веб-страницы `https://t.me/s/<username>`
   (httpx + BeautifulSoup, пагинация `?before=<id>` — до 100 последних постов).
   Без Telethon и user-аккаунтов — никаких рисков бана.
2. **Анализ** — бесплатные модели через **OpenRouter** (`:free`):
   - классификация постов батчами: категория + польза 0/1/2 + флаги рекламы/репостов;
   - синтез сводки: автор, ниша, развитие, красные флаги, «что забрать себе»,
     лучшие посты, вердикт.
   - модели перебираются по списку при 429/сбоях; кэш отчётов 7 дней.
3. **Инфраструктура** — Python, aiogram 3, SQLite. Никаких внешних сервисов
   кроме Telegram и OpenRouter.

> Лимиты бесплатного OpenRouter: ~50 запросов/день на ключе без пополнений
> (20/мин), после разового пополнения на $10 — 1000/день. Один свежий анализ
> стоит ~4–5 запросов, повторные открытия — из кэша.

## Запуск

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # вписать BOT_TOKEN и OPENROUTER_API_KEY
python -m thbot.bot
```

- `BOT_TOKEN` — у [@BotFather](https://t.me/BotFather);
- `OPENROUTER_API_KEY` — бесплатно на [openrouter.ai/keys](https://openrouter.ai/keys).

Проверка парсера без Telegram и без ключа OpenRouter:

```bash
python -m thbot.parser molyanov_blog --limit 40
```

Оффлайн-тест парсера (синтетический HTML):

```bash
PYTHONPATH=. python tests/test_parser_offline.py
```

## Структура

```
thbot/
  config.py    — настройки из .env
  parser.py    — сбор постов с t.me/s/ (+ CLI)
  analyzer.py  — классификация и синтез через OpenRouter, расчёт метрик
  report.py    — сборка HTML-отчёта для Telegram
  storage.py   — SQLite: кэш, суточные лимиты, фидбек
  bot.py       — aiogram-бот, точка входа
docs/          — спецификация и план MVP
```

## Статус

✅ MVP собран: парсер проверен оффлайн-тестом, метрики и сборка отчёта работают.
Следующий шаг — прогон вживую с реальными токенами и калибровка промптов по фидбеку.
Идеи для v1 — в [docs/mvp-plan.md](docs/mvp-plan.md) (Telethon, история анализов, динамика).
