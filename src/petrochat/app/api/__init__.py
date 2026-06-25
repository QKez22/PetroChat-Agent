"""API 层：认证、问答路由与 SSE 流式输出。"""

from fastapi import APIRouter

from .admin import router as admin_router
from .auth import router as auth_router
from .evaluation import router as evaluation_router
from .memory import router as memory_router
from .routes import router as chat_router

router = APIRouter()
router.include_router(admin_router)
router.include_router(auth_router)
router.include_router(chat_router)
router.include_router(evaluation_router)
router.include_router(memory_router)

__all__ = ["router"]
