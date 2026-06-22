"""RAG 层：文档解析、Embedding、向量库 CRUD、检索器。"""

from .parser import parse_docx
from .retriever import (
    PetrochatRetriever,
    format_citation,
    format_citations,
    make_retriever,
)
from .vector_store import (
    count,
    delete_by_filter,
    get_client,
    get_or_create_collection,
    query,
    reset_collection,
    upsert_chunks,
)

__all__ = [
    "parse_docx",
    "get_client",
    "get_or_create_collection",
    "upsert_chunks",
    "query",
    "delete_by_filter",
    "count",
    "reset_collection",
    "PetrochatRetriever",
    "make_retriever",
    "format_citation",
    "format_citations",
]
