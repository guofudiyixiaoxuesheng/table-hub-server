"""用户数据访问函数。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.user.models import User


async def get_user_by_phone(phone: str, db: AsyncSession) -> User | None:
    """根据手机号查找未被软删除的用户。"""

    statement = select(User).where(User.phone == phone, User.deleted_at.is_(None))
    return await db.scalar(statement)


async def add_user(user: User, db: AsyncSession) -> User:
    """写入用户并刷新数据库生成字段。"""

    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user
