"""Pytest 全局 fixture。

为什么把 MCP 强制关掉：
  build_graph() 会读 settings.mcp_enabled 决定工具源。
  开发者 .env 里可能开着 MCP_ENABLED=true（phase 3 演示），
  但单元测试里 MCP server 子进程没启动，会抛 RuntimeError。
  全局把它 setenv 关掉，让 graph 测试稳定走 LOCAL_TOOLS 分支。
  真要测 MCP 路径，应在专门的 test_mcp_integration.py 里启停。
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _force_local_tools(monkeypatch):
    """每个测试自动屏蔽 MCP_ENABLED。"""
    monkeypatch.setenv("MCP_ENABLED", "false")
    # 清缓存，确保新值生效
    from petrochat.app.core.config import get_settings
    from petrochat.app.agent.graph import build_graph

    get_settings.cache_clear()
    build_graph.cache_clear()
    yield
    get_settings.cache_clear()
    build_graph.cache_clear()
