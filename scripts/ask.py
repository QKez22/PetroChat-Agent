"""命令行问答（不走 FastAPI / SSE）。

用法：
    uv run python scripts/ask.py "什么是 ITPM 策略？"
    uv run python scripts/ask.py "设备分级如何划分" --top-k 5
    uv run python scripts/ask.py "..." --stream         # 流式打印 token
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from petrochat.app.agent import build_graph  # noqa: E402
from petrochat.app.core import setup_langsmith  # noqa: E402

# CLI 调用也启用 LangSmith 追踪（如果 .env 配了的话）
setup_langsmith()


def main() -> int:
    parser = argparse.ArgumentParser(description="石化规范问答")
    parser.add_argument("question", help="要问的问题")
    parser.add_argument("--stream", action="store_true",
                        help="流式输出（按 LangGraph 节点事件流）")
    args = parser.parse_args()

    graph = build_graph()
    initial_state = {"question": args.question}

    if args.stream:
        # graph.stream 按节点事件流，每次 yield 一个节点的输出
        print("─" * 60)
        for event in graph.stream(initial_state):
            for node_name, output in event.items():
                print(f"\n[节点 {node_name}]")
                if "answer" in output:
                    print(output["answer"])
                if "citations" in output and output["citations"]:
                    print("\n引用来源:")
                    for c in output["citations"]:
                        print(f"  - {c}")
        print("─" * 60)
    else:
        result = graph.invoke(initial_state)
        print("\n══════════ 答案 ══════════")
        print(result.get("answer", "(无答案)"))
        cites = result.get("citations") or []
        if cites:
            print("\n══════════ 引用来源 ══════════")
            for c in cites:
                print(f"  - {c}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
