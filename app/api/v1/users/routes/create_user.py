"""创建普通用户接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import ApiResponse
from app.core.database import get_database
from app.modules.user.actions import CreateUserAction
from app.modules.user.schemas import CreateUserRequest, UserResponse

router = APIRouter()
DatabaseSession = Annotated[AsyncSession, Depends(get_database)]


@router.post(
    "/users",
    response_model=ApiResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    summary="创建普通用户",
)
async def create_user(
    request: CreateUserRequest,
    session: DatabaseSession,
) -> ApiResponse[UserResponse]:
    """通过手机号创建普通用户，角色固定为 user。"""

    user = await CreateUserAction(session).execute(request)
    return ApiResponse(data=UserResponse.model_validate(user))
