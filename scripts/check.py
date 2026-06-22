"""快速验证向量库当前状态。

用法：
    uv run python scripts/check.py                            # 默认问"ITPM 策略"
    uv run python scripts/check.py "什么是设备分级管理"      # 自定义 query
    uv run python scripts/check.py "..." --top-k 5            # 自定义返回数量
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 把 src/ 加进 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from petrochat.app.rag import count, query  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="检索 + 集合状态查看")
    parser.add_argument("query", nargs="?", default="什么是 ITPM 策略？",
                        help="检索 query")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--collection", default=None)
    args = parser.parse_args()

    total = count(args.collection)
    print(f"集合 chunks 总量: {total}")
    if total == 0:
        print("空集合，请先跑: uv run python scripts/ingest.py")
        return 1

    print(f"\nQuery: {args.query}")
    print(f"Top-{args.top_k} 结果:")
    print("-" * 60)
    results = query(args.query, top_k=args.top_k, collection_name=args.collection)
    for i, r in enumerate(results, 1):
        src = r.metadata.get("source_doc", "?")
        sec = r.metadata.get("section_number", "?")
        path = r.metadata.get("section_path", "?")
        print(f"\n[{i}] score={r.score:.4f}  {src} | 章节 {sec}")
        print(f"    path: {path}")
        print(f"    内容: {r.content[:200].replace(chr(10), ' / ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
