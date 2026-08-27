"""汇总并注册所有 v1 业务路由。"""

from fastapi import APIRouter

from app.api.v1.users import router as users_router

router = APIRouter(prefix="/api/v1")
router.include_router(users_router)
