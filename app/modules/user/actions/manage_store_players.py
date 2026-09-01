"""门店玩家客户池增删改查用例。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ApplicationError
from app.modules.auth.service import hash_password
from app.modules.user.exceptions import UserPhoneAlreadyExistsError
from app.modules.user.models import StorePlayer, User, UserRole, UserStatus
from app.modules.user.repositories import get_user_by_phone
from app.modules.user.schemas import (
    StorePlayerListResponse,
    StorePlayerResponse,
    UpdateStorePlayerRequest,
    UpsertStorePlayerRequest,
)


class StorePlayerNotFoundError(ApplicationError):
    status_code = 404
    code = "store_player_not_found"


def _to_store_player_response(row: tuple[StorePlayer, User]) -> StorePlayerResponse:
    store_player, user = row
    return StorePlayerResponse(
        id=store_player.id,
        user_id=user.id,
        phone=user.phone,
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        preference=store_player.preference,
        notes=store_player.notes,
        created_at=store_player.created_at,
        updated_at=store_player.updated_at,
    )


async def list_store_players(
    store_id: uuid.UUID,
    db: AsyncSession,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> StorePlayerListResponse:
    """只查询当前门店客户池里的普通玩家。"""

    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    base = (
        select(StorePlayer.id)
        .join(User, User.id == StorePlayer.user_id)
        .where(
            StorePlayer.store_id == store_id,
            StorePlayer.deleted_at.is_(None),
            User.role == UserRole.USER,
            User.status != UserStatus.DISABLED,
            User.deleted_at.is_(None),
        )
    )
    if keyword:
        like = f"%{keyword.strip()}%"
        base = base.where(or_(User.nickname.ilike(like), User.phone.ilike(like), StorePlayer.preference.ilike(like)))
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (
        await db.execute(
            select(StorePlayer, User)
            .join(User, User.id == StorePlayer.user_id)
            .where(StorePlayer.id.in_(base))
            .order_by(StorePlayer.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).tuples().all()
    return StorePlayerListResponse(
        items=[_to_store_player_response(row) for row in rows],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


async def create_store_player(
    store_id: uuid.UUID,
    payload: UpsertStorePlayerRequest,
    db: AsyncSession,
) -> StorePlayerResponse:
    """创建或复用一个全局普通用户，再加入当前门店客户池。"""

    user = await get_user_by_phone(payload.phone, db)
    if user is None:
        user = User(
            phone=payload.phone,
            password_hash=hash_password(payload.password),
            nickname=payload.nickname,
            avatar_url=payload.avatar_url,
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()
    else:
        raise UserPhoneAlreadyExistsError

    existing = await db.scalar(
        select(StorePlayer).where(
            StorePlayer.store_id == store_id,
            StorePlayer.user_id == user.id,
            StorePlayer.deleted_at.is_(None),
        )
    )
    if existing:
        return _to_store_player_response((existing, user))

    store_player = StorePlayer(
        store_id=store_id,
        user_id=user.id,
        preference=payload.preference,
        notes=payload.notes,
    )
    db.add(store_player)
    try:
        await db.flush()
        await db.refresh(user)
        await db.refresh(store_player)
    except IntegrityError as error:
        await db.rollback()
        raise UserPhoneAlreadyExistsError from error
    return _to_store_player_response((store_player, user))


async def update_store_player(
    store_id: uuid.UUID,
    store_player_id: uuid.UUID,
    payload: UpdateStorePlayerRequest,
    db: AsyncSession,
) -> StorePlayerResponse:
    row = (
        await db.execute(
            select(StorePlayer, User)
            .join(User, User.id == StorePlayer.user_id)
            .where(
                StorePlayer.id == store_player_id,
                StorePlayer.store_id == store_id,
                StorePlayer.deleted_at.is_(None),
            )
        )
    ).tuples().first()
    if row is None:
        raise StorePlayerNotFoundError("玩家不存在")
    store_player, user = row
    user_fields = payload.model_dump(exclude_unset=True, include={"phone", "nickname", "avatar_url"})
    store_fields = payload.model_dump(exclude_unset=True, include={"preference", "notes"})
    for key, value in user_fields.items():
        setattr(user, key, value)
    for key, value in store_fields.items():
        setattr(store_player, key, value)
    try:
        await db.flush()
        await db.refresh(user)
        await db.refresh(store_player)
    except IntegrityError as error:
        await db.rollback()
        raise UserPhoneAlreadyExistsError from error
    return _to_store_player_response((store_player, user))


async def delete_store_player(store_id: uuid.UUID, store_player_id: uuid.UUID, db: AsyncSession) -> None:
    store_player = await db.scalar(
        select(StorePlayer).where(
            StorePlayer.id == store_player_id,
            StorePlayer.store_id == store_id,
            StorePlayer.deleted_at.is_(None),
        )
    )
    if store_player is None:
        raise StorePlayerNotFoundError("玩家不存在")
    store_player.deleted_at = datetime.now(UTC)
    await db.flush()
