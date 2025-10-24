"""Database helpers for Tomorrow Planner bot."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from typing import Dict, List, Optional

DEFAULT_DB_PATH = "events.db"


class Database:
    """Lightweight wrapper around SQLite for storing events and RSVPs."""

    def __init__(self, path: str = DEFAULT_DB_PATH) -> None:
        self.path = path
        self._ensure_tables()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_tables(self) -> None:
        with closing(self._get_connection()) as conn:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        type TEXT NOT NULL,
                        time TEXT NOT NULL,
                        location TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS rsvp (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(event_id, user_id),
                        FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
                    )
                    """
                )

    def create_event(
        self,
        user_id: int,
        title: str,
        event_type: str,
        time: str,
        location: str,
    ) -> int:
        now = datetime.utcnow().isoformat(timespec="seconds")
        with closing(self._get_connection()) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO events (user_id, title, type, time, location, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, title, event_type, time, location, now),
                )
                return cursor.lastrowid

    def delete_event(self, event_id: int, user_id: int) -> bool:
        with closing(self._get_connection()) as conn:
            with conn:
                cursor = conn.execute(
                    "DELETE FROM events WHERE id = ? AND user_id = ?",
                    (event_id, user_id),
                )
                return cursor.rowcount > 0

    def get_events_by_user(self, user_id: int) -> List[sqlite3.Row]:
        with closing(self._get_connection()) as conn:
            cursor = conn.execute(
                "SELECT * FROM events WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            )
            return cursor.fetchall()

    def get_event(self, event_id: int) -> Optional[sqlite3.Row]:
        with closing(self._get_connection()) as conn:
            cursor = conn.execute(
                "SELECT * FROM events WHERE id = ?",
                (event_id,),
            )
            return cursor.fetchone()

    def upsert_rsvp(self, event_id: int, user_id: int, status: str) -> None:
        now = datetime.utcnow().isoformat(timespec="seconds")
        with closing(self._get_connection()) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO rsvp (event_id, user_id, status, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(event_id, user_id)
                    DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at
                    """,
                    (event_id, user_id, status, now),
                )

    def get_rsvp(self, event_id: int, user_id: int) -> Optional[sqlite3.Row]:
        with closing(self._get_connection()) as conn:
            cursor = conn.execute(
                "SELECT * FROM rsvp WHERE event_id = ? AND user_id = ?",
                (event_id, user_id),
            )
            return cursor.fetchone()

    def get_rsvp_counts(self, event_id: int) -> Dict[str, int]:
        with closing(self._get_connection()) as conn:
            cursor = conn.execute(
                """
                SELECT status, COUNT(*) as total
                FROM rsvp
                WHERE event_id = ?
                GROUP BY status
                """,
                (event_id,),
            )
            counts: Dict[str, int] = {"yes": 0, "no": 0, "maybe": 0}
            for row in cursor.fetchall():
                counts[row["status"].lower()] = row["total"]
            return counts

    def list_event_participants(self, event_id: int) -> List[sqlite3.Row]:
        with closing(self._get_connection()) as conn:
            cursor = conn.execute(
                "SELECT * FROM rsvp WHERE event_id = ?",
                (event_id,),
            )
            return cursor.fetchall()


def load_database(path: Optional[str]) -> Database:
    return Database(path or DEFAULT_DB_PATH)
