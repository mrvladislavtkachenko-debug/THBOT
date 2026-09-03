"""Настройки Growth-бота. Всё тянется из .env"""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (ValueError, TypeError):
        return default


def _bool(name: str, default: bool = True) -> bool:
    return os.getenv(name, "1" if default else "0") == "1"


def _list(raw: str) -> list[str]:
    return [x.strip() for x in (raw or "").replace(";", ",").split(",") if x.strip()]


def _to_id(raw: str) -> int:
    try:
        return int((raw or "0").strip())
    except ValueError:
        return 0


@dataclass
class Config:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    channel_id: int = _to_id(os.getenv("CHANNEL_ID", "0"))
    channel_url: str = os.getenv("CHANNEL_URL", "")
    chat_id: int = _to_id(os.getenv("CHAT_ID", "0"))
    admin_ids: set[int] = field(default_factory=lambda: {int(x) for x in _list(os.getenv("ADMIN_IDS", "")) if x.isdigit()})

    autopost_times: list[str] = field(default_factory=lambda: _list(os.getenv("AUTOPOST_TIMES", "09:00,13:00,19:00")))
    quiz_times: list[str] = field(default_factory=lambda: _list(os.getenv("QUIZ_TIMES", "12:00,18:00")))
    poll_times: list[str] = field(default_factory=lambda: _list(os.getenv("POLL_TIMES", "15:00")))
    quiz_file: str = os.getenv("QUIZ_FILE", "quiz.txt")
    polls_file: str = os.getenv("POLLS_FILE", "polls.txt")

    welcome_new: bool = _bool("WELCOME_NEW", True)
    captcha: bool = _bool("CAPTCHA", True)
    antispam: bool = _bool("ANTISPAM", True)
    banwords: list[str] = field(default_factory=lambda: [s.lower() for s in _list(os.getenv("BANWORDS", ""))])
    weekly_top: bool = _bool("WEEKLY_TOP", True)
    top_day: int = _int("TOP_DAY", 0)  # 0 = понедельник
    top_time: str = os.getenv("TOP_TIME", "09:05")

    report_time: str = os.getenv("REPORT_TIME", "09:30")
    db_path: str = os.getenv("DB_PATH", "growth.db")


config = Config()

if not config.bot_token:
    print("⚠️  Нет BOT_TOKEN в .env — возьми у @BotFather.")
if not config.channel_id:
    print("⚠️  Нет CHANNEL_ID в .env — перешли пост из канала @userinfobot.")
