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
from .mem0_adapter import Mem0Candidate, Mem0MemoryAdapter, Mem0SearchResult, get_mem0_memory_adapter
from .policy import (
    MemoryRecallPolicy,
    accept_mem0_candidate,
    build_recall_policy,
    should_extract_memory,
    validate_memory_candidate,
)
from .store import ConversationStore, StoredMessage, get_conversation_store
from .summary import (
    PromptContextBudgetResult,
    SummaryUpdateResult,
    build_conversation_summary_message,
    fit_prompt_context,
    refresh_conversation_summary,
)

__all__ = [
    "ConversationStore",
    "LongTermMemoryStore",
    "Mem0Candidate",
    "Mem0MemoryAdapter",
    "Mem0SearchResult",
    "MemoryRecallPolicy",
    "MemoryEvent",
    "MemoryItem",
    "MemoryWriteResult",
    "PromptContextBudgetResult",
    "RecalledMemory",
    "SummaryUpdateResult",
    "StoredMessage",
    "augment_question_with_memory",
    "accept_mem0_candidate",
    "build_memory_system_message",
    "build_conversation_summary_message",
    "build_recall_policy",
    "extract_memory_candidates",
    "fit_prompt_context",
    "get_conversation_store",
    "get_long_term_memory_store",
    "get_mem0_memory_adapter",
    "recall_long_term_memories",
    "refresh_conversation_summary",
    "should_extract_memory",
    "validate_memory_candidate",
    "write_memory_candidates",
]
