"""SQLite-хранилище автопилота: лог комментариев, подписки, состояние."""
import time
from datetime import datetime
import aiosqlite

DB_PATH = "autopilot.db"


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


async def init_db(path: str = DB_PATH):
    global DB_PATH
    DB_PATH = path
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS comments_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT, ts INTEGER, donor TEXT, post_id INTEGER,
                variant INTEGER, status TEXT, error TEXT DEFAULT ''
            )"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS subs_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT, ts INTEGER, subs INTEGER
            )"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY, value TEXT
            )"""
        )
        await db.commit()


async def get_state(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM state WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else default


async def set_state(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO state (key, value) VALUES (?,?)", (key, value))
        await db.commit()


async def already_commented(donor: str, post_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM comments_log WHERE donor=? AND post_id=? AND status IN ('sent','dry')",
            (donor, post_id),
        ) as cur:
            return await cur.fetchone() is not None


async def log_comment(donor: str, post_id: int, variant: int, status: str, error: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO comments_log (day, ts, donor, post_id, variant, status, error) VALUES (?,?,?,?,?,?,?)",
            (today(), int(time.time()), donor, post_id, variant, status, error[:300]),
        )
        await db.commit()


async def comments_today() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM comments_log WHERE day=? AND status IN ('sent','dry')", (today(),)
        ) as cur:
            return (await cur.fetchone())[0]


async def comments_today_for_donor(donor: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM comments_log WHERE day=? AND donor=? AND status IN ('sent','dry')",
            (today(), donor),
        ) as cur:
            return (await cur.fetchone())[0]


async def variant_usage() -> dict[int, int]:
    """Сколько раз использовался каждый шаблон — для равномерной ротации."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT variant, COUNT(*) FROM comments_log WHERE status IN ('sent','dry') GROUP BY variant"
        ) as cur:
            return {r[0]: r[1] for r in await cur.fetchall()}


async def log_subs(subs: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO subs_log (day, ts, subs) VALUES (?,?,?)", (today(), int(time.time()), subs)
        )
        await db.commit()


async def subs_series(days: int = 14) -> list[tuple[str, int]]:
    """Последнее значение подписчиков по дням."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT day, MAX(subs) FROM subs_log GROUP BY day ORDER BY day DESC LIMIT ?""",
            (days,),
        ) as cur:
            rows = await cur.fetchall()
            return list(reversed(rows))


async def comments_stats(days: int = 7) -> list[tuple[str, int]]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT day, COUNT(*) FROM comments_log
               WHERE status IN ('sent','dry') GROUP BY day ORDER BY day DESC LIMIT ?""",
            (days,),
        ) as cur:
            rows = await cur.fetchall()
            return list(reversed(rows))
