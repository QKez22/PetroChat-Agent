"""LLM / Embedding 客户端工厂。"""

from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from .config import get_settings


@lru_cache(maxsize=1)
def get_chat_llm() -> ChatOpenAI:
    """DeepSeek chat（用于 RAG 答案生成）。streaming=True 让 invoke 内部也走流式 API，token chunks 通过 LangChain callback 冒泡。"""
    s = get_settings()
    return ChatOpenAI(
        model=s.deepseek_chat_model,
        api_key=s.deepseek_api_key,
        base_url=s.deepseek_base_url,
        temperature=0.3,
        timeout=60,
        max_retries=2,
        streaming=True,
    )


@lru_cache(maxsize=1)
def get_reasoner_llm() -> ChatOpenAI:
    s = get_settings()
    return ChatOpenAI(
        model=s.deepseek_reasoner_model,
        api_key=s.deepseek_api_key,
        base_url=s.deepseek_base_url,
        timeout=120,
        max_retries=2,
    )


@lru_cache(maxsize=1)
def get_embedding() -> OpenAIEmbeddings:
    """阿里云百炼 v3。check_embedding_ctx_length=False 关掉本地 tokenize（百炼只认字符串）。chunk_size 取自配置（百炼上限 10）。"""
    s = get_settings()
    return OpenAIEmbeddings(
        model=s.embedding_model,
        api_key=s.dashscope_api_key,
        base_url=s.dashscope_base_url,
        dimensions=s.embedding_dim,
        chunk_size=s.embedding_batch_size,
        check_embedding_ctx_length=False,
    )
