"""命令行问答（async 全程）。

为什么必须 async：
  MCP 模式下，langchain-mcp-adapters 暴露的工具是**纯异步**（只有 ainvoke），
  ToolNode 必须通过 graph.ainvoke / graph.astream 才能正确调用，
  否则会报 'StructuredTool does not support sync invocation'。
  本地工具是 sync+async 都支持的，所以 async 链路对两种模式都通用。

用法：
    uv run python scripts/ask.py "什么是 ITPM 策略？"
    uv run python scripts/ask.py "1 MPa 等于多少 psi" --stream
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402

from petrochat.app.agent import build_graph, build_initial_state  # noqa: E402
from petrochat.app.core import get_settings, setup_langsmith  # noqa: E402


def _extract_answer(state) -> str:
    for m in reversed(state.get("messages") or []):
        if isinstance(m, AIMessage) and m.content and not getattr(m, "tool_calls", None):
            return m.content if isinstance(m.content, str) else str(m.content)
    return "(无答案)"


async def main_async(question: str, stream: bool) -> None:
    """全程 async，兼容 MCP 工具的纯异步约定。"""
    setup_langsmith()

    # MCP 模式：在同一个事件循环里 async 初始化
    if get_settings().mcp_enabled:
        from petrochat.app.mcp import init_mcp_tools_async
        await init_mcp_tools_async()

    graph = build_graph()
    state = build_initial_state(question)

    if stream:
        print("─" * 60)
        async for event in graph.astream(state):
            for node_name, output in event.items():
                msgs = output.get("messages") or []
                for m in msgs:
                    if isinstance(m, AIMessage):
                        if getattr(m, "tool_calls", None):
                            for tc in m.tool_calls:
                                print(f"\n🔧 [agent] 调用工具 {tc['name']}({tc.get('args')})")
                        elif m.content:
                            print(f"\n💬 [agent] {m.content}")
                    elif isinstance(m, ToolMessage):
                        preview = (m.content if isinstance(m.content, str) else str(m.content))[:300]
                        print(f"\n📦 [{m.name}] {preview}")
        print("\n" + "─" * 60)
    else:
        result = await graph.ainvoke(state)
        print("\n══════════ 答案 ══════════")
        print(_extract_answer(result))
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description="石化规范问答（async）")
    parser.add_argument("question")
    parser.add_argument("--stream", action="store_true")
    args = parser.parse_args()
    asyncio.run(main_async(args.question, args.stream))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
