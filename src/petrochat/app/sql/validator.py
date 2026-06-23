"""SQL 安全校验 —— 用 sqlglot AST 解析，不靠正则。

为什么必须 AST：
  正则识别 'SELECT' 起手就误判 'SELECT 1; DELETE FROM t' 这种串。
  AST 能严格区分顶级语句类型，且统计任何嵌套的 DDL/DML 节点。

校验项：
  1. 顶级必须是 SELECT
  2. AST 中不能出现 INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE
  3. 引用的表不能落到系统库（information_schema / mysql / performance_schema / sys）
  4. 没有显式 LIMIT 时自动注入；过大 LIMIT 强制下钳
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import expressions as exp

from ..core.config import get_settings

# 系统库黑名单（不允许查询）
_FORBIDDEN_DBS = {"information_schema", "mysql", "performance_schema", "sys"}

# 危险节点类型（出现即拒）
_FORBIDDEN_NODE_TYPES = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.AlterColumn,
    exp.AlterTable, exp.Create, exp.TruncateTable,
)


@dataclass
class ValidationResult:
    ok: bool
    sql: str          # 归一化（已注入 LIMIT）后的 SQL
    reason: str = ""  # 不通过原因


def validate_sql(raw_sql: str) -> ValidationResult:
    """校验并改写 SQL：返回归一化后的可执行 SQL。"""
    raw_sql = raw_sql.strip().rstrip(";").strip()
    if not raw_sql:
        return ValidationResult(ok=False, sql="", reason="空 SQL")

    # 1) 解析（MySQL 方言）。多语句会抛 ParseError
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

    # 2) 顶级必须 SELECT（含 CTE 形式 WITH ... SELECT 也包装为 Select）
    if not isinstance(parsed, exp.Select):
        return ValidationResult(
            ok=False, sql=raw_sql,
            reason=f"只允许 SELECT 语句，收到: {type(parsed).__name__}",
        )

    # 3) AST 内任何 DDL/DML 节点都拒
    for node in parsed.walk():
        if isinstance(node, _FORBIDDEN_NODE_TYPES):
            return ValidationResult(
                ok=False, sql=raw_sql,
                reason=f"含禁止操作: {type(node).__name__}",
            )

    # 4) 表名不能落到系统库
    for tbl in parsed.find_all(exp.Table):
        db = (tbl.db or "").lower()
        if db in _FORBIDDEN_DBS:
            return ValidationResult(
                ok=False, sql=raw_sql, reason=f"禁止访问系统库: {db}",
            )

    # 5) LIMIT 注入 / 下钳
    settings = get_settings()
    cap = settings.sql_default_limit
    current_limit = parsed.args.get("limit")
    if current_limit is None:
        parsed = parsed.limit(cap)
    else:
        # 取出现有 limit 的数值；超出上限就替换
        lit = current_limit.expression
        try:
            val = int(getattr(lit, "this", 0))
            if val <= 0 or val > cap:
                parsed = parsed.limit(cap)
        except (TypeError, ValueError):
            parsed = parsed.limit(cap)

    return ValidationResult(ok=True, sql=parsed.sql(dialect="mysql"))
