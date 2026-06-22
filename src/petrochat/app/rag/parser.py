"""石化规范文档解析器。

设计要点：
1. 双策略识别标题：优先 Word 原生 outlineLvl，回退到"数字编号正则"。
2. 文档顺序遍历段落和表格（CT_P / CT_Tbl）。
3. 表格转 Markdown 表 + 合并单元格去重。
4. **标题永远进 buffer**：解决文件 2 那种"编号即条款"的形态（如 "1.4.1 备品配件是…"）。
   不再尝试区分"标题段落"与"正文段落"，统一让标题成为 chunk 内容的第一行。
5. 用 MIN_CHUNK_CHARS 过滤掉真正无意义的小片段（文档标题、版本号、扉页等）。
6. chunk 过大用 RecursiveCharacterTextSplitter 二次切，保留 50 字重叠。
7. 文本归一：去全角空格、压缩汉字间多余空格。
8. 只接受 .docx；.doc 抛错并指引（用 Word "Save As" 或 scripts/convert_doc.py）。
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger

from ..core.models import KnowledgeChunk

# ---------- 配置常量 ----------
MAX_CHUNK_CHARS = 800       # 超过则二次切分
MIN_CHUNK_CHARS = 15        # 小于此阈值的 chunk 视为噪音（如文档扉页、版本号）
CHUNK_OVERLAP = 50          # 二次切分时的重叠字符数

# ---------- 正则 ----------
# 章节编号：N / N.N / N.N.N / N.N.N.N，兼容半角/全角空格 + 半角/全角点
SECTION_PAT = re.compile(r"^(\d+(?:\.\d+){0,3})[\s　.．]+(.+)$")


def _normalize(text: str) -> str:
    """文本归一：去多余空白、压缩汉字间空格。"""
    text = text.strip()
    if not text:
        return ""
    text = re.sub(r"[\s　]+", " ", text)
    text = re.sub(r"([一-鿿]) +([一-鿿])", r"\1\2", text)
    return text.strip()


def _outline_level(p: Paragraph) -> int | None:
    """读 Word 原生 outlineLvl（0=H1, 1=H2, ...）。没有返回 None。"""
    pPr = p._element.find(qn("w:pPr"))
    if pPr is None:
        return None
    ol = pPr.find(qn("w:outlineLvl"))
    if ol is None:
        return None
    val = ol.get(qn("w:val"))
    try:
        return int(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _iter_block_items(doc) -> Iterator[Paragraph | Table]:
    """按文档顺序遍历段落与表格（保持原文顺序，doc.paragraphs/tables 会乱序）。"""
    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, doc)
        elif isinstance(child, CT_Tbl):
            yield Table(child, doc)


def _table_to_markdown(table: Table) -> str:
    """表格转 markdown，处理 python-docx 对合并单元格重复返回的问题。"""
    rows: list[list[str]] = []
    for row in table.rows:
        cells = [_normalize(c.text) for c in row.cells]
        # 相邻去重（合并单元格的副作用）
        dedup: list[str] = []
        prev = None
        for c in cells:
            if c != prev:
                dedup.append(c)
                prev = c
        rows.append(dedup)
    if not rows:
        return ""
    max_cols = max(len(r) for r in rows)
    rows = [r + [""] * (max_cols - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |",
             "| " + " | ".join(["---"] * max_cols) + " |"]
    for r in rows[1:]:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def _match_section(text: str) -> tuple[str, str] | None:
    """识别 'N.N.N 内容'。返回 (编号, 标题正文)；不匹配返回 None。"""
    m = SECTION_PAT.match(text)
    if not m:
        return None
    return m.group(1), m.group(2).strip()


def parse_docx(path: str | Path) -> list[KnowledgeChunk]:
    """解析石化规范 docx → KnowledgeChunk 列表。

    Args:
        path: .docx 文件路径。
    """
    path = Path(path)
    if path.suffix.lower() == ".doc":
        raise ValueError(
            f"不支持 .doc 旧格式：{path.name}\n"
            f"请用 Word 'Save As' 转存为 .docx，或运行 scripts/convert_doc.py。"
        )
    if path.suffix.lower() != ".docx":
        raise ValueError(f"仅支持 .docx，收到：{path.suffix}")

    doc = Document(str(path))
    chunks: list[KnowledgeChunk] = []
    source_doc = path.stem
    section_stack: list[str] = []
    current_number = ""
    buffer: list[str] = []  # 当前章节累积的所有行（标题 + 正文）
    chunk_seq = 0  # 全局序号，保证 chunk_id 唯一

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=MAX_CHUNK_CHARS,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", "；", "，", " ", ""],
    )

    def flush(chunk_type: str = "clause") -> None:
        """产出 chunk(s)。空 buffer 或内容过短直接跳过。"""
        nonlocal chunk_seq
        content = "\n".join(t for t in buffer if t).strip()
        if len(content) < MIN_CHUNK_CHARS:
            return

        sec_path = " > ".join(s for s in section_stack if s) or "preamble"
        pieces = (
            splitter.split_text(content)
            if len(content) > MAX_CHUNK_CHARS
            else [content]
        )
        pieces = [p for p in pieces if p.strip()]

        for piece in pieces:
            chunks.append(
                KnowledgeChunk(
                    chunk_id=f"{source_doc}#{current_number or 'preamble'}#{chunk_seq}",
                    content=piece,
                    source_doc=source_doc,
                    section_number=current_number,
                    section_path=sec_path,
                    chunk_type=chunk_type,
                )
            )
            chunk_seq += 1

    for item in _iter_block_items(doc):
        if isinstance(item, Paragraph):
            text = _normalize(item.text)
            if not text:
                continue

            ol = _outline_level(item)
            section_info = _match_section(text)
            is_heading = ol is not None or section_info is not None

            if is_heading:
                # 上一节落地
                flush()
                buffer = []

                if section_info is not None:
                    current_number, title = section_info
                else:
                    current_number = ""
                    title = text

                # 标题永远入 buffer：解决"编号即条款"形态
                buffer.append(f"{current_number} {title}".strip())

                # 更新 section_stack
                depth = (
                    (current_number.count(".") + 1)
                    if current_number
                    else ((ol + 1) if ol is not None else 1)
                )
                while len(section_stack) >= depth:
                    section_stack.pop()
                while len(section_stack) < depth - 1:
                    section_stack.append("")
                section_stack.append(f"{current_number} {title}".strip())
            else:
                # 普通正文
                buffer.append(text)

        elif isinstance(item, Table):
            flush()  # 表格前先把上文 clause flush 掉
            buffer = []
            md = _table_to_markdown(item)
            if md.strip() and len(md) >= MIN_CHUNK_CHARS:
                # 表格单独入一个 chunk_type=table
                buffer.append(md)
                flush(chunk_type="table")
                buffer = []

    flush()  # 最后一节
    logger.info("解析 {file} 完成：{n} 个 chunk", file=path.name, n=len(chunks))
    return chunks
