"""Schema narrowing for the optimized NL2SQL pipeline.

The selector is deterministic and cheap: it scores whitelisted table schemas
against the user question, then only exposes the most relevant schemas to the
LLM. The validator still enforces the full table whitelist after generation.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from functools import lru_cache

from loguru import logger

from ..core.config import get_settings
from .schema import dump_all_schemas, format_schemas_for_llm

_WORD_PAT = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*|\d+|[\u4e00-\u9fff]{2,}")

_DOMAIN_HINTS: dict[str, tuple[str, ...]] = {
    "affair": (
        "事务",
        "事件",
        "专业",
        "触发",
        "状态",
        "运行",
        "闭环",
        "affair",
    ),
    "affair_task": (
        "任务",
        "措施",
        "执行",
        "部门",
        "负责人",
        "完成",
        "逾期",
        "task",
        "affair_task",
    ),
}

_RELATED_TABLES: dict[str, tuple[str, ...]] = {
    "affair": ("affair_task",),
    "affair_task": ("affair",),
}

_ALWAYS_KEEP_COLUMNS: dict[str, tuple[str, ...]] = {
    "affair": (
        "id",
        "affair_id",
        "affair_name",
        "specialty",
        "area",
        "frequency",
        "trigger_status",
        "execution_department",
        "execution_role",
        "trigger_time",
        "deadline",
        "ticket_flag",
        "check_flag",
    ),
    "affair_task": (
        "id",
        "task_id",
        "associated_affair_id",
        "affair_name",
        "task_name",
        "task_properties",
        "specialty",
        "area",
        "frequency",
        "operation_department",
        "execution_role",
        "body_equipment_name",
        "body_equipment_code",
        "technical_id_code",
        "task_equipment_name",
        "task_equipment_code",
        "report_time",
        "upload_auto",
    ),
}

_COLUMN_HINTS: dict[str, tuple[str, ...]] = {
    "ticket_flag": ("开票", "票", "作业票"),
    "check_flag": ("检查表", "线上检查", "表单"),
    "frequency": ("频次", "频率", "周期"),
    "execution_department": ("执行部门", "运行部", "部门"),
    "operation_department": ("执行部门", "运行部", "部门"),
    "technical_id_code": ("位号", "设备位号"),
    "body_equipment_name": ("设备", "设备名称", "主体设备"),
    "body_equipment_code": ("设备", "设备编码", "主体设备"),
    "task_equipment_name": ("任务设备", "设备名称"),
    "task_equipment_code": ("任务设备", "设备编码"),
    "task_name": ("任务", "措施", "巡检", "检修"),
    "task_properties": ("任务属性", "属性"),
    "trigger_status": ("运行", "停止", "删除", "状态"),
    "deadline": ("截止", "到期", "逾期"),
    "report_time": ("提报", "添加时间", "时间"),
    "upload_auto": ("上传", "手动上传"),
}


@dataclass(frozen=True)
class SchemaSelection:
    """Selected schema context for one NL2SQL request."""

    tables: list[str]
    schema_md: str
    total_table_count: int
    reason: str
    selected_column_count: int = 0
    total_column_count: int = 0

    @property
    def selected_table_count(self) -> int:
        return len(self.tables)


def select_relevant_schema(
    question: str,
    max_tables: int | None = None,
    max_columns_per_table: int | None = None,
) -> SchemaSelection:
    """Pick relevant table schemas for the current question.

    If no table gets a meaningful score, the function falls back to all
    whitelisted schemas, capped by ``max_tables`` only when it is positive.
    """

    settings = get_settings()
    table_limit = max_tables if max_tables is not None else settings.sql_schema_narrowing_max_tables
    column_limit = (
        max_columns_per_table
        if max_columns_per_table is not None
        else settings.sql_schema_narrowing_max_columns_per_table
    )
    schemas = _cached_all_schemas()
    if not schemas:
        return SchemaSelection(tables=[], schema_md="", total_table_count=0, reason="no_schema")

    question_text = _normalise(question)
    question_tokens = set(_tokens(question_text))
    scored: list[tuple[int, int, dict]] = []
    for index, schema in enumerate(schemas):
        scored.append((_score_schema(schema, question_text, question_tokens), -index, schema))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    positive = [schema for score, _, schema in scored if score > 0]
    selected = positive or [schema for _, _, schema in scored]

    if table_limit and table_limit > 0:
        selected = selected[: min(table_limit, len(selected))]

    selected = _expand_related_tables(selected, schemas, table_limit)
    narrowed = [
        _narrow_columns(schema, question_text, question_tokens, column_limit)
        for schema in selected
    ]

    selected_names = [str(schema.get("table_name", "")) for schema in narrowed]
    total_columns = sum(len(schema.get("columns") or []) for schema in schemas)
    selected_columns = sum(len(schema.get("columns") or []) for schema in narrowed)
    reason = (
        f"matched_tables={len(positive)}, selected_tables={len(selected_names)}, "
        f"selected_columns={selected_columns}, total_columns={total_columns}, "
        f"max_tables={table_limit}, max_columns_per_table={column_limit}, cache=on"
    )
    logger.info("schema narrowing: {} -> {} cols={}", question[:80], selected_names, selected_columns)
    return SchemaSelection(
        tables=selected_names,
        schema_md=_format_narrowed_schemas(narrowed),
        total_table_count=len(schemas),
        reason=reason,
        selected_column_count=selected_columns,
        total_column_count=total_columns,
    )


@lru_cache(maxsize=1)
def _cached_all_schemas() -> list[dict]:
    """Cache schema/enums in-process to avoid repeated information_schema scans."""

    return dump_all_schemas()


def clear_schema_narrowing_cache() -> None:
    _cached_all_schemas.cache_clear()


def _score_schema(schema: dict, question_text: str, question_tokens: set[str]) -> int:
    table = str(schema.get("table_name") or "").lower()
    schema_text = _normalise(_schema_search_text(schema))
    score = 0

    if table and table in question_text:
        score += 8

    for hint in _DOMAIN_HINTS.get(table, ()):
        if hint.lower() in question_text:
            score += 5

    for token in question_tokens:
        if token and token in schema_text:
            score += 2

    # Column names and comments are strong signals for business filters.
    for column in schema.get("columns") or []:
        name = str(column.get("COLUMN_NAME") or "").lower()
        comment = _normalise(column.get("COLUMN_COMMENT") or "")
        if name and name in question_text:
            score += 4
        if comment and any(token in comment for token in question_tokens):
            score += 3

    return score


def _expand_related_tables(selected: list[dict], schemas: list[dict], limit: int | None) -> list[dict]:
    if limit is not None and limit <= 1:
        return selected

    by_name = {str(schema.get("table_name") or "").lower(): schema for schema in schemas}
    selected_names = [str(schema.get("table_name") or "").lower() for schema in selected]
    expanded = list(selected)
    seen = set(selected_names)

    for name in selected_names:
        for related in _RELATED_TABLES.get(name, ()):
            if related in by_name and related not in seen:
                expanded.append(by_name[related])
                seen.add(related)

    if limit and limit > 0:
        expanded = expanded[: min(limit, len(expanded))]
    return expanded


def _narrow_columns(
    schema: dict,
    question_text: str,
    question_tokens: set[str],
    max_columns: int | None,
) -> dict:
    columns = list(schema.get("columns") or [])
    if not max_columns or max_columns <= 0 or len(columns) <= max_columns:
        return copy.deepcopy(schema)

    table = str(schema.get("table_name") or "").lower()
    scored: list[tuple[int, int, dict]] = []
    for index, column in enumerate(columns):
        scored.append((_score_column(table, column, question_text, question_tokens), -index, column))

    required_names = set(_ALWAYS_KEEP_COLUMNS.get(table, ()))
    required = [column for column in columns if str(column.get("COLUMN_NAME") or "").lower() in required_names]
    required_seen = {str(column.get("COLUMN_NAME") or "").lower() for column in required}

    remaining = [
        column
        for _, _, column in sorted(scored, key=lambda item: (item[0], item[1]), reverse=True)
        if str(column.get("COLUMN_NAME") or "").lower() not in required_seen
    ]
    selected = required + remaining[: max(0, max_columns - len(required))]
    selected_names = {str(column.get("COLUMN_NAME") or "") for column in selected}

    narrowed = copy.deepcopy(schema)
    narrowed["columns"] = selected
    narrowed["primary_key"] = [
        name for name in schema.get("primary_key", []) if str(name) in selected_names
    ]
    narrowed["enums"] = {
        col: values
        for col, values in (schema.get("enums") or {}).items()
        if str(col) in selected_names
    }
    return narrowed


def _score_column(
    table: str,
    column: dict,
    question_text: str,
    question_tokens: set[str],
) -> int:
    name = str(column.get("COLUMN_NAME") or "").lower()
    comment = _normalise(column.get("COLUMN_COMMENT") or "")
    score = 0

    if name in _ALWAYS_KEEP_COLUMNS.get(table, ()):
        score += 100
    if name and name in question_text:
        score += 30
    for hint in _COLUMN_HINTS.get(name, ()):
        if hint.lower() in question_text:
            score += 18
    for token in question_tokens:
        if token and (token in name or token in comment):
            score += 8
    if (column.get("COLUMN_KEY") or "") == "PRI":
        score += 10
    if name.endswith("_id") or name in {"id", "task_id", "affair_id", "associated_affair_id"}:
        score += 8
    return score


def _format_narrowed_schemas(schemas: list[dict]) -> str:
    header = (
        "【字段级裁剪说明】以下 schema 已按当前问题裁剪字段；"
        "只能使用表格中展示的字段。事务/任务关联键固定为 "
        "`affair.affair_id = affair_task.associated_affair_id`。"
    )
    return f"{header}\n\n{format_schemas_for_llm(schemas)}"


def _schema_search_text(schema: dict) -> str:
    parts: list[str] = [
        str(schema.get("table_name") or ""),
        str(schema.get("table_comment") or ""),
    ]
    for column in schema.get("columns") or []:
        parts.append(str(column.get("COLUMN_NAME") or ""))
        parts.append(str(column.get("COLUMN_COMMENT") or ""))
        parts.append(str(column.get("COLUMN_TYPE") or ""))
    for column, values in (schema.get("enums") or {}).items():
        parts.append(str(column))
        parts.extend(str(value) for value in values)
    return " ".join(parts)


def _normalise(value: object) -> str:
    return " ".join(str(value or "").lower().split())


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in _WORD_PAT.findall(text)]
