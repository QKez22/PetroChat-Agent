"""Pytest 全局 fixture。"""

from __future__ import annotations

import csv
from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def write_csv() -> Callable[[Path, list[dict[str, str]]], None]:
    """写入 CSV（UTF-8，DictWriter 自动取首行字段名）。

    抽到 conftest 后，evaluation 相关的三个测试文件不再各自抄一份 _write_csv。
    """

    def _write(path: Path, rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    return _write


@pytest.fixture(autouse=True)
def _force_local_tools(monkeypatch):
    """每个测试自动屏蔽 MCP_ENABLED；只在 graph 已加载过的情况下清其缓存。"""
    monkeypatch.setenv("MCP_ENABLED", "false")
    import sys
    if "petrochat.app.core.config" in sys.modules:
        sys.modules["petrochat.app.core.config"].get_settings.cache_clear()
    if "petrochat.app.agent.graph" in sys.modules:
        sys.modules["petrochat.app.agent.graph"].build_graph.cache_clear()
    yield
    if "petrochat.app.core.config" in sys.modules:
        sys.modules["petrochat.app.core.config"].get_settings.cache_clear()
    if "petrochat.app.agent.graph" in sys.modules:
        sys.modules["petrochat.app.agent.graph"].build_graph.cache_clear()
