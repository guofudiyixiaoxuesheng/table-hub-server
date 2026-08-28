"""创建普通用户接口。"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.database import get_database
from app.modules.user.actions import create_user_action
from app.modules.user.schemas import CreateUserRequest

router = APIRouter()


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest,
    db: AsyncSession = Depends(get_database),
):
    """通过手机号创建普通用户，角色固定为 user。"""

    data = await create_user_action(payload, db)
    return success_response(message="创建用户成功", data=data)
