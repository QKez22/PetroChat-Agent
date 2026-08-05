"""NL2SQL 端到端胶水函数 —— 生成 → 校验 → 执行 → 结果。

这是 SQL Agent 的"单步同步版本"，给 ReAct 工具直接调用。
Step 4.5 会基于此拆成 LangGraph 子图（schema_retrieve / sql_generate / sql_validate / sql_execute）
以获得更细粒度的 trace 与错误回流。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from loguru import logger

from ..core.config import get_settings
from .executor import execute_sql
from .generator import SqlPlan, generate_sql, repair_sql
from .schema_narrowing import SchemaSelection, select_relevant_schema
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
    pipeline_mode: str = "legacy"
    schema_tables: list[str] = field(default_factory=list)
    schema_table_count: int = 0
    schema_total_table_count: int = 0
    schema_column_count: int = 0
    schema_total_column_count: int = 0
    schema_narrowing_reason: str = ""
    repair_attempted: bool = False
    repair_succeeded: bool = False
    repair_error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def nl2sql(question: str) -> Nl2SqlResult:
    """单步执行 NL2SQL 全链路。"""
    mode = get_settings().sql_pipeline_mode
    if mode == "optimized":
        return _nl2sql_optimized(question)
    return _nl2sql_legacy(question)


def _nl2sql_legacy(question: str) -> Nl2SqlResult:
    settings = get_settings()
    metadata = {
        "pipeline_mode": "legacy",
        "schema_tables": settings.mysql_whitelist,
        "schema_table_count": len(settings.mysql_whitelist),
        "schema_total_table_count": len(settings.mysql_whitelist),
        "schema_column_count": 0,
        "schema_total_column_count": 0,
        "schema_narrowing_reason": "full_whitelist_schema",
    }
    try:
        plan = generate_sql(question)
    except Exception as e:
        logger.exception("generate 阶段失败")
        return Nl2SqlResult(ok=False, stage="generate", error=str(e), **metadata)

    return _validate_and_execute(plan, metadata)


def _nl2sql_optimized(question: str) -> Nl2SqlResult:
    settings = get_settings()
    try:
        selection = select_relevant_schema(question)
    except Exception as e:
        logger.exception("schema narrowing 阶段失败")
        return Nl2SqlResult(ok=False, stage="schema", error=str(e), pipeline_mode="optimized")

    metadata = _selection_metadata(selection)
    try:
        plan = generate_sql(question, schema_md=selection.schema_md)
    except Exception as e:
        logger.exception("generate 阶段失败")
        return Nl2SqlResult(ok=False, stage="generate", error=str(e), **metadata)

    v = validate_sql(plan.sql)
    repair_attempted = False
    repair_succeeded = False
    repair_error = ""

    if not v.ok and settings.sql_repair_max_attempts > 0:
        repair_attempted = True
        first_error = v.reason
        try:
            repaired_plan = repair_sql(
                question=question,
                invalid_sql=plan.sql,
                validation_error=first_error,
                schema_md=selection.schema_md,
            )
            repaired_validation = validate_sql(repaired_plan.sql)
            plan = repaired_plan
            v = repaired_validation
            repair_succeeded = repaired_validation.ok
            if not repaired_validation.ok:
                repair_error = f"初次校验错误：{first_error}；修复后错误：{repaired_validation.reason}"
        except Exception as e:
            logger.exception("repair 阶段失败")
            repair_error = f"初次校验错误：{first_error}；修复调用失败：{e}"

    metadata.update({
        "repair_attempted": repair_attempted,
        "repair_succeeded": repair_succeeded,
        "repair_error": repair_error,
    })
    return _validate_and_execute(
        plan,
        metadata,
        prevalidated_sql=v.sql if v.ok else "",
        prevalidation_error=v.reason,
        question=question,
        schema_md=selection.schema_md,
        allow_execute_repair=True,
    )


def _validate_and_execute(
    plan: SqlPlan,
    metadata: dict[str, Any],
    *,
    prevalidated_sql: str = "",
    prevalidation_error: str = "",
    question: str = "",
    schema_md: str = "",
    allow_execute_repair: bool = False,
) -> Nl2SqlResult:
    v = validate_sql(plan.sql)
    if prevalidated_sql:
        v.sql = prevalidated_sql
        v.ok = True
    elif prevalidation_error:
        v.reason = prevalidation_error

    if not v.ok:
        return Nl2SqlResult(
            ok=False, stage="validate",
            sql=plan.sql, reasoning=plan.reasoning, error=metadata.get("repair_error") or v.reason,
            **metadata,
        )

    r = execute_sql(v.sql)
    if not r.ok and allow_execute_repair and not metadata.get("repair_attempted"):
        repaired = _repair_after_execute_error(
            question=question,
            plan=plan,
            execute_error=r.error,
            schema_md=schema_md,
            metadata=metadata,
        )
        if repaired is not None:
            return repaired

    if not r.ok:
        return Nl2SqlResult(
            ok=False, stage="execute",
            sql=r.sql_executed, reasoning=plan.reasoning, error=r.error,
            **metadata,
        )

    return Nl2SqlResult(
        ok=True, stage="ok",
        sql=r.sql_executed,
        reasoning=plan.reasoning,
        columns=r.columns,
        rows=r.rows,
        row_count=r.row_count,
        **metadata,
    )


def _repair_after_execute_error(
    *,
    question: str,
    plan: SqlPlan,
    execute_error: str,
    schema_md: str,
    metadata: dict[str, Any],
) -> Nl2SqlResult | None:
    if get_settings().sql_repair_max_attempts <= 0:
        return None

    repair_metadata = dict(metadata)
    repair_metadata["repair_attempted"] = True
    try:
        repaired_plan = repair_sql(
            question=question,
            invalid_sql=plan.sql,
            validation_error=f"SQL 执行失败：{execute_error}",
            schema_md=schema_md,
        )
    except Exception as e:
        logger.exception("execute repair 阶段失败")
        repair_metadata["repair_error"] = f"执行错误：{execute_error}；修复调用失败：{e}"
        return Nl2SqlResult(
            ok=False,
            stage="execute",
            sql=plan.sql,
            reasoning=plan.reasoning,
            error=repair_metadata["repair_error"],
            **repair_metadata,
        )

    validation = validate_sql(repaired_plan.sql)
    if not validation.ok:
        repair_metadata["repair_error"] = (
            f"执行错误：{execute_error}；执行修复后校验错误：{validation.reason}"
        )
        return Nl2SqlResult(
            ok=False,
            stage="validate",
            sql=repaired_plan.sql,
            reasoning=repaired_plan.reasoning,
            error=repair_metadata["repair_error"],
            **repair_metadata,
        )

    repaired_result = execute_sql(validation.sql)
    if not repaired_result.ok:
        repair_metadata["repair_error"] = (
            f"执行错误：{execute_error}；执行修复后仍失败：{repaired_result.error}"
        )
        return Nl2SqlResult(
            ok=False,
            stage="execute",
            sql=repaired_result.sql_executed,
            reasoning=repaired_plan.reasoning,
            error=repair_metadata["repair_error"],
            **repair_metadata,
        )

    repair_metadata["repair_succeeded"] = True
    repair_metadata["repair_error"] = ""
    return Nl2SqlResult(
        ok=True,
        stage="ok",
        sql=repaired_result.sql_executed,
        reasoning=repaired_plan.reasoning,
        columns=repaired_result.columns,
        rows=repaired_result.rows,
        row_count=repaired_result.row_count,
        **repair_metadata,
    )


def _selection_metadata(selection: SchemaSelection) -> dict[str, Any]:
    return {
        "pipeline_mode": "optimized",
        "schema_tables": selection.tables,
        "schema_table_count": selection.selected_table_count,
        "schema_total_table_count": selection.total_table_count,
        "schema_column_count": selection.selected_column_count,
        "schema_total_column_count": selection.total_column_count,
        "schema_narrowing_reason": selection.reason,
    }
