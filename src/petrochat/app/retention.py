"""Retention cleanup service for application-owned MySQL tables.

The cleanup is intentionally conservative:
- dry-run by default;
- conversations are soft-deleted first, then physically removed after recovery days;
- audit logs are kept longer than operational logs;
- expired long-term memories are disabled, not physically deleted.
"""

from __future__ import annotations

import json
import random
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from .sql.engine import get_engine

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


def _db_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


@dataclass(frozen=True)
class RetentionConfig:
    conversation_days: int = 180
    conversation_recovery_days: int = 30
    tool_log_days: int = 365
    retrieval_context_days: int = 90
    audit_log_days: int = 1095
    temp_file_days: int = 30


@dataclass
class RetentionCleanupResult:
    dry_run: bool
    generated_at: str
    cutoffs: dict[str, str]
    affected: dict[str, int] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    audit_log_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RetentionCleanupService:
    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or get_engine()

    def run(
        self,
        *,
        dry_run: bool = True,
        now: datetime | None = None,
        config: RetentionConfig | None = None,
        actor_id: str | None = None,
        reason: str = "scheduled retention cleanup",
    ) -> RetentionCleanupResult:
        config = config or RetentionConfig()
        now = now or datetime.now(UTC)
        cutoffs = {
            "conversation_soft_delete_before": _db_time(now - timedelta(days=config.conversation_days)),
            "conversation_physical_delete_before": _db_time(
                now - timedelta(days=config.conversation_recovery_days)
            ),
            "tool_log_delete_before": _db_time(now - timedelta(days=config.tool_log_days)),
            "retrieval_context_delete_before": _db_time(
                now - timedelta(days=config.retrieval_context_days)
            ),
            "audit_log_delete_before": _db_time(now - timedelta(days=config.audit_log_days)),
            "memory_expire_before": _db_time(now),
        }
        result = RetentionCleanupResult(
            dry_run=dry_run,
            generated_at=_db_time(now),
            cutoffs=cutoffs,
        )

        inspector = inspect(self.engine)
        existing_tables = set(inspector.get_table_names())
        with self.engine.begin() as conn:
            self._cleanup_conversations(conn, existing_tables, result, now, cutoffs, dry_run)
            self._cleanup_tool_logs(conn, existing_tables, result, cutoffs, dry_run)
            self._cleanup_retrieval_logs(conn, existing_tables, result, cutoffs, dry_run)
            self._cleanup_expired_memories(conn, existing_tables, result, now, cutoffs, dry_run)
            self._cleanup_audit_logs(conn, existing_tables, result, cutoffs, dry_run)
            if not dry_run:
                result.audit_log_id = self._write_audit_log(
                    conn,
                    existing_tables,
                    actor_id=actor_id,
                    reason=reason,
                    result=result,
                )

        return result

    def _cleanup_conversations(
        self,
        conn: Any,
        tables: set[str],
        result: RetentionCleanupResult,
        now: datetime,
        cutoffs: dict[str, str],
        dry_run: bool,
    ) -> None:
        required = {"agent_conversation", "agent_message"}
        if not required.issubset(tables):
            result.skipped.append("conversation tables missing")
            return

        soft_params = {
            "now": _db_time(now),
            "cutoff": cutoffs["conversation_soft_delete_before"],
        }
        soft_where = """
            deleted_at IS NULL
            AND (
                (expires_at IS NOT NULL AND expires_at <= :now)
                OR updated_at < :cutoff
            )
        """
        result.affected["conversations_soft_deleted"] = self._count(
            conn,
            f"SELECT COUNT(*) FROM agent_conversation WHERE {soft_where}",
            soft_params,
        )
        if not dry_run and result.affected["conversations_soft_deleted"]:
            conn.execute(
                text(
                    f"""
                    UPDATE agent_conversation
                    SET deleted_at = :now,
                        delete_status = 'retention_expired',
                        updated_at = :now
                    WHERE {soft_where}
                    """
                ),
                soft_params,
            )

        physical_params = {"cutoff": cutoffs["conversation_physical_delete_before"]}
        physical_where = "deleted_at IS NOT NULL AND deleted_at < :cutoff"
        result.affected["conversations_physical_deleted"] = self._count(
            conn,
            f"SELECT COUNT(*) FROM agent_conversation WHERE {physical_where}",
            physical_params,
        )
        result.affected["messages_physical_deleted"] = self._count(
            conn,
            """
            SELECT COUNT(*)
            FROM agent_message
            WHERE conversation_id IN (
                SELECT id FROM agent_conversation
                WHERE deleted_at IS NOT NULL AND deleted_at < :cutoff
            )
            """,
            physical_params,
        )
        if not dry_run and result.affected["conversations_physical_deleted"]:
            conn.execute(
                text(
                    """
                    DELETE FROM agent_message
                    WHERE conversation_id IN (
                        SELECT id FROM agent_conversation
                        WHERE deleted_at IS NOT NULL AND deleted_at < :cutoff
                    )
                    """
                ),
                physical_params,
            )
            conn.execute(
                text(f"DELETE FROM agent_conversation WHERE {physical_where}"),
                physical_params,
            )

    def _cleanup_tool_logs(
        self,
        conn: Any,
        tables: set[str],
        result: RetentionCleanupResult,
        cutoffs: dict[str, str],
        dry_run: bool,
    ) -> None:
        if "agent_tool_log" not in tables:
            result.skipped.append("agent_tool_log missing")
            return
        params = {
            "now": cutoffs["memory_expire_before"],
            "cutoff": cutoffs["tool_log_delete_before"],
        }
        where = """
            (expires_at IS NOT NULL AND expires_at <= :now)
            OR created_at < :cutoff
        """
        result.affected["tool_logs_deleted"] = self._count(
            conn,
            f"SELECT COUNT(*) FROM agent_tool_log WHERE {where}",
            params,
        )
        if not dry_run and result.affected["tool_logs_deleted"]:
            conn.execute(text(f"DELETE FROM agent_tool_log WHERE {where}"), params)

    def _cleanup_retrieval_logs(
        self,
        conn: Any,
        tables: set[str],
        result: RetentionCleanupResult,
        cutoffs: dict[str, str],
        dry_run: bool,
    ) -> None:
        if "agent_retrieval_log" not in tables:
            result.skipped.append("agent_retrieval_log missing")
            return
        params = {
            "now": cutoffs["memory_expire_before"],
            "cutoff": cutoffs["retrieval_context_delete_before"],
        }
        where = """
            (expires_at IS NOT NULL AND expires_at <= :now)
            OR created_at < :cutoff
        """
        result.affected["retrieval_logs_deleted"] = self._count(
            conn,
            f"SELECT COUNT(*) FROM agent_retrieval_log WHERE {where}",
            params,
        )
        if not dry_run and result.affected["retrieval_logs_deleted"]:
            conn.execute(text(f"DELETE FROM agent_retrieval_log WHERE {where}"), params)

    def _cleanup_expired_memories(
        self,
        conn: Any,
        tables: set[str],
        result: RetentionCleanupResult,
        now: datetime,
        cutoffs: dict[str, str],
        dry_run: bool,
    ) -> None:
        if "user_memory" not in tables:
            result.skipped.append("user_memory missing")
            return
        params = {"now": cutoffs["memory_expire_before"]}
        rows = conn.execute(
            text(
                """
                SELECT id, user_id, status
                FROM user_memory
                WHERE status = 'active'
                  AND expires_at IS NOT NULL
                  AND expires_at <= :now
                """
            ),
            params,
        ).mappings().all()
        result.affected["memories_disabled"] = len(rows)
        if dry_run or not rows:
            return

        ids = [int(row["id"]) for row in rows]
        conn.execute(
            text(
                """
                UPDATE user_memory
                SET status = 'disabled', updated_at = :now
                WHERE status = 'active'
                  AND expires_at IS NOT NULL
                  AND expires_at <= :now
                """
            ),
            {"now": _db_time(now)},
        )

        if "memory_event" not in tables:
            result.skipped.append("memory_event missing")
            return
        for row in rows:
            conn.execute(
                text(
                    """
                    INSERT INTO memory_event(
                        id, memory_id, user_id, event_type, actor_id, reason,
                        payload_json, created_at
                    )
                    VALUES (
                        :id, :memory_id, :user_id, 'disabled', NULL,
                        'retention expired memory',
                        :payload_json, :created_at
                    )
                    """
                ),
                {
                    "id": _new_bigint_id(),
                    "memory_id": int(row["id"]),
                    "user_id": int(row["user_id"]),
                    "payload_json": json.dumps(
                        {"previous_status": row["status"], "status": "disabled"},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    "created_at": _db_time(now),
                },
            )
        result.affected["memory_events_inserted"] = len(ids)

    def _cleanup_audit_logs(
        self,
        conn: Any,
        tables: set[str],
        result: RetentionCleanupResult,
        cutoffs: dict[str, str],
        dry_run: bool,
    ) -> None:
        if "agent_audit_log" not in tables:
            result.skipped.append("agent_audit_log missing")
            return
        params = {"cutoff": cutoffs["audit_log_delete_before"]}
        where = "created_at < :cutoff"
        result.affected["audit_logs_deleted"] = self._count(
            conn,
            f"SELECT COUNT(*) FROM agent_audit_log WHERE {where}",
            params,
        )
        if not dry_run and result.affected["audit_logs_deleted"]:
            conn.execute(text(f"DELETE FROM agent_audit_log WHERE {where}"), params)

    def _write_audit_log(
        self,
        conn: Any,
        tables: set[str],
        *,
        actor_id: str | None,
        reason: str,
        result: RetentionCleanupResult,
    ) -> str | None:
        if "agent_audit_log" not in tables:
            result.skipped.append("agent_audit_log missing for cleanup audit")
            return None
        audit_id = _new_bigint_id()
        detail = {
            "reason": reason,
            "dry_run": result.dry_run,
            "cutoffs": result.cutoffs,
            "affected": result.affected,
            "skipped": result.skipped,
        }
        conn.execute(
            text(
                """
                INSERT INTO agent_audit_log(
                    id, user_id, action_type, target_type, target_id,
                    action_detail, ip_address, created_at
                )
                VALUES (
                    :id, :user_id, 'retention_cleanup', 'system', 'retention',
                    :action_detail, 'system', :created_at
                )
                """
            ),
            {
                "id": audit_id,
                "user_id": int(actor_id) if actor_id else None,
                "action_detail": json.dumps(detail, ensure_ascii=False, separators=(",", ":")),
                "created_at": result.generated_at,
            },
        )
        return str(audit_id)

    def _count(self, conn: Any, statement: str, params: dict[str, Any]) -> int:
        return int(conn.execute(text(statement), params).scalar() or 0)
