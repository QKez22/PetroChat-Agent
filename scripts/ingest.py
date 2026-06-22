"""把 data/raw/ 下的所有 .docx 解析 → 嵌入 → 入库 Chroma。

用法（在项目根目录）：
    uv run python scripts/ingest.py                     # 增量入库
    uv run python scripts/ingest.py --reset             # 清空集合再入库
    uv run python scripts/ingest.py --dry-run           # 只解析不入库
    uv run python scripts/ingest.py --file <docx>       # 入库单个文件
    uv run python scripts/ingest.py --collection demo   # 指定集合名

默认行为：每份文件入库前先按 source_doc 删除旧 chunk，再 upsert，
        保证重跑同一份文件不会留下孤立的旧 chunk。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from loguru import logger

# 让脚本能直接 import 项目代码（不依赖 pip install -e .）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from petrochat.app.core import KnowledgeChunk, get_settings  # noqa: E402
from petrochat.app.rag import (  # noqa: E402
    count,
    delete_by_filter,
    parse_docx,
    reset_collection,
    upsert_chunks,
)


def find_docx_files(data_dir: Path) -> tuple[list[Path], list[Path]]:
    """扫描目录，返回 (.docx 文件, .doc 文件) 两个列表。"""
    docx_files = sorted(p for p in data_dir.glob("*.docx") if not p.name.startswith("~$"))
    doc_files = sorted(data_dir.glob("*.doc"))
    # .doc 和 .docx 都被 *.doc glob 命中，做差集
    doc_files = [p for p in doc_files if p.suffix.lower() == ".doc"]
    return docx_files, doc_files


def ingest_file(
    path: Path,
    collection_name: str | None,
    dry_run: bool = False,
) -> int:
    """处理单个 docx：parse → 删旧 → upsert。返回 chunk 数。"""
    logger.info("→ 解析 {}", path.name)
    t = time.time()
    chunks: list[KnowledgeChunk] = parse_docx(path)
    parse_time = time.time() - t
    logger.info("  ✓ 解析完成: {} chunks ({:.1f}s)", len(chunks), parse_time)

    if dry_run:
        logger.info("  ⊙ dry-run 跳过入库")
        return len(chunks)

    # 按文件幂等：先删后写
    logger.info("  → 删除旧版本 (source_doc={})", path.stem)
    delete_by_filter({"source_doc": path.stem}, collection_name=collection_name)

    logger.info("  → 嵌入 + 入库 ({} chunks)", len(chunks))
    t = time.time()
    n = upsert_chunks(chunks, collection_name=collection_name)
    embed_time = time.time() - t
    logger.info("  ✓ 入库完成: {} chunks ({:.1f}s, {:.1f} chunks/s)",
                n, embed_time, n / embed_time if embed_time > 0 else 0)
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="入库 docx 规范到 Chroma")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "raw",
        help="docx 文件所在目录 (默认: data/raw)",
    )
    parser.add_argument(
        "--file", type=Path, default=None,
        help="只入库指定的单个 .docx 文件",
    )
    parser.add_argument(
        "--collection", default=None,
        help="集合名 (默认取 .env 的 CHROMA_COLLECTION)",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="入库前清空整个集合",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="只解析，不嵌入也不入库（用于核对切片数量）",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    coll_name = args.collection or settings.chroma_collection
    logger.info("目标 collection: {}", coll_name)
    logger.info("Chroma 服务:     {}", settings.chroma_url)

    # ---- 收集要处理的文件 ----
    if args.file:
        if not args.file.exists():
            logger.error("文件不存在: {}", args.file)
            return 1
        docx_files = [args.file]
        doc_files = []
    else:
        if not args.data_dir.exists():
            logger.error("目录不存在: {}", args.data_dir)
            return 1
        docx_files, doc_files = find_docx_files(args.data_dir)

    if doc_files:
        logger.warning("发现 {} 个 .doc 文件 (本脚本不支持，请先转换为 .docx):", len(doc_files))
        for d in doc_files:
            logger.warning("  - {}", d.name)
        logger.warning("  方法 1: Word 打开 → 另存为 .docx")
        logger.warning("  方法 2: uv run python scripts/convert_doc.py data/raw/")

    if not docx_files:
        logger.error("没有可处理的 .docx 文件")
        return 1

    logger.info("待处理 .docx 文件: {} 个", len(docx_files))
    for p in docx_files:
        logger.info("  • {}", p.name)

    # ---- 重置集合（如果指定）----
    if args.reset and not args.dry_run:
        logger.warning("--reset: 清空 collection {}", coll_name)
        reset_collection(coll_name)

    # ---- 逐文件入库 ----
    total_chunks = 0
    failed: list[tuple[Path, Exception]] = []
    overall_start = time.time()

    for i, path in enumerate(docx_files, 1):
        logger.info("[{}/{}] 处理 {}", i, len(docx_files), path.name)
        try:
            total_chunks += ingest_file(path, coll_name, dry_run=args.dry_run)
        except Exception as e:
            logger.exception("  ✗ 失败: {}", path.name)
            failed.append((path, e))

    elapsed = time.time() - overall_start

    # ---- 汇总 ----
    logger.info("=" * 50)
    logger.info("总计: {} chunks 跨 {} 文件，耗时 {:.1f}s",
                total_chunks, len(docx_files) - len(failed), elapsed)
    if not args.dry_run:
        logger.info("collection 当前总量: {} chunks", count(coll_name))
    if failed:
        logger.error("失败文件 {} 个:", len(failed))
        for p, e in failed:
            logger.error("  - {}: {}", p.name, e)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
