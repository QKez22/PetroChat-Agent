"""第二轮：显式文档范围、去重复上下文、双路一致时跳过重排。"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from functools import lru_cache

import jieba
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from .hybrid import fuse, rerank

_QUESTION_WORDS = {
    "的",
    "了",
    "是",
    "什么",
    "哪些",
    "如何",
    "是否",
    "怎样",
    "请问",
    "多少",
    "怎么",
    "吗",
    "？",
    "?",
}


def parent_context(doc: Document) -> str:
    """编号即正文时不把整个叶条款重复一遍；保留上级职责等消歧信息。"""
    parts = str(doc.metadata.get("section_path", "")).split(" > ")
    return " > ".join(p for p in parts if p and p != "preamble" and p not in doc.page_content)


def contextual_text(doc: Document) -> str:
    return f"文档：{doc.metadata.get('source_doc', '')}\n上级条款：{parent_context(doc)}\n原文：{doc.page_content}"


def search_tokens(text: str) -> list[str]:
    text = text.casefold()
    words = [
        w
        for w in jieba.cut_for_search(text)
        if w.strip() and w not in _QUESTION_WORDS and re.search(r"[\w\u4e00-\u9fff]", w)
    ]
    return words + re.findall(r"[a-z0-9]+(?:[./_-][a-z0-9]+)+", text)


@lru_cache(maxsize=8)
def _index(texts: tuple[str, ...]):
    return BM25Okapi([search_tokens(t) or ["<empty>"] for t in texts])


def lexical_search(query: str, docs: list[Document], k: int = 30) -> list[Document]:
    if not docs:
        return []
    scores = _index(tuple(parent_context(d) + "\n" + d.page_content for d in docs)).get_scores(
        search_tokens(query)
    )
    order = sorted(range(len(docs)), key=lambda i: (-scores[i], str(docs[i].metadata["chunk_id"])))
    return [
        Document(
            page_content=docs[i].page_content,
            metadata={**docs[i].metadata, "bm25_score": float(scores[i])},
        )
        for i in order[:k]
        if scores[i] > 0
    ]


def explicit_source(query: str, docs: list[Document]) -> tuple[str | None, str]:
    """只接受已授权来源标题中的唯一连续长片段；比较/多文档问题不缩范围。"""
    if re.search(r"对比|比较|分别|两份|多份|不同规范|各规范|所有规范", query):
        return None, query
    matches = []
    for source in sorted({str(d.metadata.get("source_doc", "")) for d in docs}):
        title = re.sub(r"[（(].*?[）)]", "", source)
        title = re.sub(r"^\d+[.、\s]*", "", title).strip("《》 ")
        match = SequenceMatcher(
            None, query.casefold(), title.casefold(), autojunk=False
        ).find_longest_match()
        if match.size >= 6:
            fragment = query[match.a : match.a + match.size]
            matches.append((source, fragment))
    if len(matches) != 1:
        return None, query
    source, fragment = matches[0]
    remaining = query.replace(fragment, " ").strip(" 《》：:，,。？? ")
    # 只有文档名称、没有问题时不能生成空检索。
    return (source, remaining) if len(remaining) >= 2 else (None, query)


def adaptive_search(
    query: str, corpus: list[Document], vector_search, *, top_k: int = 5, candidate_k: int = 30
) -> list[Document]:
    source, search_query = explicit_source(query, corpus)
    scoped = [d for d in corpus if d.metadata.get("source_doc") == source] if source else corpus
    vectors = vector_search(search_query, candidate_k, source)
    lexical = lexical_search(search_query, scoped, candidate_k)
    merged = fuse(vectors, lexical, k=candidate_k)
    # 两个独立检索器首选一致时保留 RRF；避免不必要的模型调用和排序扰动。
    agreement = bool(
        vectors and lexical and vectors[0].metadata["chunk_id"] == lexical[0].metadata["chunk_id"]
    )
    result = merged[:top_k] if agreement else rerank(search_query, merged, top_k, contextual=True)
    return [
        Document(
            page_content=d.page_content,
            metadata={
                **d.metadata,
                "retrieval_mode": "adaptive_hybrid",
                "explicit_source_scope": source or "",
                "rerank_status": "skipped:agreement"
                if agreement
                else d.metadata.get("rerank_status", "not_needed"),
            },
        )
        for d in result
    ]
