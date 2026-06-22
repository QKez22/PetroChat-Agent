"""可观测性接入：LangSmith 追踪。

为什么需要这个桥接函数：
  pydantic-settings 只把 .env 里的值装进 Settings 对象，
  **不会反写回 os.environ**。
  LangChain 0.3+ 是通过检测 os.environ 里的 LANGSMITH_* 启用追踪的，
  所以我们要在应用启动时主动把 Settings 字段同步到 os.environ。
"""

from __future__ import annotations

import os

from loguru import logger

from .config import get_settings


def setup_langsmith() -> bool:
    """根据 .env 配置启用 LangSmith 追踪。

    Returns:
        True 表示已成功启用追踪；False 表示跳过（未配置或 key 缺失）。
    """
    s = get_settings()
    if not s.langsmith_tracing:
        return False

    key = s.langsmith_api_key.get_secret_value()
    if not key:
        logger.warning("LANGSMITH_TRACING=true 但 LANGSMITH_API_KEY 未设置，跳过追踪")
        return False

    # 新版（LangChain 0.3+）环境变量
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = key
    os.environ["LANGSMITH_PROJECT"] = s.langsmith_project
    os.environ["LANGSMITH_ENDPOINT"] = s.langsmith_endpoint
    # 兼容旧名（避免老版本组件不识别）
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = key
    os.environ["LANGCHAIN_PROJECT"] = s.langsmith_project
    os.environ["LANGCHAIN_ENDPOINT"] = s.langsmith_endpoint

    logger.info("LangSmith 追踪已启用: project={}", s.langsmith_project)
    return True
