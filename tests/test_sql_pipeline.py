"""NL2SQL pipeline mode tests."""

from __future__ import annotations

import pytest

from petrochat.app.core.config import get_settings
from petrochat.app.sql.executor import ExecutionResult
from petrochat.app.sql.generator import SqlPlan
from petrochat.app.sql.hints import build_sql_question_with_hints, extract_sql_business_hints
from petrochat.app.sql.schema_narrowing import (
    SchemaSelection,
    clear_schema_narrowing_cache,
    select_relevant_schema,
)


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    clear_schema_narrowing_cache()
    yield
    get_settings.cache_clear()
    clear_schema_narrowing_cache()


def _fake_schemas() -> list[dict]:
    return [
        {
            "table_name": "affair",
            "table_comment": "事务主表",
            "columns": [
                {
                    "COLUMN_NAME": "affair_id",
                    "COLUMN_COMMENT": "事务ID",
                    "COLUMN_TYPE": "bigint",
                    "COLUMN_KEY": "PRI",
                    "IS_NULLABLE": "NO",
                },
                {
                    "COLUMN_NAME": "specialty",
                    "COLUMN_COMMENT": "专业",
                    "COLUMN_TYPE": "varchar",
                    "COLUMN_KEY": "",
                    "IS_NULLABLE": "YES",
                },
                {
                    "COLUMN_NAME": "area",
                    "COLUMN_COMMENT": "区域",
                    "COLUMN_TYPE": "varchar",
                    "COLUMN_KEY": "",
                    "IS_NULLABLE": "YES",
                },
                {
                    "COLUMN_NAME": "template_path",
                    "COLUMN_COMMENT": "模板路径",
                    "COLUMN_TYPE": "varchar",
                    "COLUMN_KEY": "",
                    "IS_NULLABLE": "YES",
                },
                {
                    "COLUMN_NAME": "signature",
                    "COLUMN_COMMENT": "审核签名",
                    "COLUMN_TYPE": "varchar",
                    "COLUMN_KEY": "",
                    "IS_NULLABLE": "YES",
                },
            ],
            "primary_key": ["affair_id"],
            "enums": {},
        },
        {
            "table_name": "affair_task",
            "table_comment": "事务任务明细",
            "columns": [
                {
                    "COLUMN_NAME": "task_name",
                    "COLUMN_COMMENT": "任务名称",
                    "COLUMN_TYPE": "varchar",
                    "COLUMN_KEY": "",
                    "IS_NULLABLE": "YES",
                },
                {
                    "COLUMN_NAME": "associated_affair_id",
                    "COLUMN_COMMENT": "关联事务Id",
                    "COLUMN_TYPE": "varchar",
                    "COLUMN_KEY": "",
                    "IS_NULLABLE": "YES",
                },
                {
                    "COLUMN_NAME": "execution_department",
                    "COLUMN_COMMENT": "执行部门",
                    "COLUMN_TYPE": "varchar",
                    "COLUMN_KEY": "",
                    "IS_NULLABLE": "YES",
                },
                {
                    "COLUMN_NAME": "body_equipment_name",
                    "COLUMN_COMMENT": "本体设备名称",
                    "COLUMN_TYPE": "varchar",
                    "COLUMN_KEY": "",
                    "IS_NULLABLE": "YES",
                },
                {
                    "COLUMN_NAME": "file_path",
                    "COLUMN_COMMENT": "文件路径",
                    "COLUMN_TYPE": "varchar",
                    "COLUMN_KEY": "",
                    "IS_NULLABLE": "YES",
                },
            ],
            "primary_key": [],
            "enums": {},
        },
    ]


def test_schema_narrowing_prefers_task_table(monkeypatch: pytest.MonkeyPatch) -> None:
    from petrochat.app.sql import schema_narrowing

    monkeypatch.setattr(schema_narrowing, "dump_all_schemas", _fake_schemas)

    selection = select_relevant_schema("按执行部门统计任务数量", max_tables=1)

    assert selection.tables == ["affair_task"]
    assert selection.selected_table_count == 1
    assert selection.total_table_count == 2
    assert "affair_task" in selection.schema_md


def test_schema_narrowing_expands_related_tables_and_prunes_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from petrochat.app.sql import schema_narrowing

    monkeypatch.setattr(schema_narrowing, "dump_all_schemas", _fake_schemas)

    selection = select_relevant_schema(
        "按设备统计任务数量",
        max_tables=2,
        max_columns_per_table=2,
    )

    assert selection.tables == ["affair_task", "affair"]
    assert selection.selected_column_count < selection.total_column_count
    assert "affair.affair_id = affair_task.associated_affair_id" in selection.schema_md
    assert "`file_path`" not in selection.schema_md


def test_sql_business_hints_extract_filters_from_question() -> None:
    hints = extract_sql_business_hints("查炼油一部 K7102 相关动设备任务，只看频次是1次/季度的")

    assert hints.departments == ["炼油一部"]
    assert hints.specialties == ["动"]
    assert hints.equipment_ids == ["K7102"]
    assert hints.frequencies == ["1次/季度"]
    assert hints.prefer_task_table is True


def test_sql_business_hints_extract_exact_affair_name_and_hyphen_equipment() -> None:
    hints = extract_sql_business_hints("查一下炼油二部K3102-ST相关的蒸汽透平速关阀检查任务。")

    assert hints.departments == ["炼油二部"]
    assert hints.specialties == ["动"]
    assert hints.equipment_ids == ["K3102-ST"]
    assert hints.affair_names == ["蒸汽透平速关阀检查"]


def test_sql_question_with_hints_inherits_recent_user_constraints() -> None:
    prompt = build_sql_question_with_hints(
        "只看频次是1次/季度的",
        history=[
            {"role": "user", "content": "查炼油一部 K7102 相关的蒸汽透平速关阀检查任务"},
            {"role": "assistant", "content": "上一轮回答"},
        ],
    )

    assert "【最近用户约束】" in prompt
    assert "炼油一部" in prompt
    assert "K7102" in prompt
    assert "蒸汽透平速关阀检查" in prompt
    assert "affair_task.frequency" in prompt
    assert "affair_task.operation_department" in prompt
    assert "affair_task.affair_name" in prompt


def test_nl2sql_legacy_keeps_full_whitelist(monkeypatch: pytest.MonkeyPatch) -> None:
    from petrochat.app.sql import agent

    monkeypatch.setenv("SQL_PIPELINE_MODE", "legacy")
    monkeypatch.setenv("MYSQL_TABLES_WHITELIST", "affair,affair_task")
    get_settings.cache_clear()
    monkeypatch.setattr(
        agent,
        "generate_sql",
        lambda question: SqlPlan(sql="SELECT affair_id FROM affair", reasoning="查事务主表"),
    )
    monkeypatch.setattr(
        agent,
        "execute_sql",
        lambda sql: ExecutionResult(
            ok=True,
            columns=["affair_id"],
            rows=[{"affair_id": 1}],
            row_count=1,
            sql_executed=sql,
        ),
    )

    result = agent.nl2sql("查询事务")

    assert result.ok
    assert result.pipeline_mode == "legacy"
    assert result.schema_tables == ["affair", "affair_task"]
    assert result.repair_attempted is False


def test_nl2sql_optimized_repairs_validation_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from petrochat.app.sql import agent

    monkeypatch.setenv("SQL_PIPELINE_MODE", "optimized")
    monkeypatch.setenv("MYSQL_TABLES_WHITELIST", "affair,affair_task")
    monkeypatch.setenv("SQL_REPAIR_MAX_ATTEMPTS", "1")
    get_settings.cache_clear()
    selection = SchemaSelection(
        tables=["affair"],
        schema_md="### 表 `affair`\n| 字段 | 类型 | 主键 | 可空 | 含义 |",
        total_table_count=2,
        reason="unit-test",
        selected_column_count=8,
        total_column_count=20,
    )
    monkeypatch.setattr(agent, "select_relevant_schema", lambda question: selection)
    monkeypatch.setattr(
        agent,
        "generate_sql",
        lambda question, schema_md=None: SqlPlan(sql="DELETE FROM affair", reasoning="bad"),
    )
    monkeypatch.setattr(
        agent,
        "repair_sql",
        lambda question, invalid_sql, validation_error, schema_md=None: SqlPlan(
            sql="SELECT affair_id FROM affair",
            reasoning="修复为只读查询",
        ),
    )
    monkeypatch.setattr(
        agent,
        "execute_sql",
        lambda sql: ExecutionResult(
            ok=True,
            columns=["affair_id"],
            rows=[{"affair_id": 1}],
            row_count=1,
            sql_executed=sql,
        ),
    )

    result = agent.nl2sql("查询事务")

    assert result.ok
    assert result.pipeline_mode == "optimized"
    assert result.schema_tables == ["affair"]
    assert result.schema_table_count == 1
    assert result.schema_column_count == 8
    assert result.repair_attempted is True
    assert result.repair_succeeded is True
    assert "SELECT" in result.sql.upper()


def test_nl2sql_optimized_repairs_execute_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from petrochat.app.sql import agent

    monkeypatch.setenv("SQL_PIPELINE_MODE", "optimized")
    monkeypatch.setenv("MYSQL_TABLES_WHITELIST", "affair,affair_task")
    monkeypatch.setenv("SQL_REPAIR_MAX_ATTEMPTS", "1")
    get_settings.cache_clear()
    selection = SchemaSelection(
        tables=["affair", "affair_task"],
        schema_md="### 表 `affair`\n| 字段 | 类型 | 主键 | 可空 | 含义 |",
        total_table_count=2,
        reason="unit-test",
        selected_column_count=10,
        total_column_count=20,
    )
    calls = {"execute": 0}
    monkeypatch.setattr(agent, "select_relevant_schema", lambda question: selection)
    monkeypatch.setattr(
        agent,
        "generate_sql",
        lambda question, schema_md=None: SqlPlan(
            sql="SELECT a.operation_department FROM affair a",
            reasoning="列归属错误",
        ),
    )
    monkeypatch.setattr(
        agent,
        "repair_sql",
        lambda question, invalid_sql, validation_error, schema_md=None: SqlPlan(
            sql="SELECT execution_department FROM affair",
            reasoning="修复列名",
        ),
    )

    def fake_execute(sql: str) -> ExecutionResult:
        calls["execute"] += 1
        if calls["execute"] == 1:
            return ExecutionResult(ok=False, error="Unknown column 'a.operation_department'")
        return ExecutionResult(
            ok=True,
            columns=["execution_department"],
            rows=[{"execution_department": "炼油一部"}],
            row_count=1,
            sql_executed=sql,
        )

    monkeypatch.setattr(agent, "execute_sql", fake_execute)

    result = agent.nl2sql("查询炼油一部任务")

    assert result.ok
    assert calls["execute"] == 2
    assert result.repair_attempted is True
    assert result.repair_succeeded is True
    assert result.stage == "ok"
