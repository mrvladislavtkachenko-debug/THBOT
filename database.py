"""SQLite-слой на aiosqlite. Таблицы: users, referrals."""
import time
import aiosqlite

DB_PATH = "bot.db"


async def init_db(path: str = DB_PATH):
    global DB_PATH
    DB_PATH = path
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT DEFAULT '',
                full_name TEXT DEFAULT '',
                referrer_id INTEGER DEFAULT NULL,
                is_subscribed INTEGER DEFAULT 0,
                joined_at INTEGER DEFAULT 0,
                last_seen INTEGER DEFAULT 0
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL UNIQUE,
                is_valid INTEGER DEFAULT 0,
                created_at INTEGER DEFAULT 0
            )
            """
        )
        await db.commit()


async def upsert_user(user_id: int, username: str = "", full_name: str = "") -> dict:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
        if row is None:
            await db.execute(
                "INSERT INTO users (user_id, username, full_name, joined_at, last_seen) VALUES (?,?,?,?,?)",
                (user_id, username, full_name, now, now),
            )
            await db.commit()
            return {"user_id": user_id, "username": username, "full_name": full_name,
                    "referrer_id": None, "is_subscribed": 0}
        await db.execute(
            "UPDATE users SET username=?, full_name=?, last_seen=? WHERE user_id=?",
            (username, full_name, now, user_id),
        )
        await db.commit()
        return dict(row)


async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def try_set_referrer(user_id: int, referrer_id: int) -> bool:
    """Привязать реферера один раз. Нельзя самому себе и по кругу. Возвращает True если привязали."""
    if user_id == referrer_id:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id=?", (referrer_id,)) as cur:
            if await cur.fetchone() is None:
                return False  # реферера нет в базе
        async with db.execute("SELECT referrer_id FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row is None or row["referrer_id"]:
                return False  # уже есть реферер
        await db.execute("UPDATE users SET referrer_id=? WHERE user_id=?", (referrer_id, user_id))
        try:
            await db.execute(
                "INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?,?,?)",
                (referrer_id, user_id, int(time.time())),
            )
        except Exception:
            pass  # уже есть запись (UNIQUE)
        await db.commit()
        return True


async def set_subscribed(user_id: int, value: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_subscribed=? WHERE user_id=?", (1 if value else 0, user_id))
        # валидность реферала = подписка реферала
        await db.execute(
            "UPDATE referrals SET is_valid=? WHERE referred_id=?", (1 if value else 0, user_id)
        )
        await db.commit()


async def valid_referrals_count(referrer_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND is_valid=1", (referrer_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def get_referrer_of(user_id: int) -> int | None:
    u = await get_user(user_id)
    return u.get("referrer_id") if u else None


async def get_top(limit: int = 10) -> list[tuple[int, str, str, int]]:
    """[(user_id, username, full_name, valid_count)]"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        q = """
        SELECT u.user_id, u.username, u.full_name,
               (SELECT COUNT(*) FROM referrals r WHERE r.referrer_id=u.user_id AND r.is_valid=1) AS cnt
        FROM users u ORDER BY cnt DESC, u.joined_at ASC LIMIT ?
        """
        async with db.execute(q, (limit,)) as cur:
            rows = await cur.fetchall()
            return [(r["user_id"], r["username"] or "", r["full_name"] or "", r["cnt"]) for r in rows]


async def get_place(user_id: int) -> int:
    top_all: list = []
    async with aiosqlite.connect(DB_PATH) as db:
        q = """
        SELECT u.user_id,
               (SELECT COUNT(*) FROM referrals r WHERE r.referrer_id=u.user_id AND r.is_valid=1) AS cnt,
               u.joined_at
        FROM users u ORDER BY cnt DESC, u.joined_at ASC
        """
        async with db.execute(q) as cur:
            top_all = await cur.fetchall()
    for i, r in enumerate(top_all, start=1):
        if r[0] == user_id:
            return i
    return len(top_all) + 1


async def get_stats() -> dict:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            total = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_subscribed=1") as c:
            subs = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM referrals WHERE is_valid=1") as c:
            refs = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE joined_at>?", (now - 86400,)) as c:
            day = (await c.fetchone())[0]
    return {"total": total, "subs": subs, "refs": refs, "day": day}


async def get_all_user_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cur:
            return [r[0] for r in await cur.fetchall()]


async def export_rows(limit: int = 5000):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        q = """
        SELECT u.user_id, u.username, u.full_name, u.referrer_id, u.is_subscribed,
               (SELECT COUNT(*) FROM referrals r WHERE r.referrer_id=u.user_id AND r.is_valid=1) AS refs
        FROM users u ORDER BY u.joined_at DESC LIMIT ?
        """
        async with db.execute(q, (limit,)) as cur:
            return [dict(r) for r in await cur.fetchall()]
