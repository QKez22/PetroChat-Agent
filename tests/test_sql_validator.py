"""sql validator 离线测试 —— 纯逻辑，不需要 MySQL。"""

from __future__ import annotations

import pytest

from petrochat.app.sql import validate_sql
from petrochat.app.core.config import get_settings


def test_valid_select_passes() -> None:
    r = validate_sql("SELECT * FROM affair WHERE specialty = '仪表'")
    assert r.ok
    assert "LIMIT" in r.sql.upper()  # 自动注入


def test_select_with_limit_preserved() -> None:
    r = validate_sql("SELECT * FROM affair LIMIT 10")
    assert r.ok
    assert "10" in r.sql


def test_select_oversized_limit_capped() -> None:
    r = validate_sql("SELECT * FROM affair LIMIT 999999")
    assert r.ok
    # 应被下钳到默认上限（1000）
    assert "999999" not in r.sql
    assert "1000" in r.sql


def test_insert_rejected() -> None:
    r = validate_sql("INSERT INTO affair (id) VALUES (1)")
    assert not r.ok
    assert "SELECT" in r.reason


def test_update_rejected() -> None:
    r = validate_sql("UPDATE affair SET specialty = 'x' WHERE id = 1")
    assert not r.ok


def test_delete_rejected() -> None:
    r = validate_sql("DELETE FROM affair WHERE id = 1")
    assert not r.ok


def test_drop_rejected() -> None:
    r = validate_sql("DROP TABLE affair")
    assert not r.ok


def test_multi_statement_rejected() -> None:
    """SELECT 1; DELETE FROM t —— 必须拒。"""
    r = validate_sql("SELECT 1; DELETE FROM affair")
    assert not r.ok
    assert "多语句" in r.reason or "禁止" in r.reason


def test_system_schema_rejected() -> None:
    r = validate_sql("SELECT * FROM mysql.user")
    assert not r.ok
    assert "系统库" in r.reason


def test_information_schema_rejected() -> None:
    r = validate_sql("SELECT * FROM information_schema.tables")
    assert not r.ok


def test_non_whitelisted_table_rejected() -> None:
    r = validate_sql("SELECT * FROM user")
    assert not r.ok
    assert "非白名单表" in r.reason


def test_join_non_whitelisted_table_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYSQL_TABLES_WHITELIST", "affair")
    get_settings.cache_clear()

    r = validate_sql(
        "SELECT a.affair_name, t.task_name "
        "FROM affair a LEFT JOIN affair_task t ON a.affair_id = t.associated_affair_id"
    )
    assert not r.ok
    assert "affair_task" in r.reason


def test_syntax_error_rejected() -> None:
    r = validate_sql("SELEKT * FROM affair")
    assert not r.ok


def test_empty_rejected() -> None:
    r = validate_sql("   ")
    assert not r.ok


def test_join_query_valid() -> None:
    r = validate_sql(
        "SELECT a.affair_name, t.task_name "
        "FROM affair a LEFT JOIN affair_task t ON a.affair_id = t.associated_affair_id "
        "WHERE a.trigger_status = 1"
    )
    assert r.ok


def test_cte_query_valid() -> None:
    r = validate_sql(
        "WITH running AS (SELECT * FROM affair WHERE trigger_status = 1) "
        "SELECT COUNT(*) FROM running"
    )
    assert r.ok


def test_cte_real_table_still_checked() -> None:
    r = validate_sql(
        "WITH running AS (SELECT * FROM user) "
        "SELECT COUNT(*) FROM running"
    )
    assert not r.ok
    assert "非白名单表" in r.reason


def test_aggregation_valid() -> None:
    r = validate_sql(
        "SELECT execution_department, COUNT(*) AS n "
        "FROM affair_task GROUP BY execution_department"
    )
    assert r.ok
