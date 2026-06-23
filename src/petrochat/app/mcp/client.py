"""MCP 客户端：连接 MCP Server 拿到 LangChain BaseTool 列表。

设计：
- 一次性 async 加载，模块级缓存（不要每次请求都建连接）
- 提供 sync 入口给 CLI 使用（asyncio.run 包一下）
- FastAPI 用 lifespan 在启动时 await 这个 async 入口

切传输方式：改 settings.mcp_transport 即可，本模块自动适配。
"""

from __future__ import annotations

import asyncio

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from loguru import logger

from ..core.config import get_settings

_LOADED_TOOLS: list[BaseTool] | None = None


def _build_server_config() -> dict:
    """根据 settings 构造 MultiServerMCPClient 配置。"""
    s = get_settings()
    if s.mcp_transport == "streamable_http":
        return {
            "petrochat": {
                "url": s.mcp_server_url,
                "transport": "streamable_http",
            }
        }
    # 默认 stdio
    return {
        "petrochat": {
            "command": s.mcp_server_command,
            "args": s.mcp_server_args.split(),
            "transport": "stdio",
        }
    }


async def init_mcp_tools_async() -> list[BaseTool]:
    """异步初始化：连接 MCP Server，拉取工具列表，缓存。

    幂等：重复调用直接返回缓存。
    """
    global _LOADED_TOOLS
    if _LOADED_TOOLS is not None:
        return _LOADED_TOOLS

    config = _build_server_config()
    logger.info("连接 MCP Server: {}", config)
    client = MultiServerMCPClient(config)
    _LOADED_TOOLS = await client.get_tools()
    logger.info("MCP 工具加载完成: {} 个 → {}",
                len(_LOADED_TOOLS),
                [t.name for t in _LOADED_TOOLS])
    return _LOADED_TOOLS


def init_mcp_tools_sync() -> list[BaseTool]:
    """同步入口（给 CLI / 脚本用，不要在已有事件循环里调用）。"""
    global _LOADED_TOOLS
    if _LOADED_TOOLS is not None:
        return _LOADED_TOOLS
    return asyncio.run(init_mcp_tools_async())


def get_loaded_tools() -> list[BaseTool]:
    """同步获取已加载的工具（必须先 init_mcp_tools_*）。"""
    if _LOADED_TOOLS is None:
        raise RuntimeError(
            "MCP 工具未初始化。请先在应用启动时调用 "
            "init_mcp_tools_async()（FastAPI）或 init_mcp_tools_sync()（CLI）。"
        )
    return _LOADED_TOOLS


def reset_for_testing() -> None:
    """仅供测试使用：清空缓存允许重新加载。"""
    global _LOADED_TOOLS
    _LOADED_TOOLS = None
