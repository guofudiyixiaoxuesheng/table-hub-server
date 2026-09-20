"""认证相关数据库访问。"""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.modules.auth.models import RefreshToken, StoreInvite, StoreMember
from app.modules.user.models import User


async def get_login_identity(
    phone: str, db: AsyncSession
) -> tuple[User, StoreMember | None] | None:
    user = await db.scalar(
        select(User).where(
            User.phone == phone,
            User.deleted_at.is_(None),
            User.status == "active",
        )
    )
    if user is None:
        return None
    statement = (
        select(StoreMember)
        .where(
            StoreMember.user_id == user.id,
            StoreMember.status == "active",
        )
        .options(joinedload(StoreMember.user), joinedload(StoreMember.store))
        .order_by(StoreMember.created_at)
    )
    membership = await db.scalar(statement)
    return user, membership


async def get_user(user_id: uuid.UUID, db: AsyncSession) -> User | None:
    return await db.scalar(
        select(User).where(
            User.id == user_id,
            User.deleted_at.is_(None),
            User.status == "active",
        )
    )


async def get_user_by_phone(phone: str, db: AsyncSession) -> User | None:
    """按登录手机号查询有效账户；只在店长授权员工时使用。"""

    return await db.scalar(
        select(User).where(
            User.phone == phone,
            User.deleted_at.is_(None),
            User.status == "active",
        )
    )


async def get_membership(
    user_id: uuid.UUID, store_id: uuid.UUID, db: AsyncSession
) -> StoreMember | None:
    statement = (
        select(StoreMember)
        .where(
            StoreMember.user_id == user_id,
            StoreMember.store_id == store_id,
            StoreMember.status == "active",
        )
        .options(joinedload(StoreMember.user), joinedload(StoreMember.store))
    )
    return await db.scalar(statement)


async def get_store_member_for_update(
    user_id: uuid.UUID, store_id: uuid.UUID, db: AsyncSession
) -> StoreMember | None:
    """取得门店成员关系的行锁，避免并发授权时创建重复关系。"""

    statement = (
        select(StoreMember)
        .where(StoreMember.user_id == user_id, StoreMember.store_id == store_id)
        # PostgreSQL 不允许对 joinedload 产生的外连接整体加行锁；这里调用方
        # 已持有用户对象，也不需要预加载关联对象。
        .with_for_update(of=StoreMember)
    )
    return await db.scalar(statement)


async def list_store_members(store_id: uuid.UUID, db: AsyncSession) -> list[StoreMember]:
    """返回当前门店有效成员，供店长管理员工/DM 使用。"""

    statement = (
        select(StoreMember)
        .where(StoreMember.store_id == store_id, StoreMember.status == "active")
        .options(joinedload(StoreMember.user), joinedload(StoreMember.store))
        .order_by(StoreMember.created_at)
    )
    return list((await db.scalars(statement)).all())


async def get_refresh_token_for_update(
    token_id: uuid.UUID, db: AsyncSession
) -> RefreshToken | None:
    statement = (
        select(RefreshToken).where(RefreshToken.id == token_id).with_for_update()
    )
    return await db.scalar(statement)


async def add_refresh_token(token: RefreshToken, db: AsyncSession) -> None:
    db.add(token)
    await db.flush()


async def revoke_user_refresh_tokens(
    user_id: uuid.UUID, revoked_at: datetime, db: AsyncSession
) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=revoked_at)
    )


async def get_invite_for_update(
    code_hash: str, db: AsyncSession
) -> StoreInvite | None:
    statement = (
        select(StoreInvite)
        .where(StoreInvite.code_hash == code_hash)
        .options(joinedload(StoreInvite.store, innerjoin=True))
        .with_for_update(of=StoreInvite)
    )
    return await db.scalar(statement)
