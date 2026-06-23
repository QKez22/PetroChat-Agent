"""NL2SQL 端到端胶水函数 —— 生成 → 校验 → 执行 → 结果。

这是 SQL Agent 的"单步同步版本"，给 ReAct 工具直接调用。
Step 4.5 会基于此拆成 LangGraph 子图（schema_retrieve / sql_generate / sql_validate / sql_execute）
以获得更细粒度的 trace 与错误回流。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from loguru import logger

from .executor import execute_sql
from .generator import generate_sql
from .validator import validate_sql


@dataclass
class Nl2SqlResult:
    ok: bool
    stage: str = ""           # 失败时定位是哪一步：generate / validate / execute
    sql: str = ""
    reasoning: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def nl2sql(question: str) -> Nl2SqlResult:
    """单步执行 NL2SQL 全链路。"""
    # 1) 生成
    try:
        plan = generate_sql(question)
    except Exception as e:
        logger.exception("generate 阶段失败")
        return Nl2SqlResult(ok=False, stage="generate", error=str(e))

    # 2) 校验 + LIMIT 注入
    v = validate_sql(plan.sql)
    if not v.ok:
        return Nl2SqlResult(
            ok=False, stage="validate",
            sql=plan.sql, reasoning=plan.reasoning, error=v.reason,
        )

    # 3) 执行
    r = execute_sql(v.sql)
    if not r.ok:
        return Nl2SqlResult(
            ok=False, stage="execute",
            sql=r.sql_executed, reasoning=plan.reasoning, error=r.error,
        )

    return Nl2SqlResult(
        ok=True, stage="ok",
        sql=r.sql_executed,
        reasoning=plan.reasoning,
        columns=r.columns,
        rows=r.rows,
        row_count=r.row_count,
    )
