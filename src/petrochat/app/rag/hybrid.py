"""中文 BM25 / RRF / 百炼重排；候选输入必须已按同一策略过滤。"""

from __future__ import annotations

import math
import re
from functools import lru_cache

import httpx
import jieba
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from ..core.config import get_settings


def tokenize(text: str) -> list[str]:
    text = text.casefold()
    return [w for w in jieba.cut(text) if w.strip()] + re.findall(
        r"[a-z0-9]+(?:[./_-][a-z0-9]+)*", text
    )


@lru_cache(maxsize=8)
def _index(texts: tuple[str, ...]) -> BM25Okapi:
    return BM25Okapi([tokenize(t) or ["<empty>"] for t in texts])


def keyword_search(query: str, docs: list[Document], k: int = 30) -> list[Document]:
    if not docs:
        return []
    scores = _index(
        tuple(str(d.metadata.get("section_path", "")) + " " + d.page_content for d in docs)
    ).get_scores(tokenize(query))
    order = sorted(range(len(docs)), key=lambda i: (-scores[i], str(docs[i].metadata["chunk_id"])))
    return [
        Document(
            page_content=docs[i].page_content,
            metadata={**docs[i].metadata, "bm25_score": float(scores[i])},
        )
        for i in order[:k]
        if scores[i] > 0
    ]


def fuse(*rankings: list[Document], k: int = 30) -> list[Document]:
    candidates: dict[str, Document] = {}
    scores: dict[str, float] = {}
    routes: dict[str, list[int]] = {}
    for route, ranking in enumerate(rankings):
        seen: set[str] = set()
        for rank, doc in enumerate(ranking, 1):
            key = str(doc.metadata["chunk_id"])
            if key in seen:
                continue
            seen.add(key)
            candidates.setdefault(key, doc)
            scores[key] = scores.get(key, 0) + 1 / (60 + rank)
            routes.setdefault(key, []).append(route)
    return [
        Document(
            page_content=candidates[key].page_content,
            metadata={
                **candidates[key].metadata,
                "rrf_score": scores[key],
                "retrieval_routes": routes[key],
            },
        )
        for key in sorted(scores, key=lambda key: (-scores[key], key))[:k]
    ]


def rerank(
    query: str, docs: list[Document], top_k: int = 5, *, contextual: bool = False
) -> list[Document]:
    if not docs:
        return []
    s = get_settings()
    if contextual:
        from .adaptive import contextual_text

        texts = [contextual_text(d) for d in docs]
    else:
        texts = [d.page_content for d in docs]
    try:
        response = httpx.post(
            s.rag_rerank_url,
            headers={"Authorization": f"Bearer {s.dashscope_api_key.get_secret_value()}"},
            json={
                "model": s.rag_rerank_model,
                "input": {"query": query, "documents": texts},
                "parameters": {"top_n": min(top_k, len(docs)), "return_documents": False},
            },
            timeout=s.rag_rerank_timeout_seconds,
        )
        response.raise_for_status()
        results = response.json()["output"]["results"]
        indices = [r["index"] for r in results]
        if len(indices) != min(top_k, len(docs)) or len(set(indices)) != len(indices):
            raise ValueError("invalid rerank cardinality")
        if any(type(i) is not int or not 0 <= i < len(docs) for i in indices):
            raise ValueError("invalid rerank index")
        if any(not math.isfinite(float(r["relevance_score"])) for r in results):
            raise ValueError("invalid rerank score")
        return [
            Document(
                page_content=docs[r["index"]].page_content,
                metadata={
                    **docs[r["index"]].metadata,
                    "rerank_score": float(r["relevance_score"]),
                    "rerank_status": "ok",
                },
            )
            for r in results
        ]
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        return [
            Document(
                page_content=d.page_content,
                metadata={**d.metadata, "rerank_status": f"fallback:{type(exc).__name__}"},
            )
            for d in docs[:top_k]
        ]
