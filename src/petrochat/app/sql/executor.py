"""SQL 执行 —— pandas DataFrame 返回 + MySQL 原生超时。

为什么用 MAX_EXECUTION_TIME hint 而不是 SQLAlchemy 层 timeout：
  SQLAlchemy 的 statement_timeout 在 MySQL driver 下是软超时，慢查询照样烧 CPU。
  MySQL 8 的 MAX_EXECUTION_TIME(ms) 优化器 hint 是硬超时，过期内核杀线程。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy import text

from ..core.config import get_settings
from .engine import get_engine


@dataclass
class ExecutionResult:
    ok: bool
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    error: str = ""
    sql_executed: str = ""


# 用于在第一个 SELECT 后注入 MAX_EXECUTION_TIME hint
_SELECT_PAT = re.compile(r"^(\s*SELECT)\s", re.IGNORECASE)


def _inject_timeout(sql: str, timeout_seconds: int) -> str:
    """把 MySQL hint 注入到 SQL 第一个 SELECT 关键字之后。

    若 SQL 已含 /*+ ... */ hint，不重复注入。
    """
    if "MAX_EXECUTION_TIME" in sql.upper():
        return sql
    hint = f"/*+ MAX_EXECUTION_TIME({timeout_seconds * 1000}) */"
    return _SELECT_PAT.sub(r"\1 " + hint, sql, count=1)


def execute_sql(sql: str, timeout_seconds: int | None = None) -> ExecutionResult:
    """执行已校验的 SELECT，返回 DataFrame 兼容的字典列表。"""
    s = get_settings()
    timeout = timeout_seconds or s.sql_timeout_seconds
    executed = _inject_timeout(sql, timeout)

    engine = get_engine()
    try:
        with engine.connect() as conn:
            # 多一层只读保护
            conn.execute(text("SET SESSION TRANSACTION READ ONLY"))
            df = pd.read_sql(text(executed), conn)
        return ExecutionResult(
            ok=True,
            columns=df.columns.tolist(),
            rows=df.to_dict(orient="records"),
            row_count=len(df),
            sql_executed=executed,
        )
    except Exception as e:
        logger.exception("execute_sql 失败: {}", e)
        return ExecutionResult(
            ok=False, error=str(e), sql_executed=executed,
        )
