"""Schema 抓取与格式化：MySQL → LLM 友好的 markdown，含枚举值采样。"""

from __future__ import annotations

from sqlalchemy import text

from ..core.config import get_settings
from .engine import get_engine, list_tables

_ENUM_CANDIDATE_TYPES = {"varchar", "char", "tinyint", "smallint", "enum"}


def fetch_column_enums(table_name: str, threshold: int | None = None) -> dict[str, list[str]]:
    """对低基数列采样 distinct 值。

    用 SELECT DISTINCT col LIMIT (threshold+1) 提前止扫，大表也很快。
    """
    s = get_settings()
    th = threshold or s.mysql_enum_sample_threshold

    engine = get_engine()
    enums: dict[str, list[str]] = {}

    with engine.connect() as conn:
        cols = conn.execute(text(
            "SELECT COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t "
            "ORDER BY ORDINAL_POSITION"
        ), {"t": table_name}).mappings().all()

        for c in cols:
            col_name = c["COLUMN_NAME"]
            data_type = (c["DATA_TYPE"] or "").lower()
            if data_type not in _ENUM_CANDIDATE_TYPES:
                continue
            try:
                rows = conn.execute(text(
                    f"SELECT DISTINCT `{col_name}` FROM `{table_name}` "
                    f"WHERE `{col_name}` IS NOT NULL AND `{col_name}` <> '' "
                    f"LIMIT :n"
                ), {"n": th + 1}).scalars().all()
            except Exception:
                continue
            if len(rows) == 0 or len(rows) > th:
                continue
            try:
                vals = sorted(rows, key=lambda v: (int(v),) if isinstance(v, int) else (0, str(v)))
            except Exception:
                vals = sorted(str(v) for v in rows)
            enums[col_name] = [str(v) for v in vals]
    return enums


def dump_table_schema(table_name: str, with_enums: bool = True) -> dict:
    """抓取单表的字段定义 + 表注释 + 可选的枚举值采样。"""
    engine = get_engine()
    with engine.connect() as conn:
        cols = conn.execute(text(
            "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, "
            "COLUMN_KEY, COLUMN_COMMENT FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t "
            "ORDER BY ORDINAL_POSITION"
        ), {"t": table_name}).mappings().all()

        table_meta = conn.execute(text(
            "SELECT TABLE_COMMENT FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
        ), {"t": table_name}).mappings().first()

    enums = fetch_column_enums(table_name) if with_enums else {}
    return {
        "table_name": table_name,
        "table_comment": (table_meta or {}).get("TABLE_COMMENT", ""),
        "columns": [dict(c) for c in cols],
        "primary_key": [c["COLUMN_NAME"] for c in cols if c["COLUMN_KEY"] == "PRI"],
        "enums": enums,
    }


def format_table_schema_md(schema: dict) -> str:
    """渲染单表 schema 为 markdown，含枚举值。"""
    lines = [f"### 表 `{schema['table_name']}`"]
    if schema.get("table_comment"):
        lines.append(f"> {schema['table_comment']}")
    lines.append("")
    lines.append("| 字段 | 类型 | 主键 | 可空 | 含义 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for c in schema["columns"]:
        pk = "✓" if c["COLUMN_KEY"] == "PRI" else ""
        nullable = "Y" if c["IS_NULLABLE"] == "YES" else "N"
        comment = (c["COLUMN_COMMENT"] or "").replace("\n", " ").replace("|", "/")
        lines.append(f"| `{c['COLUMN_NAME']}` | {c['COLUMN_TYPE']} | {pk} | {nullable} | {comment} |")

    enums = schema.get("enums") or {}
    if enums:
        lines.append("")
        lines.append("**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**")
        for col, vals in enums.items():
            display = " / ".join(f"`{v}`" for v in vals[:20])
            if len(vals) > 20:
                display += f" …（共 {len(vals)} 个）"
            lines.append(f"- `{col}`：{display}")
    return "\n".join(lines)


def _filtered_tables() -> list[str]:
    all_tables = list_tables()
    whitelist = get_settings().mysql_whitelist
    if not whitelist:
        return all_tables
    return [t for t in all_tables if t in whitelist]


def dump_all_schemas(with_enums: bool = True) -> list[dict]:
    return [dump_table_schema(t, with_enums=with_enums) for t in _filtered_tables()]


def format_schemas_for_llm(schemas: list[dict]) -> str:
    return "\n\n".join(format_table_schema_md(s) for s in schemas)
