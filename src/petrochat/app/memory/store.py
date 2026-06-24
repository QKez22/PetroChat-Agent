"""SQLite-backed conversation store for short-term memory."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from ..core.config import get_settings


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class StoredMessage:
    id: str
    conversation_id: str
    role: str
    content: str
    route: str | None
    latency_ms: int | None
    created_at: str


class ConversationStore:
    """Small SQLite store for conversation history.

    The project already uses a read-only MySQL account for business data. Keeping
    chat sessions in a separate local SQLite file avoids weakening that boundary
    while still giving the agent persistent short-term memory.
    """

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversation (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS message (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    route TEXT,
                    latency_ms INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversation(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_message_conversation_created
                    ON message(conversation_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_conversation_user_updated
                    ON conversation(user_id, updated_at DESC);
                """
            )

    def create_session(self, user_id: str = "default", title: str | None = None) -> str:
        session_id = uuid.uuid4().hex
        now = _now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conversation(id, user_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, user_id, title or "新会话", now, now),
            )
        return session_id

    def ensure_session(
        self,
        session_id: str | None,
        user_id: str = "default",
        title: str | None = None,
    ) -> str:
        if not session_id:
            return self.create_session(user_id=user_id, title=title)

        now = _now_iso()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM conversation WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row:
                return session_id
            conn.execute(
                """
                INSERT INTO conversation(id, user_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, user_id, title or "新会话", now, now),
            )
        return session_id

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        route: str | None = None,
        latency_ms: int | None = None,
    ) -> StoredMessage:
        if role not in {"user", "assistant"}:
            raise ValueError(f"unsupported role: {role}")
        msg = StoredMessage(
            id=uuid.uuid4().hex,
            conversation_id=conversation_id,
            role=role,
            content=content,
            route=route,
            latency_ms=latency_ms,
            created_at=_now_iso(),
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO message(id, conversation_id, role, content, route, latency_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    msg.id,
                    msg.conversation_id,
                    msg.role,
                    msg.content,
                    msg.route,
                    msg.latency_ms,
                    msg.created_at,
                ),
            )
            conn.execute(
                "UPDATE conversation SET updated_at = ? WHERE id = ?",
                (msg.created_at, conversation_id),
            )
        return msg

    def append_turn(
        self,
        conversation_id: str,
        question: str,
        answer: str,
        *,
        route: str | None = None,
        latency_ms: int | None = None,
    ) -> None:
        self.append_message(conversation_id, "user", question)
        if answer.strip():
            self.append_message(
                conversation_id,
                "assistant",
                answer,
                route=route,
                latency_ms=latency_ms,
            )

    def recent_messages(self, conversation_id: str, turns: int) -> list[StoredMessage]:
        limit = max(turns, 0) * 2
        if limit <= 0:
            return []
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, conversation_id, role, content, route, latency_ms, created_at
                FROM message
                WHERE conversation_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()
        return [
            StoredMessage(
                id=row["id"],
                conversation_id=row["conversation_id"],
                role=row["role"],
                content=row["content"],
                route=row["route"],
                latency_ms=row["latency_ms"],
                created_at=row["created_at"],
            )
            for row in reversed(rows)
        ]

    def list_sessions(self, user_id: str = "default", limit: int = 30) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.user_id, c.title, c.created_at, c.updated_at,
                       COUNT(m.id) AS message_count
                FROM conversation c
                LEFT JOIN message m ON m.conversation_id = c.id
                WHERE c.user_id = ?
                GROUP BY c.id
                ORDER BY c.updated_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_messages(self, conversation_id: str, limit: int = 200) -> list[StoredMessage]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, conversation_id, role, content, route, latency_ms, created_at
                FROM message
                WHERE conversation_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()
        return [
            StoredMessage(
                id=row["id"],
                conversation_id=row["conversation_id"],
                role=row["role"],
                content=row["content"],
                route=row["route"],
                latency_ms=row["latency_ms"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def delete_session(self, conversation_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM conversation WHERE id = ?", (conversation_id,))
            return cur.rowcount > 0


@lru_cache(maxsize=1)
def get_conversation_store() -> ConversationStore:
    return ConversationStore(get_settings().session_store_path)
