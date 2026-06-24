"""API 层：认证、问答路由与 SSE 流式输出。"""

from fastapi import APIRouter

from .auth import router as auth_router
from .routes import router as chat_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(chat_router)

__all__ = ["router"]
