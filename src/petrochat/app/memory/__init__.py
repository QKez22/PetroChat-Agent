"""Conversation memory utilities.

Phase 5 starts with a conservative memory layer:
- persist conversations and messages in MySQL application tables;
- load a bounded short-term window into LangGraph state;
- keep NL2SQL business-table access read-only.

Phase 6 adds explicit and auditable long-term memory tables, plus conservative
recall and write-back helpers for Agent context.
"""

from .context import (
    MemoryWriteResult,
    RecalledMemory,
    augment_question_with_memory,
    build_memory_system_message,
    extract_memory_candidates,
    recall_long_term_memories,
    write_memory_candidates,
)
from .long_term import LongTermMemoryStore, MemoryEvent, MemoryItem, get_long_term_memory_store
from .store import ConversationStore, StoredMessage, get_conversation_store

__all__ = [
    "ConversationStore",
    "LongTermMemoryStore",
    "MemoryEvent",
    "MemoryItem",
    "MemoryWriteResult",
    "RecalledMemory",
    "StoredMessage",
    "augment_question_with_memory",
    "build_memory_system_message",
    "extract_memory_candidates",
    "get_conversation_store",
    "get_long_term_memory_store",
    "recall_long_term_memories",
    "write_memory_candidates",
]
