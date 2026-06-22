"""检索器测试。

分两层：
1. format_citation/format_citations 纯逻辑，离线可测
2. PetrochatRetriever 集成测试，跳过条件：Chroma 或 embedding key 不可达
"""

from __future__ import annotations

import uuid

import pytest
from langchain_core.documents import Document

from petrochat.app.core import KnowledgeChunk, get_settings
from petrochat.app.rag import (
    PetrochatRetriever,
    format_citation,
    format_citations,
    get_client,
    make_retriever,
    reset_collection,
    upsert_chunks,
)


# ============== 离线纯逻辑测试 ==============

def test_format_citation_basic() -> None:
    cite = format_citation({
        "source_doc": "2.《高桥石化备品配件管理细则》（2025年2月修订稿）",
        "section_number": "3.1.2",
    })
    # 去掉了 "2." 前缀和"（...修订稿）"尾巴
    assert "2." not in cite
    assert "修订稿" not in cite
    assert "3.1.2" in cite
    assert "高桥石化备品配件管理细则" in cite


def test_format_citation_no_section() -> None:
    """没 section_number 时不附加章节号。"""
    cite = format_citation({"source_doc": "1.设备完整性管理"})
    assert "1." not in cite
    assert cite.endswith("》") or cite.endswith("管理》")


def test_format_citation_missing_source() -> None:
    cite = format_citation({})
    assert "未知" in cite


def test_format_citations_dedup_keeps_order() -> None:
    docs = [
        Document(page_content="x", metadata={"source_doc": "1.A", "section_number": "1.1"}),
        Document(page_content="y", metadata={"source_doc": "1.A", "section_number": "1.1"}),
        Document(page_content="z", metadata={"source_doc": "2.B", "section_number": "2.1"}),
    ]
    cites = format_citations(docs)
    assert len(cites) == 2  # 去重
    assert "A" in cites[0] and "1.1" in cites[0]
    assert "B" in cites[1] and "2.1" in cites[1]


# ============== 集成测试（Chroma + embedding 可达时才跑）==============

@pytest.fixture(scope="module")
def chroma_alive() -> bool:
    try:
        get_client.cache_clear()
        get_client()
        return True
    except Exception as e:
        pytest.skip(f"Chroma 不可达: {e}")


@pytest.fixture
def embedder_ready() -> bool:
    if not get_settings().dashscope_api_key.get_secret_value():
        pytest.skip("DASHSCOPE_API_KEY 未设置")
    return True


@pytest.fixture
def temp_collection_with_data(chroma_alive, embedder_ready) -> str:
    """临时集合 + 3 条假数据，跑完自动清理。"""
    name = f"test_retr_{uuid.uuid4().hex[:6]}"
    upsert_chunks([
        KnowledgeChunk(
            chunk_id="a1", content="ITPM 策略是针对设备故障模式的预防性检测和维修活动。",
            source_doc="docA", section_number="1.1", section_path="1 > 1.1",
        ),
        KnowledgeChunk(
            chunk_id="a2", content="备品配件储备目录由设备动力部牵头编制。",
            source_doc="docB", section_number="2.1", section_path="2 > 2.1",
        ),
        KnowledgeChunk(
            chunk_id="a3", content="设备分级管理按风险分为 A、B、C 三类。",
            source_doc="docA", section_number="3.1", section_path="3 > 3.1",
        ),
    ], collection_name=name)
    yield name
    reset_collection(name)


def test_retriever_returns_documents(temp_collection_with_data: str) -> None:
    """retriever.invoke 应返回 Document 列表，且元数据带 score/chunk_id。"""
    r = make_retriever(top_k=2, collection=temp_collection_with_data)
    docs = r.invoke("什么是 ITPM 策略？")
    assert len(docs) == 2
    assert all(isinstance(d, Document) for d in docs)
    assert "score" in docs[0].metadata
    assert "chunk_id" in docs[0].metadata


def test_retriever_top_relevant_is_itpm(temp_collection_with_data: str) -> None:
    r = make_retriever(top_k=1, collection=temp_collection_with_data)
    docs = r.invoke("ITPM 是什么？")
    assert "ITPM" in docs[0].page_content


def test_retriever_where_filter(temp_collection_with_data: str) -> None:
    """where_filter 应限定到指定 source_doc。"""
    r = make_retriever(
        top_k=5,
        where={"source_doc": "docB"},
        collection=temp_collection_with_data,
    )
    docs = r.invoke("管理")
    for d in docs:
        assert d.metadata["source_doc"] == "docB"


def test_retriever_score_threshold(temp_collection_with_data: str) -> None:
    """score_threshold 极小时应过滤掉所有结果。"""
    r = PetrochatRetriever(
        top_k=5,
        score_threshold=0.0001,  # 几乎不可能达到
        collection_name=temp_collection_with_data,
    )
    docs = r.invoke("不相关的随机问题 quark gluon")
    assert docs == []


def test_format_citations_from_real_docs(temp_collection_with_data: str) -> None:
    """端到端：检索 + 引用格式化。"""
    r = make_retriever(top_k=3, collection=temp_collection_with_data)
    docs = r.invoke("ITPM")
    citations = format_citations(docs)
    assert len(citations) >= 1
    assert all("docA" in c or "docB" in c for c in citations)
