"""MySQL 引擎与 schema 抓取测试。

集成测试，MySQL 不可达自动 skip。
"""

from __future__ import annotations

import pytest

from petrochat.app.sql import (
    dump_table_schema,
    format_schemas_for_llm,
    format_table_schema_md,
    healthcheck,
    list_tables,
)


@pytest.fixture(scope="module")
def db_alive() -> bool:
    h = healthcheck()
    if not h.get("ok"):
        pytest.skip(f"MySQL 不可达: {h.get('error')}")
    return True


def test_healthcheck_returns_version(db_alive) -> None:
    h = healthcheck()
    assert h["ok"] is True
    assert h["version"]
    assert h["database"]


def test_list_tables_includes_affair(db_alive) -> None:
    tables = list_tables()
    assert "affair" in tables or "affair_task" in tables, \
        f"预期表不在列表中: {tables}"


def test_dump_table_schema_has_columns(db_alive) -> None:
    tables = list_tables()
    if not tables:
        pytest.skip("无表可测")
    s = dump_table_schema(tables[0])
    assert s["table_name"] == tables[0]
    assert s["columns"]
    assert all("COLUMN_NAME" in c for c in s["columns"])


def test_format_markdown_contains_columns(db_alive) -> None:
    tables = list_tables()
    if not tables:
        pytest.skip("无表可测")
    s = dump_table_schema(tables[0])
    md = format_table_schema_md(s)
    assert tables[0] in md
    assert "|" in md  # markdown 表格
    assert "字段" in md


def test_format_multiple_schemas(db_alive) -> None:
    tables = list_tables()[:2]  # 只取前两张避免超时
    if not tables:
        pytest.skip("无表可测")
    md = format_schemas_for_llm([dump_table_schema(t) for t in tables])
    for t in tables:
        assert t in md
