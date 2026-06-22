"""FastAPI 应用入口。

第一阶段（步骤 1.1）：先搭一个最小可启动的 FastAPI 服务，验证脚手架可用。
后续步骤会在此基础上逐步注册路由、SSE、Agent 等。
"""

from __future__ import annotations

from fastapi import FastAPI


def create_app() -> FastAPI:
    """应用工厂函数。

    用工厂模式而不是模块顶层直接 `app = FastAPI()`，原因有二：
    1. 测试时可以独立创建多个 app 实例，互不污染配置；
    2. 后续接入 lifespan、依赖注入、路由注册时，逻辑集中在一处。
    """
    app = FastAPI(
        title="PetroChat-Agent",
        description="石化领域智能问答与质检 Agent 平台",
        version="0.1.0",
    )

    # 健康检查 —— 用于验证服务是否启动，K8s / Docker healthcheck 也会用到
    @app.get("/health", summary="健康检查")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # 根路由 —— 给一个友好的欢迎信息
    @app.get("/", summary="根路由")
    async def root() -> dict[str, str]:
        return {
            "name": "PetroChat-Agent",
            "version": "0.1.0",
            "stage": "phase-1: RAG 问答",
            "docs": "/docs",
        }

    return app


# 模块级 app 实例，供 `uvicorn petrochat.main:app` 启动
app = create_app()
