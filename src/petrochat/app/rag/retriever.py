"""LangChain BaseRetriever 适配 PetroChat 向量库。

为什么搞这一层（而不是直接用 vector_store.query）：
1. 继承 BaseRetriever 后，retriever.invoke(query) 自动出现在 LangSmith trace 里；
2. 返回 LangChain Document 对象，能直接喂给 prompt 模板和 LangGraph 节点；
3. 把"过滤/阈值/集合名"参数化到一个对象上，调用方拿一个 retriever 用到底，
   不用每次 query 都重复传一堆 kwargs。
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field

from ..core.config import get_settings
from .vector_store import get_chunks
from .vector_store import query as _vector_query


class PetrochatRetriever(BaseRetriever):
    """从 Chroma 检索石化规范条款。

    用法：
        retriever = PetrochatRetriever(top_k=5)
        docs = retriever.invoke("什么是 ITPM 策略？")

        # 限定到某个文件
        retriever = PetrochatRetriever(
            top_k=5,
            where_filter={"source_doc": "2.《高桥石化备品配件管理细则》..."},
        )
    """

    top_k: int = Field(default=5, description="返回前 K 条")
    mode: str | None = None
    score_threshold: float | None = Field(
        default=None,
        description="cosine distance 阈值，越大保留越多。None 表示不过滤。"
        "经验：百炼 v3 的 cosine distance，相关条款通常 < 0.6。",
    )
    collection_name: str | None = Field(
        default=None,
        description="Chroma 集合名，None 取 settings.chroma_collection。",
    )
    where_filter: dict[str, Any] | None = Field(
        default=None,
        description="Chroma 原生 where 子句，如 {'source_doc': 'xxx'}。",
    )

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        mode = self.mode or get_settings().rag_mode
        if mode not in {"vector", "hybrid", "hybrid_rerank", "adaptive_hybrid"}:
            raise ValueError("unknown retrieval mode")
        candidate_k = max(self.top_k, get_settings().rag_candidate_k)
        if mode == "adaptive_hybrid":
            from .adaptive import adaptive_search

            corpus = [
                Document(page_content=r.content, metadata={**r.metadata, "chunk_id": r.chunk_id})
                for r in get_chunks(where=self.where_filter, collection_name=self.collection_name)
            ]

            def scoped_vector(question, k, source):
                where = self.where_filter
                if source:
                    source_filter = {"source_doc": source}
                    where = {"$and": [where, source_filter]} if where else source_filter
                results = _vector_query(
                    query_text=question, top_k=k, where=where, collection_name=self.collection_name
                )
                return [
                    Document(
                        page_content=r.content,
                        metadata={**r.metadata, "chunk_id": r.chunk_id, "score": r.score},
                    )
                    for r in results
                    if self.score_threshold is None or r.score <= self.score_threshold
                ]

            return adaptive_search(
                query, corpus, scoped_vector, top_k=self.top_k, candidate_k=candidate_k
            )
        retrieved = _vector_query(
            query_text=query,
            top_k=self.top_k if mode == "vector" else candidate_k,
            where=self.where_filter,
            collection_name=self.collection_name,
        )

        if self.score_threshold is not None:
            retrieved = [r for r in retrieved if r.score <= self.score_threshold]

        docs = [
            Document(
                page_content=r.content,
                metadata={
                    "chunk_id": r.chunk_id,
                    "score": r.score,
                    # 展平 chunk 的元数据，便于 prompt 直接读
                    **{k: v for k, v in r.metadata.items()},
                },
            )
            for r in retrieved
        ]
        if mode == "vector":
            return docs
        from .hybrid import fuse, keyword_search, rerank

        corpus = [
            Document(page_content=r.content, metadata={**r.metadata, "chunk_id": r.chunk_id})
            for r in get_chunks(where=self.where_filter, collection_name=self.collection_name)
        ]
        merged = fuse(docs, keyword_search(query, corpus, candidate_k), k=candidate_k)
        return (
            rerank(query, merged, self.top_k) if mode == "hybrid_rerank" else merged[: self.top_k]
        )


# ============================================================
# 引用格式化（与检索逻辑解耦，问答节点 / API 都可调用）
# ============================================================

# 用于剔除文件名前缀的 "1." "2.《..." 这类计数前缀
_FILE_PREFIX_PAT = re.compile(r"^\d+[.、\s]*")


def format_citation(metadata: dict[str, Any]) -> str:
    """从单条 metadata 生成用户可读引用串。

    输入示例:
        {"source_doc": "2.《高桥石化备品配件管理细则》（2025年2月修订稿）",
         "section_number": "3.1.2", ...}
    输出:
        "《高桥石化备品配件管理细则》 3.1.2"
    """
    src = metadata.get("source_doc", "未知文档")
    sec = metadata.get("section_number", "").strip()
    # 去前缀编号
    src_clean = _FILE_PREFIX_PAT.sub("", src).strip()
    # 版本是证据身份的一部分，不得抹掉修订稿等标记。
    # 已经带《》就不再加，没有的话加上
    if not src_clean.startswith("《"):
        src_clean = f"《{src_clean}》"
    return f"{src_clean} {sec}".strip()


def format_citations(documents: list[Document]) -> list[str]:
    """批量从 Document 列表生成引用串，**保持文档顺序去重**。"""
    seen: set[str] = set()
    out: list[str] = []
    for d in documents:
        c = format_citation(d.metadata)
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def make_retriever(
    top_k: int = 5,
    score_threshold: float | None = None,
    where: dict[str, Any] | None = None,
    collection: str | None = None,
    mode: str | None = None,
) -> PetrochatRetriever:
    """检索器工厂，给常用配置一个短调用形式。"""
    return PetrochatRetriever(
        top_k=top_k,
        score_threshold=score_threshold,
        where_filter=where,
        collection_name=collection,
        mode=mode,
    )
