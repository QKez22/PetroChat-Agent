"""LLM / Embedding 客户端工厂。

设计要点：
1. 按 "用途" 暴露工厂函数（get_chat_llm / get_reasoner_llm / get_embedding），
   调用方不需要关心底层是 DeepSeek 还是阿里云，便于后续替换模型。
2. DeepSeek 和阿里云百炼都通过 OpenAI 兼容协议调用，复用 langchain-openai 一个客户端，
   依赖更少，模型切换只是改 base_url + api_key + model。
3. 客户端实例化用 @lru_cache 缓存，避免每次请求都新建 HTTP 连接池。
4. temperature 等推理参数在工厂函数处提供合理默认值，调用方可覆盖。
"""

from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from .config import get_settings


@lru_cache(maxsize=1)
def get_chat_llm() -> ChatOpenAI:
    """获取 DeepSeek chat 客户端（用于 RAG 问答生成）。

    temperature=0.3 兼顾稳定性与表达自然度：
      - 太低 (0.0) 会让答案僵硬、复述检索片段；
      - 太高 (0.7+) 会让答案飘忽、引用对不上召回内容。
    """
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
    """获取 DeepSeek reasoner 客户端（用于后续质检评分的 LLM-as-Judge）。

    第一阶段不会用到，但提前定义好，第四阶段可以无缝切换。
    reasoner 模型不支持 temperature 参数（官方要求），传 None 让 langchain 跳过。
    """
    s = get_settings()
    return ChatOpenAI(
        model=s.deepseek_reasoner_model,
        api_key=s.deepseek_api_key,
        base_url=s.deepseek_base_url,
        timeout=120,  # 推理模型耗时更长
        max_retries=2,
    )


@lru_cache(maxsize=1)
def get_embedding() -> OpenAIEmbeddings:
    """获取阿里云百炼 Embedding 客户端（text-embedding-v3）。

    用 OpenAI 兼容协议直接调用，无需引入 dashscope SDK。
    dimensions=1024 是性能与成本的最佳平衡点（百炼官方推荐）。
    """
    s = get_settings()
    return OpenAIEmbeddings(
        model=s.embedding_model,
        api_key=s.dashscope_api_key,
        base_url=s.dashscope_base_url,
        dimensions=s.embedding_dim,
        # 阿里云百炼批量调用上限，超过会报错；保守取 10
        chunk_size=10,
    )
