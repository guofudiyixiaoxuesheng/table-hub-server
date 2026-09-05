"""汇总并注册所有 v1 业务路由。"""

from fastapi import APIRouter

from app.api.v1.analytics import router as analytics_router
from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.game_sessions import router as game_sessions_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.script_marketing import router as script_marketing_router
from app.api.v1.script_opening_manual import router as script_opening_manual_router
from app.api.v1.script_profiles import router as script_profiles_router
from app.api.v1.users import router as users_router

router = APIRouter(prefix="/api/v1")
router.include_router(analytics_router)
router.include_router(auth_router)
router.include_router(chat_router)
router.include_router(users_router)
router.include_router(knowledge_router)
router.include_router(game_sessions_router)
router.include_router(script_marketing_router)
router.include_router(script_opening_manual_router)
router.include_router(script_profiles_router)
