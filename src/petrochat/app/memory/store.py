"""MySQL-backed conversation store for short-term memory."""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from sqlalchemy import text
UTC = timezone.utc  # Py3.10 兼容（3.11+ datetime.UTC 等价）
from sqlalchemy.engine import Engine

from ..sql.engine import get_app_engine as get_engine


def _now_db() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


_id_lock = threading.Lock()
_last_id = 0


def _new_bigint_id() -> int:
    global _last_id
    candidate = int(time.time() * 1000) * 100_000 + random.randint(0, 99_999)
    with _id_lock:
        if candidate <= _last_id:
            candidate = _last_id + 1
        _last_id = candidate
        return candidate


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
    """Small MySQL store for conversation history.

    Chat memory uses application tables (`agent_conversation`, `agent_message`)
    instead of the read-only business tables used by NL2SQL.
    """

    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or get_engine()
        self._lock = threading.RLock()

    def create_session(self, user_id: str = "default", title: str | None = None) -> str:
        session_id = _new_bigint_id()
        now = _now_db()
        with self._lock, self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO agent_conversation(
                        id, user_id, title, created_at, updated_at,
                        expires_at, deleted_at, delete_status, retention_policy
                    )
                    VALUES (
                        :id, :user_id, :title, :created_at, :updated_at,
                        NULL, NULL, 'active', 'conversation_180d'
                    )
                    """
                ),
                {
                    "id": session_id,
                    "user_id": self._user_id_value(user_id),
                    "title": title or "新会话",
                    "created_at": now,
                    "updated_at": now,
                },
            )
        return str(session_id)

    def ensure_session(
        self,
        session_id: str | None,
        user_id: str = "default",
        title: str | None = None,
    ) -> str:
        if not session_id:
            return self.create_session(user_id=user_id, title=title)

        try:
            session_key = self._id_value(session_id)
        except ValueError:
            return self.create_session(user_id=user_id, title=title)

        with self._lock, self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id
                    FROM agent_conversation
                    WHERE id = :id AND deleted_at IS NULL
                    LIMIT 1
                    """
                ),
                {"id": session_key},
            ).mappings().first()
            if row:
                return str(row["id"])
        return self.create_session(user_id=user_id, title=title)

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
        now = _now_db()
        message_id = _new_bigint_id()
        msg = StoredMessage(
            id=str(message_id),
            conversation_id=str(conversation_id),
            role=role,
            content=content,
            route=route,
            latency_ms=latency_ms,
            created_at=now,
        )
        with self._lock, self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO agent_message(id, conversation_id, role, content, created_at, deleted_at)
                    VALUES (:id, :conversation_id, :role, :content, :created_at, NULL)
                    """
                ),
                {
                    "id": message_id,
                    "conversation_id": self._id_value(conversation_id),
                    "role": role,
                    "content": content,
                    "created_at": now,
                },
            )
            conn.execute(
                text("UPDATE agent_conversation SET updated_at = :updated_at WHERE id = :id"),
                {"updated_at": now, "id": self._id_value(conversation_id)},
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
        with self._lock, self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, conversation_id, role, content, created_at
                    FROM agent_message
                    WHERE conversation_id = :conversation_id AND deleted_at IS NULL
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit
                    """
                ),
                {"conversation_id": self._id_value(conversation_id), "limit": limit},
            ).mappings().all()
        return [self._row_to_message(row) for row in reversed(rows)]

    def list_sessions(self, user_id: str = "default", limit: int = 30) -> list[dict[str, Any]]:
        with self._lock, self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT c.id, c.user_id, c.title, c.created_at, c.updated_at,
                           COUNT(m.id) AS message_count
                    FROM agent_conversation c
                    LEFT JOIN agent_message m
                        ON m.conversation_id = c.id AND m.deleted_at IS NULL
                    WHERE c.user_id = :user_id AND c.deleted_at IS NULL
                    GROUP BY c.id, c.user_id, c.title, c.created_at, c.updated_at
                    ORDER BY c.updated_at DESC
                    LIMIT :limit
                    """
                ),
                {"user_id": self._user_id_value(user_id), "limit": max(1, min(limit, 200))},
            ).mappings().all()
        return [
            {
                "id": str(row["id"]),
                "user_id": str(row["user_id"]),
                "title": row["title"],
                "created_at": self._stringify_time(row["created_at"]),
                "updated_at": self._stringify_time(row["updated_at"]),
                "message_count": int(row["message_count"] or 0),
            }
            for row in rows
        ]

    def list_messages(self, conversation_id: str, limit: int = 200) -> list[StoredMessage]:
        with self._lock, self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, conversation_id, role, content, created_at
                    FROM agent_message
                    WHERE conversation_id = :conversation_id AND deleted_at IS NULL
                    ORDER BY created_at ASC, id ASC
                    LIMIT :limit
                    """
                ),
                {"conversation_id": self._id_value(conversation_id), "limit": max(1, min(limit, 500))},
            ).mappings().all()
        return [self._row_to_message(row) for row in rows]

    def delete_session(self, conversation_id: str) -> bool:
        try:
            conversation_key = self._id_value(conversation_id)
        except ValueError:
            return False

        now = _now_db()
        with self._lock, self.engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE agent_conversation
                    SET deleted_at = :deleted_at, delete_status = 'user_deleted', updated_at = :updated_at
                    WHERE id = :id AND deleted_at IS NULL
                    """
                ),
                {"deleted_at": now, "updated_at": now, "id": conversation_key},
            )
            return result.rowcount > 0

    def _row_to_message(self, row: Any) -> StoredMessage:
        return StoredMessage(
            id=str(row["id"]),
            conversation_id=str(row["conversation_id"]),
            role=str(row["role"]),
            content=str(row["content"]),
            route=None,
            latency_ms=None,
            created_at=self._stringify_time(row["created_at"]),
        )

    def _id_value(self, value: str | int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid bigint id: {value}") from exc

    def _user_id_value(self, value: str | int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _stringify_time(self, value: Any) -> str:
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return str(value)


@lru_cache(maxsize=1)
def get_conversation_store() -> ConversationStore:
    return ConversationStore()
