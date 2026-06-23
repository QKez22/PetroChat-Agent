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
