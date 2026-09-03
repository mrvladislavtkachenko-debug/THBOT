"""Настройки автопилота. Всё тянется из .env"""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _list(raw: str) -> list[str]:
    return [x.strip() for x in (raw or "").replace(";", ",").split(",") if x.strip()]


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (ValueError, TypeError):
        return default


@dataclass
class Config:
    api_id: int = _int("API_ID", 0)
    api_hash: str = os.getenv("API_HASH", "")
    session_name: str = os.getenv("SESSION_NAME", "autopilot")

    my_channel: str = os.getenv("MY_CHANNEL", "")
    signature: str = os.getenv("SIGNATURE", "")
    donors: list[str] = field(default_factory=lambda: _list(os.getenv("DONORS", "")))
    send_as: str = os.getenv("SEND_AS", "")

    max_comments_per_day: int = _int("MAX_COMMENTS_PER_DAY", 6)
    max_per_donor_per_day: int = _int("MAX_PER_DONOR_PER_DAY", 2)
    comment_delay_min: int = _int("COMMENT_DELAY_MIN", 15)
    comment_delay_max: int = _int("COMMENT_DELAY_MAX", 45)
    active_start: int = _int("ACTIVE_HOURS_START", 9)
    active_end: int = _int("ACTIVE_HOURS_END", 23)
    stopwords: list[str] = field(default_factory=lambda: [s.lower() for s in _list(os.getenv("STOPWORDS", ""))])

    dry_run: bool = os.getenv("DRY_RUN", "1") == "1"

    autopost_enabled: bool = os.getenv("AUTOPOST_ENABLED", "1") == "1"
    autopost_times: list[str] = field(default_factory=lambda: _list(os.getenv("AUTOPOST_TIMES", "09:00,13:00,19:00")))
    posts_file: str = os.getenv("POSTS_FILE", "posts.txt")
    comments_file: str = os.getenv("COMMENTS_FILE", "comments.txt")

    subs_check_hours: int = _int("SUBS_CHECK_HOURS", 6)
    report_time: str = os.getenv("REPORT_TIME", "09:30")
    db_path: str = os.getenv("DB_PATH", "autopilot.db")


config = Config()

missing = [k for k in ("API_ID", "API_HASH") if not os.getenv(k)]
if missing:
    print(f"⚠️  В .env не хватает: {', '.join(missing)}. Возьми на https://my.telegram.org")
if not config.donors:
    print("⚠️  DONORS пустой — не за кем следить. Добавь 5–15 каналов своей ниши.")
if not config.my_channel:
    print("⚠️  MY_CHANNEL пустой — статистика подписок и автопостинг не будут работать.")
