"""Conversation memory utilities.

Phase 5 starts with a conservative memory layer:
- persist conversations and messages in MySQL application tables;
- load a bounded short-term window into LangGraph state;
- keep NL2SQL business-table access read-only.

Phase 6 adds explicit and auditable long-term memory tables. Automatic
extraction/retrieval is introduced in later phases.
"""

from .long_term import LongTermMemoryStore, MemoryEvent, MemoryItem, get_long_term_memory_store
from .store import ConversationStore, StoredMessage, get_conversation_store

__all__ = [
    "ConversationStore",
    "LongTermMemoryStore",
    "MemoryEvent",
    "MemoryItem",
    "StoredMessage",
    "get_conversation_store",
    "get_long_term_memory_store",
]
