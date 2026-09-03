"""Конфигурация бота. Все настройки тянутся из .env"""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _parse_admins(raw: str) -> set[int]:
    admins: set[int] = set()
    for part in (raw or "").replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            admins.add(int(part))
    return admins


def _parse_levels(raw: str) -> list[int]:
    try:
        levels = sorted({int(x.strip()) for x in raw.split(",") if x.strip().isdigit()})
        return levels or [0, 3, 10]
    except Exception:
        return [0, 3, 10]


@dataclass
class Gift:
    level: int
    name: str
    url: str
    desc: str = ""


@dataclass
class Config:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    channel_id: str = os.getenv("CHANNEL_ID", "")
    channel_url: str = os.getenv("CHANNEL_URL", "https://t.me/durov")
    channel_username: str = os.getenv("CHANNEL_USERNAME", "durov")
    support_username: str = os.getenv("SUPPORT_USERNAME", "")
    admin_ids: set[int] = field(default_factory=lambda: _parse_admins(os.getenv("ADMIN_IDS", "")))
    levels: list[int] = field(default_factory=lambda: _parse_levels(os.getenv("REWARD_LEVELS", "0,3,10")))
    gifts: dict[int, Gift] = field(default_factory=dict)
    db_path: str = os.getenv("DB_PATH", "bot.db")

    def __post_init__(self):
        self.gifts = {
            0: Gift(
                0,
                os.getenv("GIFT_NAME_0", "Чек-лист «10 ошибок новичка»"),
                os.getenv("GIFT_URL_0", self.channel_url),
                os.getenv("GIFT_DESC_0", "Базовый подарок за подписку"),
            ),
            3: Gift(
                3,
                os.getenv("GIFT_NAME_3", "Гайд «Как вырасти в доходе за 30 дней»"),
                os.getenv("GIFT_URL_3", self.channel_url),
            ),
            10: Gift(
                10,
                os.getenv("GIFT_NAME_10", "Мини-курс / личный разбор от автора"),
                os.getenv("GIFT_URL_10", self.channel_url),
            ),
        }
        # Уровни из .env маппим на подарки: берём ближайший описанный
        # Если админ задал свои уровни — подарок берётся по ключу, иначе дефолт
        for lvl in self.levels:
            if lvl not in self.gifts:
                # подхватываем ближайший меньший подарок как заглушку
                known = sorted(self.gifts.keys())
                fallback = max([k for k in known if k <= lvl], default=0)
                g = self.gifts[fallback]
                self.gifts[lvl] = Gift(lvl, g.name, g.url, g.desc)

    @property
    def chat_id(self):
        """CHANNEL_ID может быть числом (-100...) или @username."""
        raw = (self.channel_id or "").strip()
        if not raw:
            return raw
        try:
            return int(raw)
        except ValueError:
            return raw if raw.startswith("@") else f"@{raw}"


config = Config()

REQUIRED = ["BOT_TOKEN", "CHANNEL_ID"]
missing = [k for k in REQUIRED if not os.getenv(k)]
if missing:
    print(f"⚠️  В .env не хватает: {', '.join(missing)}. Скопируй .env.example в .env и заполни.")
