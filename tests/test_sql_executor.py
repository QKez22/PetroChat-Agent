"""SQL executor 集成测试 —— MySQL 不通自动 skip。"""

from __future__ import annotations

import pytest

from petrochat.app.sql import execute_sql, healthcheck


@pytest.fixture(scope="module")
def db_alive() -> bool:
    h = healthcheck()
    if not h.get("ok"):
        pytest.skip(f"MySQL 不可达: {h.get('error')}")
    return True


def test_execute_select_one(db_alive) -> None:
    r = execute_sql("SELECT 1 AS one")
    assert r.ok
    assert r.row_count == 1
    assert r.rows[0]["one"] == 1


def test_execute_invalid_table_returns_error(db_alive) -> None:
    r = execute_sql("SELECT * FROM nonexistent_xyz")
    assert not r.ok
    assert r.error


def test_inject_timeout_hint(db_alive) -> None:
    r = execute_sql("SELECT 1")
    assert "MAX_EXECUTION_TIME" in r.sql_executed
