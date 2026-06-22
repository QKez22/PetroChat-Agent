"""LLM / Embedding 客户端工厂。

按用途暴露 get_chat_llm / get_reasoner_llm / get_embedding，调用方不关心底层。
DeepSeek 和阿里云百炼均通过 OpenAI 兼容协议调用，共用 langchain-openai。
"""

from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from .config import get_settings


@lru_cache(maxsize=1)
def get_chat_llm() -> ChatOpenAI:
    """DeepSeek chat（用于 RAG 答案生成）。"""
    s = get_settings()
    return ChatOpenAI(
        model=s.deepseek_chat_model,
        api_key=s.deepseek_api_key,
        base_url=s.deepseek_base_url,
        temperature=0.3,
        timeout=60,
        max_retries=2,
    )


@lru_cache(maxsize=1)
def get_reasoner_llm() -> ChatOpenAI:
    """DeepSeek reasoner（后续第四阶段做评分 Judge）。"""
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
    """阿里云百炼 text-embedding-v3。

    关键参数：
      check_embedding_ctx_length=False
        LangChain 默认会用 tiktoken 把字符串本地切成 token ID 再发，
        OpenAI 官方接口接受 token ID，但**百炼兼容层只认纯字符串**，
        不关掉会报 400 'input.contents is neither str nor list of str'。
        国内厂商走 OpenAI 兼容协议的通用坑。
      chunk_size=embedding_batch_size
        百炼实测批量上限 10（超过会报 400），用配置项暴露便于切厂商。
    """
    s = get_settings()
    return OpenAIEmbeddings(
        model=s.embedding_model,
        api_key=s.dashscope_api_key,
        base_url=s.dashscope_base_url,
        dimensions=s.embedding_dim,
        chunk_size=s.embedding_batch_size,
        check_embedding_ctx_length=False,
    )
