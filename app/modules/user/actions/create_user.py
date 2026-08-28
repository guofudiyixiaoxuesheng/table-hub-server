"""创建普通用户业务用例。"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.user.exceptions import UserPhoneAlreadyExistsError
from app.modules.user.models import User, UserRole
from app.modules.user.repositories import add_user, get_user_by_phone
from app.modules.user.schemas import CreateUserRequest, UserResponse


async def create_user_action(
    payload: CreateUserRequest,
    db: AsyncSession,
) -> UserResponse:
    """校验手机号唯一性并创建普通用户。"""

    if await get_user_by_phone(payload.phone, db):
        raise UserPhoneAlreadyExistsError

    user = User(
        phone=payload.phone,
        nickname=payload.nickname,
        avatar_url=payload.avatar_url,
        role=UserRole.USER,
    )

    try:
        user = await add_user(user, db)
    except IntegrityError as error:
        await db.rollback()
        raise UserPhoneAlreadyExistsError from error

    return UserResponse.model_validate(user)
