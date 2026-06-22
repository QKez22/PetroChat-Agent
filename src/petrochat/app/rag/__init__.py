"""RAG 层：文档解析、Embedding、向量库 CRUD、检索。

依赖：core
"""

from .parser import parse_docx
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
    # 解析
    "parse_docx",
    # 向量库操作
    "get_client",
    "get_or_create_collection",
    "upsert_chunks",
    "query",
    "delete_by_filter",
    "count",
    "reset_collection",
]
