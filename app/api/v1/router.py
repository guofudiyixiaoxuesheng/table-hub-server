"""汇总并注册所有 v1 业务路由。"""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.users import router as users_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(chat_router)
router.include_router(users_router)
router.include_router(knowledge_router)
