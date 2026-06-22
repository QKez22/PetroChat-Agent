"""文档解析器测试。

用项目实际 data/raw/ 下的样例文件做 smoke test。
为了不让测试依赖外部数据，没有数据时自动 skip。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from petrochat.app.core.models import KnowledgeChunk
from petrochat.app.rag.parser import parse_docx

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


@pytest.fixture
def sample_docx() -> Path:
    """优先用文件 2（小文件，跑得快）。"""
    candidates = [
        DATA_DIR / "2.《高桥石化备品配件管理细则》（2025年2月修订稿）.docx",
        DATA_DIR / "1.中国石化炼化企业设备完整性管理体系文件（V2.0版） (1).docx",
    ]
    for p in candidates:
        if p.exists():
            return p
    pytest.skip(f"未找到测试样例文件，跳过解析器测试。{DATA_DIR}")


def test_parse_returns_chunks(sample_docx: Path) -> None:
    """能成功解析并返回非空 chunk 列表。"""
    chunks = parse_docx(sample_docx)
    assert isinstance(chunks, list)
    assert len(chunks) > 0
    assert all(isinstance(c, KnowledgeChunk) for c in chunks)


def test_chunks_have_required_metadata(sample_docx: Path) -> None:
    """每个 chunk 都有必要的元数据。"""
    chunks = parse_docx(sample_docx)
    for c in chunks:
        assert c.chunk_id, "chunk_id 必须非空"
        assert c.content.strip(), "content 必须非空"
        assert c.source_doc == sample_docx.stem


def test_chunk_ids_are_unique(sample_docx: Path) -> None:
    """chunk_id 在单文档内全局唯一。"""
    chunks = parse_docx(sample_docx)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids)), "存在重复的 chunk_id"


def test_at_least_some_chunks_have_section_number(sample_docx: Path) -> None:
    """规范类文档绝大多数 chunk 应当带章节编号。"""
    chunks = parse_docx(sample_docx)
    with_number = [c for c in chunks if c.section_number]
    # 至少 70% 的 chunk 应该有编号（容忍一些 preamble / 杂项）
    ratio = len(with_number) / len(chunks)
    assert ratio > 0.7, f"带编号的 chunk 比例过低：{ratio:.1%}"


def test_no_oversized_chunk(sample_docx: Path) -> None:
    """二次切分应保证没有过长 chunk（容忍 200 字溢出，分隔符不理想时的兜底）。"""
    chunks = parse_docx(sample_docx)
    over_limit = [c for c in chunks if len(c.content) > 1000]
    assert not over_limit, f"存在 {len(over_limit)} 个超长 chunk，最长 {max(len(c.content) for c in over_limit)}"


def test_doc_extension_rejected(tmp_path: Path) -> None:
    """传 .doc 应给出明确指引。"""
    fake_doc = tmp_path / "fake.doc"
    fake_doc.write_bytes(b"")
    with pytest.raises(ValueError, match="\\.doc"):
        parse_docx(fake_doc)
