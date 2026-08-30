# TG Channel Analyzer

> **«Я кинул ссылку на канал и через минуту понял, стоит ли мне вообще его читать»**

Telegram-бот, который принимает ссылку на **публичный** Telegram-канал,
анализирует его содержимое с помощью AI и выдаёт структурированный отчёт:
о чём канал, для кого он, насколько качественный контент, сколько рекламы,
есть ли признаки риска и стоит ли на него подписываться.

---

## 1. Что делает проект

Пользователь отправляет боту ссылку на канал (например `https://t.me/example`).
Бот:

1. проверяет ссылку и находит канал;
2. собирает метаданные канала и последние N постов;
3. анализирует каждый пост через AI (отдельным запросом);
4. агрегирует результаты и вычисляет метрики:
   - 🧠 **Quality** — качество контента;
   - 🛡 **Trust** — доверие;
   - 🚨 **Scam Risk** — риск мошенничества;
   - 📢 **Advertising** — рекламная нагрузка;
   - 💎 **Originality** — оригинальность;
5. определяет тематику, аудиторию, стиль, активность;
6. находит лучшие и сомнительные посты;
7. формирует итоговый **вердикт** и подробный отчёт.

---

## 2. Требования

- **Python 3.12+** (рекомендуется 3.12; работает на 3.11)
- **Git**
- **Telegram Bot Token** (от @BotFather)
- **Telegram API ID / Hash** (MTProto, от https://my.telegram.org)
- **AI API Key** (OpenAI; или используйте mock-режим для локальной разработки)
- **PostgreSQL** (или SQLite для локальной разработки/тестов)
- **Redis** (опционально — для кэша и очереди; без него используется in-memory)

---

## 3. Установка

```bash
# 1. Склонировать репозиторий
git clone <repo-url> tg-channel-analyzer
cd tg-channel-analyzer

# 2. Создать виртуальное окружение (Windows: python -m venv .venv)
python3 -m venv .venv

# 3. Активировать
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

# 4. Установить зависимости
pip install -r requirements.txt
```

---

## 4. Получение Telegram Bot Token

1. Откройте [@BotFather](https://t.me/BotFather) в Telegram.
2. Отправьте `/newbot`.
3. Укажите имя и username бота.
4. Скопируйте **token** (вида `123456789:AAF...`).
5. Вставьте его в `.env` как `BOT_TOKEN=`.

---

## 5. Получение Telegram API ID / HASH

Telegram API / MTProto используется для чтения данных публичных каналов
(Telethon). Без него бот не сможет получить посты.

1. Зайдите на https://my.telegram.org и войдите в аккаунт.
2. Откройте **API development tools**.
3. Создайте приложение — получите **api_id** и **api_hash**.
4. Вставьте их в `.env`.

> ⚠️ При первом запуске Telethon запросит подтверждение входа
> (номер телефона + код). Это одноразовая процедура для локального
> файла сессии `tg_session.session`.

---

## 6. Получение AI API Key

1. Зарегистрируйтесь на https://platform.openai.com
2. Создайте API key в **API keys**.
3. Вставьте его в `.env` как `OPENAI_API_KEY=`.

> Для локальной разработки без затрат можно использовать `AI_PROVIDER=mock`
> — тогда AI-запросы не выполняются, а результаты генерируются детерминированно.

---

## 7. Настройка `.env`

```bash
cp .env.example .env
# заполните ключи в .env
```

`.env` **не** попадает в Git (см. `.gitignore`).

Основные переменные — см. `.env.example`. Кратко:

| Переменная | Назначение | По умолчанию |
|---|---|---|
| `BOT_TOKEN` | Telegram Bot token | — |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | MTProto доступ | — |
| `AI_PROVIDER` | `openai` или `mock` | `openai` |
| `OPENAI_API_KEY` | Ключ OpenAI | — |
| `OPENAI_MODEL` | Модель | `gpt-4o-mini` |
| `DATABASE_URL` | PostgreSQL (asyncpg) | `postgresql+asyncpg://...` |
| `REDIS_URL` | Redis | `redis://localhost:6379/0` |
| `ADMIN_IDS` | Telegram ID администраторов (через запятую) | — |
| `ANALYSIS_POST_LIMIT` | Сколько постов анализировать | `100` |
| `ANALYSIS_CACHE_HOURS` | Сколько часов использовать кэш | `24` |
| `FREE_ANALYSES_PER_DAY` | Лимит бесплатных анализов/день (`0` = безлимит) | `3` |
| `JOB_QUEUE_BACKEND` | `asyncio` или `redis` | `asyncio` |
| `LOG_LEVEL` | `INFO`, `DEBUG`, ... | `INFO` |

---

## 8. Запуск локально

### Шаг 1. PostgreSQL и Redis

```bash
docker compose up -d postgres redis   # или запустите локально
```

> Для быстрого локального старта можно указать SQLite
> (не для продакшена):
> `DATABASE_URL=sqlite+aiosqlite:///./dev.db`

### Шаг 2. Применить миграции

```bash
alembic upgrade head
```

### Шаг 3. Запустить бота

```bash
python run.py
```

---

## 9. Запуск через Docker

```bash
cp .env.example .env   # заполните ключи
docker compose up -d
```

Compose поднимает `bot`, `postgres` и `redis` одной командой и автоматически
применяет миграции при старте бота.

---

## 10. Структура проекта

```
tg-channel-analyzer/
├── app/
│   ├── main.py                  # точка входа бота
│   ├── config.py                # конфигурация (.env + pydantic-settings)
│   ├── context.py               # общий контекст сервисов (singleton)
│   ├── schemas.py               # Pydantic-модели данных анализа
│   ├── bot/
│   │   ├── handlers/            # start, channel, analysis, favorites,
│   │   │                        # monitoring, settings, admin, compare
│   │   ├── keyboards/           # меню и inline-кнопки
│   │   ├── middlewares/         # DB session middleware
│   │   ├── states.py            # FSM-состояния
│   │   └── deps.py              # DI-хелперы
│   ├── telegram/                # MTProto: client, channel_service, post_service
│   ├── ai/                      # AI: base, openai, mock, post/channel/scam analyzer
│   ├── scoring/                 # trust, quality, scam, advertising, verdict
│   ├── database/                # models, session, repositories
│   ├── services/                # analysis, cache, report, monitoring,
│   │                            # job_queue, rate_limiter, url_analyzer,
│   │                            # localization, session_store
│   └── utils/                   # validators, logger, text
├── prompts/                     # системные промпты (*.txt)
├── locales/                     # ru.json, en.json
├── tests/                       # unit tests + fixtures
├── migrations/                  # Alembic
├── docker/                      # (доп. docker-файлы при необходимости)
├── .env.example
├── .gitignore
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── README.md
└── run.py
```

> Небольшие архитектурные уточнения к ТЗ (обоснование в разделе 11):
> - `post_service.py` вынесен из `telegram/` и реализует персистентность
>   постов и хеширование контента;
> - добавлен `session_store.py` (in-memory) для быстрого отображения
>   разделов отчёта по кнопкам без повторного AI-анализа;
> - репозитории БД вынесены в `database/repositories/`.

---

## 11. Архитектура

Анализ канала построен как многоуровневый конвейер (не один гигантский
prompt):

```text
Telegram Channel
      ↓
Channel Collector  (MTProto/Telethon)
      ↓
Posts
      ↓
Post Analyzer  (AI, по одному посту)
      ↓
Structured JSON (Pydantic-валидация)
      ↓
Aggregation Engine
      ↓
Channel Analyzer (AI, сводный анализ)
      ↓
Risk Engine (scam + url-анализ)
      ↓
Scoring Engine (trust/quality/scam/advertising)
      ↓
Report Generator
      ↓
Telegram Bot
```

Ключевые принципы:

- **AI Provider — интерфейс.** Вся бизнес-логика зависит от абстрактного
  `AIProvider` (`analyze_post`, `analyze_channel`, `analyze_scam_risk`).
  Реализации: `OpenAIProvider`, `MockAIProvider`. Добавление Anthropic/
  Google/local не требует переписывания бизнес-логики.
- **Промпты — в файлах.** Системные промпты лежат в `prompts/*.txt`.
- **Отдельный AnalysisService.** Telegram-хендлеры не выполняют логику
  анализа сами — они вызывают `AnalysisService.analyze(...)`.
- **Асинхронность.** MTProto, AI и БД — async. Тяжёлый анализ выполняется
  в фоновой asyncio-задаче, обновляя сообщение прогресса, не блокируя
  event loop.
- **Scoring изолирован.** Формулы trust/quality/scam/advertising — в
  отдельных модулях `app/scoring/`, их можно менять без переписывания
  системы.

---

## 12. Как работает анализ

1. **Валидация ссылки** — поддерживаются `https://t.me/c`, `t.me/c`,
   `@c`, `c`, ссылки на пост `t.me/c/123` (номер игнорируется).
2. **Получение канала** — метаданные + последние `ANALYSIS_POST_LIMIT` постов.
3. **Проверка кэша** — если канал анализировался недавно
   (`ANALYSIS_CACHE_HOURS`), отдаётся сохранённый результат (кнопка
   «Обновить» запускает новый анализ).
4. **Анализ постов** — каждый пост обрабатывается отдельным AI-запросом,
   возвращающим строгий JSON. Некорректный JSON → retry (несколько попыток);
   при устойчивом сбое пост помечается как `failed`, но анализ канала
   продолжается (отказоустойчивость: «анализ основан на 97 из 100»).
5. **Агрегация** — тематика, контент-микс, активность, engagement, URL-анализ.
6. **Сводный AI-анализ канала** — аудитория, стиль, тональность, резюме.
7. **Scam Risk** — независимый движок (AI + правило-базированный
   URL-анализ): финансовые обещания, давление, переводы, подозрительные
   ссылки, имперсонация.
8. **Scoring** — Quality, Trust, Advertising, Originality, Verdict.
9. **Сохранение** — в БД пишутся channel_analysis, post_analysis,
   channel_snapshots (история), analysis_jobs (статусы).
10. **Отчёт** — компактный + расширенные разделы по кнопкам.

### Метрики и их объяснение

| Метрика | Описание | «Почему?» |
|---|---|---|
| 🧠 Quality | полезность, глубина, источники, информативность | кнопка «🛡 Почему такой рейтинг?» |
| 🛡 Trust | источники, фактология, оригинальность, прозрачность, риск | там же |
| 🚨 Scam Risk | независимый риск-движок | кнопка «🚨 Проверка риска» |
| 📢 Advertising | доля рекламы | полный отчёт |
| 💎 Originality | доля оригинального контента | полный отчёт |

> ⚠️ **Важно:** высокий риск не означает юридически «канал мошеннический».
> Система пишет «обнаружены признаки повышенного риска» и рекомендует
> самостоятельную проверку перед переводами.

---

## 13. Как изменить AI model

В `.env`:

```env
AI_PROVIDER=openai
OPENAI_MODEL=gpt-4o-mini
```

Чтобы добавить нового провайдера, реализуйте `AIProvider` и зарегистрируйте
его в `app/ai/factory.py`.

---

## 14. Как изменить лимиты

```env
ANALYSIS_POST_LIMIT=200     # сколько постов анализировать
MAX_POSTS_PER_ANALYSIS=200  # жёсткий потолок
ANALYSIS_CACHE_HOURS=24     # время жизни кэша
FREE_ANALYSES_PER_DAY=3     # бесплатных анализов в день (0 = безлимит)
```

---

## 15. Как добавить новый язык

1. Создайте `locales/xx.json` (пример — `locales/en.json`).
2. Хендлеры используют `t("key")` из `app/services/localization.py`.
3. Язык можно переключить в настройках бота (кнопка «⚙️ Настройки»).

---

## 16. Как запускать тесты

```bash
pip install -r requirements.txt
python -m pytest -q
```

Тесты не требуют AI-ключа и Telegram: используется `MockAIProvider`,
in-memory SQLite и fake-данные в `tests/fixtures/`. Покрытие: парсер ссылок,
scoring, scam-detector, AI JSON validation, URL-анализатор, CRUD БД,
end-to-end анализ.

---

## 17. Частые ошибки

| Ошибка | Причина / решение |
|---|---|
| `BOT_TOKEN is not set` | не заполнен `.env` |
| Telethon просит вход | подтвердите телефон/код при первом запуске |
| `init_db skipped` | нет доступной БД — проверьте `DATABASE_URL`, запустите Postgres |
| OpenAI ошибка | проверьте `OPENAI_API_KEY`, модель, баланс |
| «Канал приватный» | бот анализирует только публичные каналы |
| Слишком долго | 100 постов требуют ~100 AI-запросов; время зависит от API |

---

## 18. Безопасность

- `.env` и все секреты в `.gitignore`; ключи не попадают в Git.
- Валидация пользовательского ввода (парсер ссылок).
- Admin-команды защищены через `ADMIN_IDS`.
- Rate limiting (`FREE_ANALYSES_PER_DAY`).
- Обработка исключений Telegram API, AI API, timeout, сетевых ошибок.
- SQL injection исключён за счёт SQLAlchemy ORM.
- Не логируются токены, ключи, пароли, чувствительные данные
  (логгер использует allow-list полей).

---

## Privacy considerations

Сервис сохраняет минимально необходимые данные:

- **Пользователи:** `telegram_id`, username, first_name, язык — только для
  работы сервиса (избранное, мониторинг, настройки, rate limiting).
- **Каналы и посты:** публичные данные (название, описание, текст постов,
  просмотры, реакции) — только для анализа. Личные сообщения и приватные
  каналы не собираются.
- **Результаты анализа:** метрики, вердикты, снапшоты истории.

Данные используются исключительно для предоставления сервиса и не
передаются третьим лицам. Пользовательские Telegram-данные не используются
для рассылок без согласия.

---

## 19. Roadmap

- [x] Telegram bot (public channels)
- [x] MTProto collector + post storage
- [x] AI post analysis (structured JSON, retry)
- [x] Channel aggregation + scoring
- [x] Scam Risk Engine + URL analysis
- [x] Trust / Quality / Advertising / Verdict
- [x] Report (compact + sections + best/concerning posts)
- [x] Database + caching + rate limit + logging
- [x] Favorites + Monitoring
- [x] Admin panel + analytics
- [x] Tests + Docker + migrations + README
- [ ] Персональный Match Score
- [ ] Сравнение каналов (MVP уже реализован — `/compare`)
- [ ] Платежи / тарифы PRO
- [ ] Web dashboard / Mini App / PDF/JSON export
- [ ] Дополнительные AI-провайдеры (Anthropic, Google, local)
- [ ] Факт-чекинг через внешние источники

---

## 20. Лицензия / дисклеймер

AI-анализ является информационной оценкой и не гарантирует достоверность
информации. Отсутствие обнаруженных рисков не означает, что канал безопасен.
Перед финансовыми операциями самостоятельно проверяйте автора, компанию,
ссылки и условия.
