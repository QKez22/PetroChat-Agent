"""SQL 安全校验 —— sqlglot AST 解析。

校验项：
  1. 单语句（多语句直接拒）
  2. 顶级必须是 SELECT（含 WITH ... SELECT，sqlglot 都归类为 Select）
  3. 引用的表不能落到系统库
  4. LIMIT 自动注入 / 下钳
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import expressions as exp

from ..core.config import get_settings

_FORBIDDEN_DBS = {"information_schema", "mysql", "performance_schema", "sys"}


@dataclass
class ValidationResult:
    ok: bool
    sql: str          # 归一化（已注入 LIMIT）后的 SQL
    reason: str = ""  # 不通过原因


def validate_sql(raw_sql: str) -> ValidationResult:
    raw_sql = raw_sql.strip().rstrip(";").strip()
    if not raw_sql:
        return ValidationResult(ok=False, sql="", reason="空 SQL")

    # 1) 解析（MySQL 方言）
    try:
        statements = sqlglot.parse(raw_sql, dialect="mysql")
    except sqlglot.errors.ParseError as e:
        return ValidationResult(ok=False, sql=raw_sql, reason=f"SQL 语法错误: {e}")

    statements = [s for s in statements if s is not None]
    if not statements:
        return ValidationResult(ok=False, sql=raw_sql, reason="未解析出任何语句")
    if len(statements) > 1:
        return ValidationResult(ok=False, sql=raw_sql, reason="禁止多语句执行")

    parsed = statements[0]

    # 2) 顶级必须 SELECT
    # MySQL 的 SELECT 语法不允许嵌套 DDL/DML，所以顶级类型检查就够了
    if not isinstance(parsed, exp.Select):
        return ValidationResult(
            ok=False, sql=raw_sql,
            reason=f"只允许 SELECT 语句，收到: {type(parsed).__name__}",
        )

    # 3) 表名不能落到系统库
    for tbl in parsed.find_all(exp.Table):
        db = (tbl.db or "").lower()
        if db in _FORBIDDEN_DBS:
            return ValidationResult(
                ok=False, sql=raw_sql, reason=f"禁止访问系统库: {db}",
            )
        # 也兼容 unqualified 直接命中系统库名作 schema 的情况
        name = (tbl.name or "").lower()
        if name in _FORBIDDEN_DBS:
            return ValidationResult(
                ok=False, sql=raw_sql, reason=f"禁止访问系统库: {name}",
            )

    # 4) LIMIT 注入 / 下钳
    settings = get_settings()
    cap = settings.sql_default_limit
    current_limit = parsed.args.get("limit")
    if current_limit is None:
        parsed = parsed.limit(cap)
    else:
        lit = current_limit.expression
        try:
            val = int(getattr(lit, "this", 0))
            if val <= 0 or val > cap:
                parsed = parsed.limit(cap)
        except (TypeError, ValueError):
            parsed = parsed.limit(cap)

    return ValidationResult(ok=True, sql=parsed.sql(dialect="mysql"))
