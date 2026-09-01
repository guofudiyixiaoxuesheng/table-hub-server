"""汇总用户模块的独立路由文件。"""

from fastapi import APIRouter

from app.api.v1.users.routes.create_user import router as create_user_router
from app.api.v1.users.routes.manage_players import router as manage_players_router

router = APIRouter(tags=["users"])
router.include_router(create_user_router)
router.include_router(manage_players_router)
