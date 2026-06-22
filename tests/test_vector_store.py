"""向量库 CRUD 集成测试。

依赖 Chroma 服务在 localhost:8001 + 阿里云百炼 API Key 可用。
任一不可达自动 skip，CI 上无服务也不会失败。

测试用临时集合（不污染生产 collection），跑完自动清理。
"""

from __future__ import annotations

import uuid

import pytest

from petrochat.app.core import KnowledgeChunk, get_settings
from petrochat.app.rag import (
    count,
    delete_by_filter,
    get_client,
    query,
    reset_collection,
    upsert_chunks,
)


@pytest.fixture(scope="module")
def chroma_alive() -> bool:
    """探活：Chroma 不通就跳过整组测试。"""
    try:
        get_client.cache_clear()  # 防止上次失败的连接被缓存
        get_client()
        return True
    except Exception as e:
        pytest.skip(f"Chroma 未启动或不可达：{e}")


@pytest.fixture
def embedder_ready() -> bool:
    """探活：百炼 key 未配置就跳过。"""
    s = get_settings()
    if not s.dashscope_api_key.get_secret_value():
        pytest.skip("DASHSCOPE_API_KEY 未设置，跳过 embedding 相关测试")
    return True


@pytest.fixture
def temp_collection_name() -> str:
    """每个测试用独立临时集合，避免相互污染。"""
    return f"test_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def sample_chunks() -> list[KnowledgeChunk]:
    """3 条假数据，覆盖不同 source_doc / section / chunk_type。"""
    return [
        KnowledgeChunk(
            chunk_id="docA#1.1#0",
            content="ITPM 策略指针对设备故障模式开展的预防性检测和维修活动。",
            source_doc="docA",
            section_number="1.1",
            section_path="1 范围 > 1.1 术语",
            chunk_type="clause",
        ),
        KnowledgeChunk(
            chunk_id="docA#2.1#1",
            content="设备分级管理是按风险等级把设备分为 A、B、C 三类的管理方法。",
            source_doc="docA",
            section_number="2.1",
            section_path="2 分级 > 2.1 方法",
            chunk_type="clause",
        ),
        KnowledgeChunk(
            chunk_id="docB#3.1#2",
            content="备品配件储备目录由设备动力部牵头组织编制和修订。",
            source_doc="docB",
            section_number="3.1",
            section_path="3 储备",
            chunk_type="clause",
        ),
    ]


def test_upsert_and_count(
    chroma_alive,
    embedder_ready,
    temp_collection_name: str,
    sample_chunks: list[KnowledgeChunk],
) -> None:
    """写入后 count 应等于 chunks 数。"""
    try:
        n = upsert_chunks(sample_chunks, collection_name=temp_collection_name)
        assert n == len(sample_chunks)
        assert count(temp_collection_name) == len(sample_chunks)
    finally:
        reset_collection(temp_collection_name)


def test_query_returns_relevant(
    chroma_alive,
    embedder_ready,
    temp_collection_name: str,
    sample_chunks: list[KnowledgeChunk],
) -> None:
    """对相关 query 应返回正确 chunk。"""
    try:
        upsert_chunks(sample_chunks, collection_name=temp_collection_name)
        results = query("ITPM 是什么？", top_k=1, collection_name=temp_collection_name)
        assert len(results) == 1
        # 最相关的应当是 ITPM 那条
        assert "ITPM" in results[0].content
    finally:
        reset_collection(temp_collection_name)


def test_metadata_filter(
    chroma_alive,
    embedder_ready,
    temp_collection_name: str,
    sample_chunks: list[KnowledgeChunk],
) -> None:
    """where 过滤能限定来源文档。"""
    try:
        upsert_chunks(sample_chunks, collection_name=temp_collection_name)
        results = query(
            "管理",
            top_k=5,
            where={"source_doc": "docB"},
            collection_name=temp_collection_name,
        )
        # 全部命中应都来自 docB
        for r in results:
            assert r.metadata["source_doc"] == "docB"
    finally:
        reset_collection(temp_collection_name)


def test_delete_by_filter(
    chroma_alive,
    embedder_ready,
    temp_collection_name: str,
    sample_chunks: list[KnowledgeChunk],
) -> None:
    """按 metadata 删除后剩余数量正确。"""
    try:
        upsert_chunks(sample_chunks, collection_name=temp_collection_name)
        delete_by_filter(
            {"source_doc": "docA"},
            collection_name=temp_collection_name,
        )
        # docA 2 条删掉，应只剩 docB 那 1 条
        assert count(temp_collection_name) == 1
    finally:
        reset_collection(temp_collection_name)


def test_delete_without_filter_raises(chroma_alive) -> None:
    """delete_by_filter 必须有 where，防止误删全集合。"""
    with pytest.raises(ValueError, match="where"):
        delete_by_filter({})
