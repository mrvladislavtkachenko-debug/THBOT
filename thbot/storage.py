"""Минимальное хранилище на SQLite: кэш отчётов, суточные лимиты, фидбек.

Для MVP отдельная БД не нужна; sqlite3 из stdlib оборачиваем в to_thread,
чтобы не блокировать event loop.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

from .config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    username    TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    created_at  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
    user_id     INTEGER NOT NULL,
    day         TEXT NOT NULL,
    count       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);
CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT NOT NULL,
    user_id     INTEGER NOT NULL,
    vote        TEXT NOT NULL,
    created_at  INTEGER NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path)
    conn.executescript(_SCHEMA)
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.commit()


# ------------------------------- кэш отчётов ---------------------------------

def _get_report(username: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT payload, created_at FROM reports WHERE username = ?", (username,)
        ).fetchone()
    if not row:
        return None
    payload, created_at = row
    age_hours = (time.time() - created_at) / 3600
    if age_hours > settings.cache_ttl_hours:
        return None
    return json.loads(payload)


def _save_report(username: str, payload: dict[str, Any]) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO reports (username, payload, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(username) DO UPDATE SET payload = excluded.payload, "
            "created_at = excluded.created_at",
            (username, json.dumps(payload, ensure_ascii=False), int(time.time())),
        )
        conn.commit()


async def get_cached_report(username: str) -> dict[str, Any] | None:
    return await asyncio_to_thread(_get_report, username)


async def save_report(username: str, payload: dict[str, Any]) -> None:
    await asyncio_to_thread(_save_report, username, payload)


# -------------------------------- лимиты -------------------------------------

def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _usage_count(user_id: int) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT count FROM usage WHERE user_id = ? AND day = ?",
            (user_id, _today()),
        ).fetchone()
    return row[0] if row else 0


def _usage_increment(user_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO usage (user_id, day, count) VALUES (?, ?, 1) "
            "ON CONFLICT(user_id, day) DO UPDATE SET count = count + 1",
            (user_id, _today()),
        )
        conn.commit()


async def usage_left(user_id: int) -> int:
    return settings.user_daily_limit - await asyncio_to_thread(_usage_count, user_id)


async def usage_increment(user_id: int) -> None:
    await asyncio_to_thread(_usage_increment, user_id)


# -------------------------------- фидбек -------------------------------------

def _save_feedback(username: str, user_id: int, vote: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO feedback (username, user_id, vote, created_at) VALUES (?, ?, ?, ?)",
            (username, user_id, vote, int(time.time())),
        )
        conn.commit()


async def save_feedback(username: str, user_id: int, vote: str) -> None:
    await asyncio_to_thread(_save_feedback, username, user_id, vote)


async def asyncio_to_thread(func, *args):  # noqa: ANN001
    return await asyncio.to_thread(func, *args)
