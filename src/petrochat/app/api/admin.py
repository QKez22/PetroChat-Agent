"""Admin observability API.

This module exposes read-only operational summaries for the Vue admin console.
It reads application tables in MySQL and intentionally returns truncated
summaries rather than full prompts, SQL text, retrieved chunks, or tool output.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from ..core.models import AuthUser
from ..sql.engine import get_engine
from .auth import require_admin, resolve_auth_user

router = APIRouter(prefix="/api/admin", tags=["admin"])

CurrentUserDep = Annotated[AuthUser, Depends(resolve_auth_user)]


def _require_admin(user: CurrentUserDep) -> AuthUser:
    return require_admin(user)


AdminUserDep = Annotated[AuthUser, Depends(_require_admin)]


def _limit(value: int, maximum: int = 200) -> int:
    return max(1, min(value, maximum))


def _time(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value or "")


def _clip(value: Any, limit: int = 120) -> str:
    text_value = " ".join(str(value or "").split())
    if len(text_value) <= limit:
        return text_value
    return f"{text_value[:max(limit - 3, 0)]}..."


def _is_sqlite() -> bool:
    return get_engine().dialect.name == "sqlite"


def _summary_sql() -> str:
    if _is_sqlite():
        return """
        SELECT
            (SELECT COUNT(*) FROM agent_conversation WHERE deleted_at IS NULL) AS conversation_count,
            (SELECT COUNT(*) FROM agent_message WHERE deleted_at IS NULL) AS message_count,
            (SELECT COUNT(*) FROM agent_tool_log) AS tool_log_count,
            (SELECT COUNT(*) FROM agent_audit_log) AS audit_log_count,
            (SELECT COUNT(DISTINCT user_id) FROM agent_conversation WHERE deleted_at IS NULL) AS active_user_count
        """
    return """
    SELECT
        (SELECT COUNT(*) FROM agent_conversation WHERE deleted_at IS NULL) AS conversation_count,
        (SELECT COUNT(*) FROM agent_message WHERE deleted_at IS NULL) AS message_count,
        (SELECT COUNT(*) FROM agent_tool_log) AS tool_log_count,
        (SELECT COUNT(*) FROM agent_audit_log) AS audit_log_count,
        (SELECT COUNT(DISTINCT user_id) FROM agent_conversation WHERE deleted_at IS NULL) AS active_user_count
    """


@router.get("/overview", summary="管理员观测摘要")
async def admin_overview(_: AdminUserDep) -> dict[str, Any]:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text(_summary_sql())).mappings().first() or {}
    return {
        "conversationCount": int(row.get("conversation_count") or 0),
        "messageCount": int(row.get("message_count") or 0),
        "toolLogCount": int(row.get("tool_log_count") or 0),
        "auditLogCount": int(row.get("audit_log_count") or 0),
        "activeUserCount": int(row.get("active_user_count") or 0),
        "source": "mysql",
        "privacyNote": "仅返回聚合数量和截断摘要，不返回完整问题、SQL、检索片段或工具输出。",
    }


@router.get("/conversations", summary="管理员查看会话摘要")
async def admin_conversations(
    _: AdminUserDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT c.id, c.user_id, c.title, c.created_at, c.updated_at,
                       c.delete_status, c.retention_policy,
                       COUNT(m.id) AS message_count,
                       MAX(m.created_at) AS last_message_at
                FROM agent_conversation c
                LEFT JOIN agent_message m
                    ON m.conversation_id = c.id AND m.deleted_at IS NULL
                WHERE c.deleted_at IS NULL
                GROUP BY c.id, c.user_id, c.title, c.created_at, c.updated_at,
                         c.delete_status, c.retention_policy
                ORDER BY c.updated_at DESC
                LIMIT :limit
                """
            ),
            {"limit": _limit(limit)},
        ).mappings().all()
    return [
        {
            "id": str(row["id"]),
            "userId": str(row["user_id"]),
            "title": row["title"] or "",
            "createdAt": _time(row["created_at"]),
            "updatedAt": _time(row["updated_at"]),
            "lastMessageAt": _time(row["last_message_at"]),
            "messageCount": int(row["message_count"] or 0),
            "deleteStatus": row["delete_status"] or "active",
            "retentionPolicy": row["retention_policy"] or "",
        }
        for row in rows
    ]


@router.get("/tool-logs", summary="管理员查看工具调用摘要")
async def admin_tool_logs(
    _: AdminUserDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, conversation_id, user_id, tool_name,
                       input_summary, output_summary, status, error_message,
                       created_at, expires_at
                FROM agent_tool_log
                ORDER BY created_at DESC, id DESC
                LIMIT :limit
                """
            ),
            {"limit": _limit(limit)},
        ).mappings().all()
    return [
        {
            "id": str(row["id"]),
            "conversationId": str(row["conversation_id"] or ""),
            "userId": str(row["user_id"] or ""),
            "toolName": row["tool_name"] or "",
            "inputSummary": _clip(row["input_summary"], 120),
            "outputSummary": _clip(row["output_summary"], 120),
            "status": row["status"] or "",
            "errorMessage": _clip(row["error_message"], 120),
            "createdAt": _time(row["created_at"]),
            "expiresAt": _time(row["expires_at"]),
        }
        for row in rows
    ]


@router.get("/audit-logs", summary="管理员查看系统审计摘要")
async def admin_audit_logs(
    _: AdminUserDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, user_id, action_type, target_type, target_id,
                       action_detail, ip_address, created_at
                FROM agent_audit_log
                ORDER BY created_at DESC, id DESC
                LIMIT :limit
                """
            ),
            {"limit": _limit(limit)},
        ).mappings().all()
    return [
        {
            "id": str(row["id"]),
            "userId": str(row["user_id"] or ""),
            "actionType": row["action_type"] or "",
            "targetType": row["target_type"] or "",
            "targetId": row["target_id"] or "",
            "actionDetail": _clip(row["action_detail"], 160),
            "ipAddress": row["ip_address"] or "",
            "createdAt": _time(row["created_at"]),
        }
        for row in rows
    ]
