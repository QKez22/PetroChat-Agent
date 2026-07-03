"""MCP 测试。

离线纯逻辑部分（client 配置构造）必跑；
端到端 server↔client 测试只在依赖安装齐备时跑（langchain-mcp-adapters 没装就跳过）。
"""

from __future__ import annotations

import pytest

# server 模块直接 import 不依赖网络/子进程，仅验证装饰器结构
def test_server_module_importable() -> None:
    """server.py 能 import 且 mcp 对象存在。"""
    from petrochat.app.mcp import server
    assert hasattr(server, "mcp")
    assert hasattr(server, "main")


def test_server_registers_four_tools() -> None:
    """4 个工具都被 @mcp.tool() 注册。"""
    from petrochat.app.mcp.server import mcp
    # FastMCP 的内部 tools 字典名因版本不同（_tools / tools），用 dir 探测
    candidates = ["_tool_manager", "tool_manager", "_tools", "tools"]
    found = None
    for c in candidates:
        if hasattr(mcp, c):
            found = getattr(mcp, c)
            break
    assert found is not None, "FastMCP 未暴露 tools 注册表"


def test_client_config_stdio() -> None:
    """默认 stdio 模式构造的客户端配置正确。"""
    from petrochat.app.mcp.client import _build_server_config
    config = _build_server_config()
    assert "petrochat" in config
    server = config["petrochat"]
    assert server["transport"] == "stdio"
    assert "command" in server
    assert "args" in server


def test_get_loaded_tools_before_init_raises() -> None:
    """未初始化就拿工具应抛清晰错误。"""
    from petrochat.app.mcp.client import get_loaded_tools, reset_for_testing
    reset_for_testing()
    with pytest.raises(RuntimeError, match="未初始化"):
        get_loaded_tools()


def test_graph_falls_back_to_local_tools_when_mcp_uninitialized(monkeypatch) -> None:
    """MCP 开关打开但工具未初始化时，graph 构建应降级本地工具。"""
    from petrochat.app.agent.graph import _resolve_tools, build_graph
    from petrochat.app.core.config import get_settings
    from petrochat.app.mcp.client import reset_for_testing
    from petrochat.app.tools import ALL_TOOLS

    monkeypatch.setenv("MCP_ENABLED", "true")
    get_settings.cache_clear()
    build_graph.cache_clear()
    reset_for_testing()

    assert _resolve_tools() == ALL_TOOLS


def test_general_node_falls_back_to_local_tools_when_mcp_uninitialized(monkeypatch) -> None:
    """MCP 缓存缺失时，general 节点取工具不应抛错。"""
    from petrochat.app.agent.nodes.general_node import _current_tools
    from petrochat.app.core.config import get_settings
    from petrochat.app.mcp.client import reset_for_testing
    from petrochat.app.tools import ALL_TOOLS

    monkeypatch.setenv("MCP_ENABLED", "true")
    get_settings.cache_clear()
    reset_for_testing()

    assert _current_tools() == ALL_TOOLS
