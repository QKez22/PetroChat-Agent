"""Pytest 全局 fixture。"""

from __future__ import annotations

import pytest


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
