"""FastAPI 应用入口。

步骤 1.2 后：集成 core 配置，启动时输出加载到的关键配置摘要。
"""

from __future__ import annotations

from fastapi import FastAPI
from loguru import logger

from petrochat.app.core import get_settings


def create_app() -> FastAPI:
    """应用工厂函数。"""
    settings = get_settings()

    app = FastAPI(
        title="PetroChat-Agent",
        description="石化领域智能问答与质检 Agent 平台",
        version="0.1.0",
    )

    # 启动时打印配置摘要（不含敏感字段）
    logger.info(
        "App starting: env={} host={}:{} chroma={} embedding_model={} chat_model={}",
        settings.app_env,
        settings.app_host,
        settings.app_port,
        settings.chroma_url,
        settings.embedding_model,
        settings.deepseek_chat_model,
    )

    @app.get("/health", summary="健康检查")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", summary="根路由")
    async def root() -> dict[str, str]:
        return {
            "name": "PetroChat-Agent",
            "version": "0.1.0",
            "stage": "phase-1: RAG 问答",
            "docs": "/docs",
        }

    @app.get("/config", summary="当前配置摘要（不含敏感字段）")
    async def config_summary() -> dict[str, object]:
        """暴露非敏感配置，方便确认环境变量是否正确加载。

        SecretStr 字段只返回是否非空，不返回明文。
        """
        s = get_settings()
        return {
            "app_env": s.app_env,
            "chroma_url": s.chroma_url,
            "chroma_collection": s.chroma_collection,
            "chat_model": s.deepseek_chat_model,
            "reasoner_model": s.deepseek_reasoner_model,
            "embedding_model": s.embedding_model,
            "embedding_dim": s.embedding_dim,
            "deepseek_api_key_set": bool(s.deepseek_api_key.get_secret_value()),
            "dashscope_api_key_set": bool(s.dashscope_api_key.get_secret_value()),
            "langsmith_tracing": s.langsmith_tracing,
            "langsmith_project": s.langsmith_project,
        }

    return app


app = create_app()
