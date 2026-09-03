"""SQLite: очередь постов, пользователи+источники, входы, конкурсы, активность чата."""
import time
from datetime import datetime
import aiosqlite

DB_PATH = "growth.db"


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


async def init_db(path: str = DB_PATH):
    global DB_PATH
    DB_PATH = path
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_chat INTEGER, message_id INTEGER, ts INTEGER)"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, username TEXT DEFAULT '',
                full_name TEXT DEFAULT '', source TEXT DEFAULT '',
                joined_at INTEGER DEFAULT 0)"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS joins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT, ts INTEGER, user_id INTEGER, source TEXT DEFAULT '')"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS contests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prize TEXT, winners_n INTEGER, deadline INTEGER,
                channel_msg_id INTEGER DEFAULT 0, status TEXT DEFAULT 'open',
                created_at INTEGER)"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS participants (
                contest_id INTEGER, user_id INTEGER, ts INTEGER,
                UNIQUE(contest_id, user_id))"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS activity (
                user_id INTEGER PRIMARY KEY, username TEXT DEFAULT '',
                full_name TEXT DEFAULT '', msgs INTEGER DEFAULT 0)"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS subs_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT, ts INTEGER, subs INTEGER)"""
        )
        await db.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)")
        await db.commit()


# --- state ---
async def get_state(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM state WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else default


async def set_state(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO state (key, value) VALUES (?,?)", (key, value))
        await db.commit()


# --- queue ---
async def queue_add(from_chat: int, message_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "INSERT INTO queue (from_chat, message_id, ts) VALUES (?,?,?)",
            (from_chat, message_id, int(time.time())),
        ) as cur:
            await db.commit()
            return cur.lastrowid


async def queue_pop() -> tuple[int, int, int] | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, from_chat, message_id FROM queue ORDER BY id LIMIT 1") as cur:
            row = await cur.fetchone()
            if not row:
                return None
            await db.execute("DELETE FROM queue WHERE id=?", (row[0],))
            await db.commit()
            return (row[0], row[1], row[2])


async def queue_len() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM queue") as cur:
            return (await cur.fetchone())[0]


async def queue_clear() -> int:
    n = await queue_len()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM queue")
        await db.commit()
    return n


# --- users / joins ---
async def upsert_user(uid: int, username: str = "", full_name: str = "", source: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO users (user_id, username, full_name, source, joined_at)
               VALUES (?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, full_name=excluded.full_name""",
            (uid, username, full_name, source, int(time.time())),
        )
        await db.commit()


async def log_join(uid: int, source: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO joins (day, ts, user_id, source) VALUES (?,?,?,?)",
            (today(), int(time.time()), uid, source or "—"),
        )
        await db.commit()


async def joins_by_source(day: str | None = None) -> list[tuple[str, int]]:
    q = "SELECT source, COUNT(*) FROM joins" + (" WHERE day=?" if day else "") + " GROUP BY source ORDER BY 2 DESC"
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(q, (day,) if day else ()) as cur:
            return [(r[0], r[1]) for r in await cur.fetchall()]


async def joins_total(day: str | None = None) -> int:
    q = "SELECT COUNT(*) FROM joins" + (" WHERE day=?" if day else "")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(q, (day,) if day else ()) as cur:
            return (await cur.fetchone())[0]


async def log_subs(subs: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO subs_log (day, ts, subs) VALUES (?,?,?)", (today(), int(time.time()), subs))
        await db.commit()


async def subs_first_last(days: int = 7) -> tuple[int | None, int | None]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT MIN(subs), MAX(subs) FROM subs_log WHERE ts>? ", (int(time.time()) - days * 86400,)
        ) as cur:
            row = await cur.fetchone()
            return (row[0], row[1]) if row else (None, None)


# --- contests ---
async def contest_create(prize: str, winners_n: int, deadline: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "INSERT INTO contests (prize, winners_n, deadline, created_at) VALUES (?,?,?,?)",
            (prize, winners_n, deadline, int(time.time())),
        ) as cur:
            await db.commit()
            return cur.lastrowid


async def contest_get(cid: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM contests WHERE id=?", (cid,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def contest_set_msg(cid: int, msg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE contests SET channel_msg_id=? WHERE id=?", (msg_id, cid))
        await db.commit()


async def contest_close(cid: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE contests SET status='done' WHERE id=?", (cid,))
        await db.commit()


async def contest_extend(cid: int, extra_seconds: int = 86400):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE contests SET deadline=? WHERE id=?",
                         (int(time.time()) + extra_seconds, cid))
        await db.commit()


async def open_contests() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM contests WHERE status='open' ORDER BY id") as cur:
            return [dict(r) for r in await cur.fetchall()]


async def contest_add(cid: int, uid: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("INSERT INTO participants (contest_id, user_id, ts) VALUES (?,?,?)",
                             (cid, uid, int(time.time())))
            await db.commit()
            return True
        except Exception:
            return False


async def contest_count(cid: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM participants WHERE contest_id=?", (cid,)) as cur:
            return (await cur.fetchone())[0]


async def contest_users(cid: int) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM participants WHERE contest_id=?", (cid,)) as cur:
            return [r[0] for r in await cur.fetchall()]


# --- activity ---
async def bump_activity(uid: int, username: str, full_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO activity (user_id, username, full_name, msgs) VALUES (?,?,?,1)
               ON CONFLICT(user_id) DO UPDATE SET msgs=msgs+1, username=excluded.username, full_name=excluded.full_name""",
            (uid, username, full_name),
        )
        await db.commit()


async def chat_top(limit: int = 10) -> list[tuple[int, str, str, int]]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, username, full_name, msgs FROM activity ORDER BY msgs DESC LIMIT ?",
                              (limit,)) as cur:
            return [tuple(r) for r in await cur.fetchall()]


async def activity_reset():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM activity")
        await db.commit()
