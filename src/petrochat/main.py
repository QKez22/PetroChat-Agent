"""FastAPI 应用入口。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from petrochat.app.api import router as api_router
from petrochat.app.core import get_settings, setup_langsmith


def create_app() -> FastAPI:
    settings = get_settings()
    setup_langsmith()

    app = FastAPI(
        title="PetroChat-Agent",
        description="石化领域智能问答与质检 Agent 平台",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("App starting: env={} chroma={} chat_model={}",
                settings.app_env, settings.chroma_url, settings.deepseek_chat_model)
    app.include_router(api_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/")
    async def root():
        return {
            "name": "PetroChat-Agent",
            "version": "0.1.0",
            "stage": "phase-1: RAG 问答",
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
            "deepseek_api_key_set": bool(s.deepseek_api_key.get_secret_value()),
            "dashscope_api_key_set": bool(s.dashscope_api_key.get_secret_value()),
            "langsmith_tracing": s.langsmith_tracing,
            "langsmith_project": s.langsmith_project,
        }

    return app


app = create_app()
