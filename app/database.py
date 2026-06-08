"""SQLite async layer."""
import aiosqlite
import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from .config import DB_PATH

log = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    created_at TEXT,
    last_seen TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    session_number INTEGER PRIMARY KEY,
    dice_values TEXT NOT NULL,
    total INTEGER NOT NULL,
    tai_xiu TEXT NOT NULL,
    chan_le TEXT NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_number INTEGER NOT NULL,
    prediction TEXT NOT NULL,
    confidence REAL NOT NULL,
    prediction_correct INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE(session_number)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS banned_users (
    user_id INTEGER PRIMARY KEY,
    reason TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS auto_groups (
    chat_id INTEGER PRIMARY KEY,
    enabled INTEGER DEFAULT 1,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS stats (
    key TEXT PRIMARY KEY,
    value INTEGER DEFAULT 0
);
"""


class DB:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA)
            await db.commit()
        log.info("Database initialised at %s", self.path)

    # ---------- users ----------
    async def upsert_user(self, user_id: int, username: str = "", first_name: str = ""):
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO users (user_id, username, first_name, created_at, last_seen)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(user_id) DO UPDATE SET
                     username=excluded.username,
                     first_name=excluded.first_name,
                     last_seen=excluded.last_seen""",
                (user_id, username, first_name, now, now),
            )
            await db.commit()

    async def all_user_ids(self) -> List[int]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT user_id FROM users")
            rows = await cur.fetchall()
        return [r[0] for r in rows]

    async def count_users(self) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM users")
            (n,) = await cur.fetchone()
        return n

    async def count_active_today(self) -> int:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT COUNT(*) FROM users WHERE substr(last_seen,1,10)=?", (today,)
            )
            (n,) = await cur.fetchone()
        return n

    # ---------- bans ----------
    async def ban_user(self, user_id: int, reason: str = ""):
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO banned_users (user_id, reason, created_at) VALUES (?,?,?)",
                (user_id, reason, now),
            )
            await db.commit()

    async def unban_user(self, user_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM banned_users WHERE user_id=?", (user_id,))
            await db.commit()

    async def is_banned(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT 1 FROM banned_users WHERE user_id=?", (user_id,))
            row = await cur.fetchone()
        return row is not None

    async def count_banned(self) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM banned_users")
            (n,) = await cur.fetchone()
        return n

    # ---------- sessions ----------
    async def insert_session(
        self,
        session_number: int,
        dice_values: List[int],
        total: int,
        tai_xiu: str,
        chan_le: str,
        timestamp: str,
    ) -> bool:
        """Return True if new row inserted."""
        async with aiosqlite.connect(self.path) as db:
            try:
                await db.execute(
                    """INSERT INTO sessions
                       (session_number, dice_values, total, tai_xiu, chan_le, timestamp)
                       VALUES (?,?,?,?,?,?)""",
                    (
                        session_number,
                        ",".join(map(str, dice_values)),
                        total,
                        tai_xiu,
                        chan_le,
                        timestamp,
                    ),
                )
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False

    async def session_exists(self, session_number: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT 1 FROM sessions WHERE session_number=?", (session_number,)
            )
            row = await cur.fetchone()
        return row is not None

    async def last_session(self) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM sessions ORDER BY session_number DESC LIMIT 1"
            )
            row = await cur.fetchone()
        return dict(row) if row else None

    async def recent_sessions(self, limit: int = 200) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM sessions ORDER BY session_number DESC LIMIT ?", (limit,)
            )
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # ---------- predictions ----------
    async def insert_prediction(self, session_number: int, prediction: str, confidence: float):
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.path) as db:
            try:
                await db.execute(
                    """INSERT INTO predictions
                       (session_number, prediction, confidence, created_at)
                       VALUES (?,?,?,?)""",
                    (session_number, prediction, confidence, now),
                )
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False

    async def get_prediction(self, session_number: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM predictions WHERE session_number=?", (session_number,)
            )
            row = await cur.fetchone()
        return dict(row) if row else None

    async def update_prediction_outcome(self, session_number: int, correct: bool):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE predictions SET prediction_correct=? WHERE session_number=?",
                (1 if correct else 0, session_number),
            )
            await db.commit()

    async def recent_prediction_outcomes(self, limit: int = 20) -> List[int]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                """SELECT prediction_correct FROM predictions
                   WHERE prediction_correct IS NOT NULL
                   ORDER BY session_number DESC LIMIT ?""",
                (limit,),
            )
            rows = await cur.fetchall()
        return [r[0] for r in rows]

    async def prediction_stats(self) -> Dict[str, int]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                """SELECT
                       COUNT(*) total,
                       SUM(CASE WHEN prediction_correct=1 THEN 1 ELSE 0 END) wins,
                       SUM(CASE WHEN prediction_correct=0 THEN 1 ELSE 0 END) losses
                   FROM predictions WHERE prediction_correct IS NOT NULL"""
            )
            row = await cur.fetchone()
        total, wins, losses = row or (0, 0, 0)
        return {"total": total or 0, "wins": wins or 0, "losses": losses or 0}

    # ---------- auto groups ----------
    async def add_auto_group(self, chat_id: int):
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO auto_groups (chat_id, enabled, created_at) VALUES (?,1,?)",
                (chat_id, now),
            )
            await db.commit()

    async def remove_auto_group(self, chat_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM auto_groups WHERE chat_id=?", (chat_id,))
            await db.commit()

    async def auto_groups(self) -> List[int]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT chat_id FROM auto_groups WHERE enabled=1")
            rows = await cur.fetchall()
        return [r[0] for r in rows]

    # ---------- settings ----------
    async def set_setting(self, key: str, value: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, value)
            )
            await db.commit()

    async def get_setting(self, key: str) -> Optional[str]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
            row = await cur.fetchone()
        return row[0] if row else None


db = DB()
