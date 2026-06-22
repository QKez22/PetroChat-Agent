"""核心层：配置、状态、实体、LLM 客户端。

最底层包，不依赖其他业务包。其它包通过这些公共导出获取基础能力。
"""

from .config import Settings, get_settings
from .llm import get_chat_llm, get_embedding, get_reasoner_llm
from .models import (
    ChatRequest,
    ChatResponse,
    KnowledgeChunk,
    RetrievedChunk,
    ScoreResult,
)
from .state import AgentState, NextNode

__all__ = [
    # config
    "Settings",
    "get_settings",
    # llm clients
    "get_chat_llm",
    "get_reasoner_llm",
    "get_embedding",
    # state
    "AgentState",
    "NextNode",
    # models
    "ChatRequest",
    "ChatResponse",
    "KnowledgeChunk",
    "RetrievedChunk",
    "ScoreResult",
]
