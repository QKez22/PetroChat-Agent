"""FastAPI 应用入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from petrochat.app.api import router as api_router
from petrochat.app.core import get_settings, setup_langsmith


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭钩子。"""
    settings = get_settings()
    setup_langsmith()

    # 启用 MCP 时, 启动期一次性连接 MCP Server 并拉取工具列表。
    # MCP 是工具暴露方式，不应成为普通问答的单点故障；失败时运行期会降级到本地工具。
    if settings.mcp_enabled:
        from petrochat.app.mcp import init_mcp_tools_async
        try:
            await init_mcp_tools_async()
        except Exception as exc:
            logger.warning("MCP 工具启动初始化失败，将在运行期降级本地工具: {}", exc)

    logger.info("App ready: env={} mcp_enabled={} chroma={} chat_model={}",
                settings.app_env, settings.mcp_enabled,
                settings.chroma_url, settings.deepseek_chat_model)
    yield
    logger.info("App shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="PetroChat-Agent",
        description="石化领域智能问答与多 Agent 数据分析平台",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/")
    async def root():
        return {
            "name": "PetroChat-Agent",
            "version": "1.0.0",
            "stage": "v1.0-multiagent",
            "docs": "/docs",
        }

    @app.get("/config")
    async def config_summary():
        s = get_settings()
        return {
            "app_env": s.app_env,
            "chroma_url": s.chroma_url,
            "chroma_collection": s.chroma_collection,
            "chat_model": s.deepseek_chat_model,
            "reasoner_model": s.deepseek_reasoner_model,
            "embedding_model": s.embedding_model,
            "embedding_dim": s.embedding_dim,
            "mcp_enabled": s.mcp_enabled,
            "mcp_transport": s.mcp_transport,
            "deepseek_api_key_set": bool(s.deepseek_api_key.get_secret_value()),
            "dashscope_api_key_set": bool(s.dashscope_api_key.get_secret_value()),
            "langsmith_tracing": s.langsmith_tracing,
            "langsmith_project": s.langsmith_project,
        }

    return app


app = create_app()
