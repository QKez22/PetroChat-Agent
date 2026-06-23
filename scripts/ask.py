"""命令行问答（不走 FastAPI / SSE）。

用法：
    uv run python scripts/ask.py "什么是 ITPM 策略？"
    uv run python scripts/ask.py "1 MPa 等于多少 psi" --stream
    uv run python scripts/ask.py "查一下 4.2.2 在设备完整性管理体系里写什么"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402

from petrochat.app.agent import build_graph, build_initial_state  # noqa: E402
from petrochat.app.core import setup_langsmith  # noqa: E402

setup_langsmith()


def _extract_answer(state) -> str:
    """从最终 state 取最后一条无 tool_calls 的 AIMessage。"""
    for m in reversed(state.get("messages") or []):
        if isinstance(m, AIMessage) and m.content and not getattr(m, "tool_calls", None):
            return m.content if isinstance(m.content, str) else str(m.content)
    return "(无答案)"


def main() -> int:
    parser = argparse.ArgumentParser(description="石化规范问答")
    parser.add_argument("question")
    parser.add_argument("--stream", action="store_true",
                        help="按节点事件流式打印")
    args = parser.parse_args()

    graph = build_graph()
    state = build_initial_state(args.question)

    if args.stream:
        print("─" * 60)
        for event in graph.stream(state):
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
        result = graph.invoke(state)
        print("\n══════════ 答案 ══════════")
        print(_extract_answer(result))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
