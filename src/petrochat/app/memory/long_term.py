"""MySQL-backed long-term memory store.

Phase 6.1 creates an explicit, auditable memory data model. Table creation is
managed by SQL scripts, not by runtime code.
"""

from __future__ import annotations

import json
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Literal

from sqlalchemy import text
UTC = timezone.utc  # Py3.10 兼容（3.11+ datetime.UTC 等价）
from sqlalchemy.engine import Engine

from ..sql.engine import get_app_engine as get_engine

MemoryStatus = Literal["active", "disabled", "deleted"]
MemoryEventType = Literal["created", "updated", "disabled", "deleted", "accessed"]


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


def _json_dumps(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False, separators=(",", ":"))


def _json_loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


@dataclass(frozen=True)
class MemoryItem:
    id: str
    user_id: str
    memory_type: str
    content: str
    source: str
    confidence: float
    status: MemoryStatus
    metadata: dict[str, Any]
    created_at: str
    updated_at: str
    expires_at: str | None = None


@dataclass(frozen=True)
class MemoryEvent:
    id: str
    memory_id: str
    user_id: str
    event_type: MemoryEventType
    actor_id: str | None
    reason: str
    payload: dict[str, Any]
    created_at: str


class LongTermMemoryStore:
    """Durable memory store for user preferences and reusable business context."""

    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or get_engine()
        self._lock = threading.RLock()

    def create_memory(
        self,
        *,
        user_id: str,
        memory_type: str,
        content: str,
        source: str = "manual",
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
        actor_id: str | None = None,
        expires_at: str | None = None,
    ) -> MemoryItem:
        user_id = user_id.strip()
        memory_type = memory_type.strip()
        content = content.strip()
        if not user_id:
            raise ValueError("user_id is required")
        if not memory_type:
            raise ValueError("memory_type is required")
        if not content:
            raise ValueError("content is required")
        if confidence < 0 or confidence > 1:
            raise ValueError("confidence must be between 0 and 1")

        now = _now_db()
        item = MemoryItem(
            id=str(_new_bigint_id()),
            user_id=str(self._user_id_value(user_id)),
            memory_type=memory_type,
            content=content,
            source=source or "manual",
            confidence=confidence,
            status="active",
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )
        with self._lock, self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO user_memory(
                        id, user_id, memory_type, content, source, confidence, status,
                        metadata_json, created_at, updated_at, expires_at
                    )
                    VALUES (
                        :id, :user_id, :memory_type, :content, :source, :confidence, :status,
                        :metadata_json, :created_at, :updated_at, :expires_at
                    )
                    """
                ),
                {
                    "id": self._id_value(item.id),
                    "user_id": self._user_id_value(item.user_id),
                    "memory_type": item.memory_type,
                    "content": item.content,
                    "source": item.source,
                    "confidence": item.confidence,
                    "status": item.status,
                    "metadata_json": _json_dumps(item.metadata),
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                    "expires_at": item.expires_at,
                },
            )
            self._insert_event(
                conn,
                memory_id=item.id,
                user_id=item.user_id,
                event_type="created",
                actor_id=actor_id,
                reason="create memory",
                payload={
                    "memory_type": item.memory_type,
                    "source": item.source,
                    "confidence": item.confidence,
                },
            )
        return item

    def get_memory(self, memory_id: str) -> MemoryItem | None:
        with self._lock, self.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id, user_id, memory_type, content, source, confidence, status,
                           metadata_json, created_at, updated_at, expires_at
                    FROM user_memory
                    WHERE id = :id
                    LIMIT 1
                    """
                ),
                {"id": self._id_value(memory_id)},
            ).mappings().first()
        return self._row_to_item(row) if row else None

    def list_memories(
        self,
        *,
        user_id: str,
        status: MemoryStatus | Literal["all"] = "active",
        memory_type: str | None = None,
        q: str | None = None,
        limit: int = 50,
    ) -> list[MemoryItem]:
        clauses = ["user_id = :user_id"]
        params: dict[str, Any] = {
            "user_id": self._user_id_value(user_id),
            "limit": max(1, min(limit, 200)),
        }
        if status != "all":
            clauses.append("status = :status")
            params["status"] = status
        if memory_type:
            clauses.append("memory_type = :memory_type")
            params["memory_type"] = memory_type
        if q and q.strip():
            clauses.append(
                """
                (
                    content LIKE :q
                    OR memory_type LIKE :q
                    OR source LIKE :q
                    OR metadata_json LIKE :q
                )
                """
            )
            params["q"] = f"%{q.strip()}%"
        query = f"""
            SELECT id, user_id, memory_type, content, source, confidence, status,
                   metadata_json, created_at, updated_at, expires_at
            FROM user_memory
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC, id DESC
            LIMIT :limit
        """
        with self._lock, self.engine.connect() as conn:
            rows = conn.execute(text(query), params).mappings().all()
        return [self._row_to_item(row) for row in rows]

    def update_memory(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
        confidence: float | None = None,
        actor_id: str | None = None,
        reason: str = "update memory",
    ) -> MemoryItem | None:
        current = self.get_memory(memory_id)
        if current is None:
            return None
        next_content = current.content if content is None else content.strip()
        if not next_content:
            raise ValueError("content is required")
        next_confidence = current.confidence if confidence is None else confidence
        if next_confidence < 0 or next_confidence > 1:
            raise ValueError("confidence must be between 0 and 1")
        next_metadata = current.metadata if metadata is None else metadata
        now = _now_db()
        with self._lock, self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE user_memory
                    SET content = :content,
                        metadata_json = :metadata_json,
                        confidence = :confidence,
                        updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                {
                    "content": next_content,
                    "metadata_json": _json_dumps(next_metadata),
                    "confidence": next_confidence,
                    "updated_at": now,
                    "id": self._id_value(memory_id),
                },
            )
            self._insert_event(
                conn,
                memory_id=memory_id,
                user_id=current.user_id,
                event_type="updated",
                actor_id=actor_id,
                reason=reason,
                payload={"confidence": next_confidence},
            )
        return self.get_memory(memory_id)

    def disable_memory(
        self,
        memory_id: str,
        *,
        actor_id: str | None = None,
        reason: str = "disable memory",
    ) -> MemoryItem | None:
        return self._set_status(memory_id, "disabled", actor_id=actor_id, reason=reason)

    def delete_memory(
        self,
        memory_id: str,
        *,
        actor_id: str | None = None,
        reason: str = "delete memory",
    ) -> MemoryItem | None:
        return self._set_status(memory_id, "deleted", actor_id=actor_id, reason=reason)

    def list_events(self, memory_id: str, limit: int = 50) -> list[MemoryEvent]:
        with self._lock, self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, memory_id, user_id, event_type, actor_id, reason, payload_json, created_at
                    FROM memory_event
                    WHERE memory_id = :memory_id
                    ORDER BY created_at ASC, id ASC
                    LIMIT :limit
                    """
                ),
                {"memory_id": self._id_value(memory_id), "limit": max(1, min(limit, 200))},
            ).mappings().all()
        return [self._row_to_event(row) for row in rows]

    def _set_status(
        self,
        memory_id: str,
        status: Literal["disabled", "deleted"],
        *,
        actor_id: str | None,
        reason: str,
    ) -> MemoryItem | None:
        current = self.get_memory(memory_id)
        if current is None:
            return None
        now = _now_db()
        event_type: MemoryEventType = "disabled" if status == "disabled" else "deleted"
        with self._lock, self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE user_memory
                    SET status = :status, updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                {"status": status, "updated_at": now, "id": self._id_value(memory_id)},
            )
            self._insert_event(
                conn,
                memory_id=memory_id,
                user_id=current.user_id,
                event_type=event_type,
                actor_id=actor_id,
                reason=reason,
                payload={"previous_status": current.status, "status": status},
            )
        return self.get_memory(memory_id)

    def _insert_event(
        self,
        conn: Any,
        *,
        memory_id: str,
        user_id: str,
        event_type: MemoryEventType,
        actor_id: str | None,
        reason: str,
        payload: dict[str, Any] | None,
    ) -> None:
        conn.execute(
            text(
                """
                INSERT INTO memory_event(
                    id, memory_id, user_id, event_type, actor_id, reason, payload_json, created_at
                )
                VALUES (
                    :id, :memory_id, :user_id, :event_type, :actor_id,
                    :reason, :payload_json, :created_at
                )
                """
            ),
            {
                "id": _new_bigint_id(),
                "memory_id": self._id_value(memory_id),
                "user_id": self._user_id_value(user_id),
                "event_type": event_type,
                "actor_id": self._optional_id_value(actor_id),
                "reason": reason,
                "payload_json": _json_dumps(payload),
                "created_at": _now_db(),
            },
        )

    def _row_to_item(self, row: Any) -> MemoryItem:
        return MemoryItem(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            memory_type=str(row["memory_type"]),
            content=str(row["content"]),
            source=str(row["source"]),
            confidence=float(row["confidence"]),
            status=row["status"],
            metadata=_json_loads(row["metadata_json"]),
            created_at=self._stringify_time(row["created_at"]),
            updated_at=self._stringify_time(row["updated_at"]),
            expires_at=self._stringify_time(row["expires_at"]) if row["expires_at"] else None,
        )

    def _row_to_event(self, row: Any) -> MemoryEvent:
        return MemoryEvent(
            id=str(row["id"]),
            memory_id=str(row["memory_id"]),
            user_id=str(row["user_id"]),
            event_type=row["event_type"],
            actor_id=str(row["actor_id"]) if row["actor_id"] is not None else None,
            reason=str(row["reason"]),
            payload=_json_loads(row["payload_json"]),
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
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid user_id: {value}") from exc

    def _optional_id_value(self, value: str | int | None) -> int | None:
        if value is None or value == "":
            return None
        return self._id_value(value)

    def _stringify_time(self, value: Any) -> str:
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return str(value)


@lru_cache(maxsize=1)
def get_long_term_memory_store() -> LongTermMemoryStore:
    return LongTermMemoryStore()
