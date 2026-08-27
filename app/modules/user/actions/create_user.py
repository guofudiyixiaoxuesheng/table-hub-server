"""创建普通用户业务用例。"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.user.exceptions import UserPhoneAlreadyExistsError
from app.modules.user.models import User, UserRole
from app.modules.user.repositories import UserRepository
from app.modules.user.schemas import CreateUserRequest


class CreateUserAction:
    """校验手机号唯一性并创建普通用户。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = UserRepository(session)

    async def execute(self, request: CreateUserRequest) -> User:
        """执行创建普通用户用例。"""

        if await self.repository.get_by_phone(request.phone):
            raise UserPhoneAlreadyExistsError

        user = User(
            phone=request.phone,
            nickname=request.nickname,
            avatar_url=request.avatar_url,
            role=UserRole.USER,
        )

        try:
            return await self.repository.add(user)
        except IntegrityError as error:
            await self.session.rollback()
            raise UserPhoneAlreadyExistsError from error
