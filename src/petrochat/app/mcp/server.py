"""MCP Server：把 phase 2 的 4 个工具暴露为 MCP 协议端点。

启动方式：
  stdio (开发常用，父进程通过 stdin/stdout 通信)：
      python -m petrochat.app.mcp.server

  streamable-http (跨容器/跨主机)：
      python -m petrochat.app.mcp.server --transport streamable-http --port 8765

设计：
  - 服务端不重复实现工具逻辑，直接调用 ..tools 包里的 @tool 对象的 .invoke()
  - FastMCP 自动从函数签名 + docstring 生成 schema 给 LLM 看
  - 因为 retrieve_specs / lookup_section 等依赖 chromadb + 阿里云 key，
    本进程也需要读到 .env（dotenv 会自动 load 因为 settings 单例触发）
"""

from __future__ import annotations

import argparse

from mcp.server.fastmcp import FastMCP

from ..tools import (
    convert_unit as _local_convert_unit,
    lookup_section as _local_lookup_section,
    retrieve_specs as _local_retrieve_specs,
    search_within_doc as _local_search_within_doc,
)

mcp = FastMCP("petrochat-tools")


# ============================================================
# 工具透传：MCP 装饰器包一层，内部调本地 @tool 的 .invoke()
# 这种"反射式包装"避免维护两份逻辑，所有改动只发生在 ..tools 包
# ============================================================

@mcp.tool()
def convert_unit(value: float, from_unit: str, to_unit: str) -> str:
    """石化领域常用单位换算（压力/温度/流量/长度/重量/体积）。

    Args:
        value: 数值
        from_unit: 源单位（如 'MPa', 'celsius', 'm3/h'）
        to_unit:   目标单位
    """
    return _local_convert_unit.invoke({
        "value": value, "from_unit": from_unit, "to_unit": to_unit,
    })


@mcp.tool()
def lookup_section(source_doc_hint: str, section_number: str) -> str:
    """按章节号精确查询规范条款（metadata 过滤，不走向量检索）。

    Args:
        source_doc_hint: 文档名片段（部分匹配），如 '高桥石化'
        section_number:  完整章节号，如 '4.2.2'
    """
    return _local_lookup_section.invoke({
        "source_doc_hint": source_doc_hint,
        "section_number": section_number,
    })


@mcp.tool()
def search_within_doc(query: str, source_doc_hint: str, top_k: int = 5) -> str:
    """在指定规范文档内做语义检索。

    Args:
        query: 自然语言查询
        source_doc_hint: 文档名片段
        top_k: 返回条数
    """
    return _local_search_within_doc.invoke({
        "query": query, "source_doc_hint": source_doc_hint, "top_k": top_k,
    })


@mcp.tool()
def retrieve_specs(query: str, top_k: int = 5) -> str:
    """在石化规范知识库中做跨文档语义检索（RAG）。

    Args:
        query: 自然语言查询
        top_k: 返回条数
    """
    return _local_retrieve_specs.invoke({"query": query, "top_k": top_k})


# ============================================================
# CLI 入口
# ============================================================
def main() -> None:
    parser = argparse.ArgumentParser(description="PetroChat MCP Server")
    parser.add_argument(
        "--transport", default="stdio",
        choices=["stdio", "streamable-http"],
        help="传输方式 (默认 stdio)",
    )
    parser.add_argument("--port", type=int, default=8765, help="streamable-http 端口")
    args = parser.parse_args()

    if args.transport == "stdio":
        # stdio 模式：父进程通过 stdin/stdout 通信。不要 print 任何东西到 stdout！
        mcp.run(transport="stdio")
    else:
        # streamable-http 模式：监听 HTTP 端口
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
