"""快速演示 NL2SQL 全链路（不走 agent，直接调 nl2sql）。

用法：
    uv run python scripts/ask_sql.py "查询仪表专业所有待运行的事务"
    uv run python scripts/ask_sql.py "统计各执行部门的事务数量"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from petrochat.app.core import setup_langsmith  # noqa: E402
from petrochat.app.sql import nl2sql  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    args = parser.parse_args()
    setup_langsmith()

    print(f"问题: {args.question}")
    print("=" * 60)
    result = nl2sql(args.question)

    if not result.ok:
        print(f"❌ 失败（{result.stage}）: {result.error}")
        if result.sql:
            print(f"\n生成的 SQL:\n{result.sql}")
        return 1

    print(f"\n思路: {result.reasoning}")
    print(f"\nSQL:\n{result.sql}")
    print(f"\n结果（{result.row_count} 行）:")
    if not result.rows:
        print("  (空)")
    else:
        # 简洁打印前 10 行
        cols = result.columns
        print("  " + " | ".join(cols))
        print("  " + "-+-".join(["-" * 8 for _ in cols]))
        for row in result.rows[:10]:
            cells = [str(row.get(c, ""))[:20] for c in cols]
            print("  " + " | ".join(cells))
        if result.row_count > 10:
            print(f"  ...（剩余 {result.row_count - 10} 行省略）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
