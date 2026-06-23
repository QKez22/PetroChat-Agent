"""导出 MySQL schema 为 markdown，供人审阅 + 后续 RAG 召回。

用法：
    uv run python scripts/dump_schema.py                       # 打印到屏幕
    uv run python scripts/dump_schema.py -o data/schema.md     # 写文件
    uv run python scripts/dump_schema.py --tables affair affair_task  # 指定表

也用作连通性自检：跑通就证明 MySQL 配置 + 网络都通了。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from petrochat.app.sql import (  # noqa: E402
    dump_table_schema,
    format_schemas_for_llm,
    healthcheck,
    list_tables,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="导出 MySQL schema 为 markdown")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="输出文件路径（不指定则打印到 stdout）")
    parser.add_argument("--tables", nargs="+", default=None,
                        help="指定要导出的表名，默认全部 BASE TABLE")
    args = parser.parse_args()

    # 1. 探活
    health = healthcheck()
    if not health.get("ok"):
        print(f"✗ MySQL 连接失败: {health.get('error')}", file=sys.stderr)
        return 1
    print(f"✓ MySQL 连通: version={health['version']} database={health['database']}",
          file=sys.stderr)

    # 2. 列表
    all_tables = list_tables()
    target = args.tables or all_tables
    missing = set(target) - set(all_tables)
    if missing:
        print(f"⚠ 表不存在，跳过: {missing}", file=sys.stderr)
        target = [t for t in target if t in all_tables]
    print(f"待导出: {target}", file=sys.stderr)

    # 3. dump
    schemas = [dump_table_schema(t) for t in target]
    md = format_schemas_for_llm(schemas)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(md, encoding="utf-8")
        print(f"✓ 已写入 {args.output}", file=sys.stderr)
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
