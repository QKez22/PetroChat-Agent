"""Chroma 向量库原子操作。

设计意图（学习目标）：
  不使用 langchain-chroma 的高层封装，直接用 chromadb.HttpClient 暴露每个原始操作，
  你能看清"文本 → 向量 → 元数据 → 入库 → 检索"的全链路。

约定：
  - 集合名缺省取 settings.chroma_collection；测试可指定不同名。
  - 距离度量显式选 cosine（百炼 embedding 是归一化向量，cosine 比 L2 更直觉）。
  - embedding 在 upsert / query 内部完成，调用方只关心文本与元数据。
  - Chroma metadata 只接受 str/int/float/bool，所以 KnowledgeChunk.to_metadata() 已做转换。
"""

from __future__ import annotations

import os
from functools import lru_cache

# 关掉 chromadb 客户端的匿名遥测（避免日志里出现 posthog 失败警告）
# 必须在 import chromadb 之前设置才能生效
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_IMPL", "none")

import chromadb  # noqa: E402
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from loguru import logger

from ..core.config import get_settings
from ..core.llm import get_embedding
from ..core.models import KnowledgeChunk, RetrievedChunk

# Chroma collection 元数据：固定 cosine 距离
_COLLECTION_META = {"hnsw:space": "cosine"}


@lru_cache(maxsize=1)
def get_client() -> ClientAPI:
    """获取 Chroma HTTP 客户端单例。

    单例化避免重复建立 HTTP 连接池。第一次调用会做一次握手验证，
    Chroma 服务未启动时这里会抛 ConnectionError。
    """
    s = get_settings()
    client = chromadb.HttpClient(host=s.chroma_host, port=s.chroma_port)
    # 主动 heartbeat 一次：早失败优于晚失败
    client.heartbeat()
    logger.info("Chroma 连接就绪: {}", s.chroma_url)
    return client


def get_or_create_collection(name: str | None = None) -> Collection:
    """获取或创建集合（类似关系库的 CREATE TABLE IF NOT EXISTS）。

    Args:
        name: 集合名，缺省取 settings.chroma_collection。
    """
    s = get_settings()
    coll_name = name or s.chroma_collection
    client = get_client()
    return client.get_or_create_collection(
        name=coll_name,
        metadata=_COLLECTION_META,
    )


def upsert_chunks(
    chunks: list[KnowledgeChunk],
    collection_name: str | None = None,
    batch_size: int = 100,
) -> int:
    """把 KnowledgeChunk 列表批量嵌入并写入向量库。

    Args:
        chunks: 待入库的 chunk 列表。空列表直接返回 0。
        collection_name: 目标集合名。
        batch_size: 每批次写库的 chunk 数。注意 embedding 的实际批量
                    由 OpenAIEmbeddings 的 chunk_size 控制（在 core/llm.py 里）。

    Returns:
        实际写入的 chunk 数。
    """
    if not chunks:
        return 0

    collection = get_or_create_collection(collection_name)
    embedder = get_embedding()

    total = 0
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        ids = [c.chunk_id for c in batch]
        documents = [c.content for c in batch]
        metadatas = [c.to_metadata() for c in batch]

        # 关键步骤：把文本批量送进 embedding API，拿到 list[list[float]]
        embeddings = embedder.embed_documents(documents)

        # 用 upsert 而非 add：同 id 自动覆盖，幂等。开发期反复 ingest 不会爆主键
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        total += len(batch)
        logger.info("upsert {}/{} chunks", total, len(chunks))

    return total


def query(
    query_text: str,
    top_k: int = 5,
    where: dict | None = None,
    collection_name: str | None = None,
) -> list[RetrievedChunk]:
    """向量相似度检索。

    Args:
        query_text: 用户查询。会被嵌入成向量后做 ANN 搜索。
        top_k: 返回前 K 条结果。
        where: Chroma 原生 metadata 过滤语法。
               示例 {"source_doc": "高桥..."} 或 {"chunk_type": {"$eq": "clause"}}
               详见 https://docs.trychroma.com/usage-guide#using-where-filters
        collection_name: 集合名。

    Returns:
        按相似度排序的 RetrievedChunk 列表（score 越小越相关，cosine distance）。
    """
    collection = get_or_create_collection(collection_name)
    embedder = get_embedding()

    # 查询向量（注意 embed_query 跟 embed_documents 在某些模型上有不同 prompt prefix）
    query_emb = embedder.embed_query(query_text)

    result = collection.query(
        query_embeddings=[query_emb],
        n_results=top_k,
        where=where,
    )

    # Chroma 返回的是 list[list[...]]（支持多 query 批查），我们只取第 0 个
    ids_list = result["ids"][0]
    docs_list = result["documents"][0]
    metas_list = result["metadatas"][0]
    dists_list = result["distances"][0]

    return [
        RetrievedChunk(
            chunk_id=cid,
            content=doc,
            metadata=meta or {},
            score=float(dist),
        )
        for cid, doc, meta, dist in zip(
            ids_list, docs_list, metas_list, dists_list, strict=True
        )
    ]


def delete_by_filter(
    where: dict,
    collection_name: str | None = None,
) -> None:
    """按 metadata 条件删除 chunk。

    Args:
        where: Chroma 过滤语法。**必填**，避免误删全集合。
        collection_name: 集合名。
    """
    if not where:
        raise ValueError("delete_by_filter 必须传 where，避免误删全集合")
    collection = get_or_create_collection(collection_name)
    collection.delete(where=where)
    logger.info("已按条件删除: {}", where)


def count(collection_name: str | None = None) -> int:
    """集合内 chunk 总数（用于核对入库结果）。"""
    return get_or_create_collection(collection_name).count()


def reset_collection(collection_name: str | None = None) -> None:
    """删除整个集合（开发期重建用）。

    生产慎用：Chroma 不可恢复。
    """
    s = get_settings()
    coll_name = collection_name or s.chroma_collection
    client = get_client()
    try:
        client.delete_collection(name=coll_name)
        logger.warning("已删除集合: {}", coll_name)
    except Exception as e:
        # 集合不存在时 Chroma 抛 NotFoundError，吞掉
        logger.info("集合不存在或删除失败: {} ({})", coll_name, e)
