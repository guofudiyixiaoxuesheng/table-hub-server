"""用户数据访问封装。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.user.models import User


class UserRepository:
    """只负责用户持久化，不包含业务判断。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_phone(self, phone: str) -> User | None:
        """根据手机号查找未被软删除的用户。"""

        statement = select(User).where(User.phone == phone, User.deleted_at.is_(None))
        return await self.session.scalar(statement)

    async def add(self, user: User) -> User:
        """写入用户并刷新数据库生成字段。"""

        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user
