"""统一解析当前请求所属门店。

玩家端/游客端没有登录态时，JWT 里没有 store_id。这个 resolver 用来把
“当前请求属于哪个门店”这件事集中处理，避免每个接口各写一套兜底逻辑。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import StoreAccessContext
from app.modules.auth.models import Store


async def resolve_request_store_id(
    *,
    db: AsyncSession,
    access: StoreAccessContext | None,
    requested_store_id: uuid.UUID | None = None,
    allow_default: bool = True,
) -> uuid.UUID | None:
    """解析当前门店 ID。

    优先级：
    1. 已登录用户 JWT 中的 store_id
    2. 游客/玩家端请求显式传入的 storeId
    3. MVP 单门店兜底：默认第一家门店
    """

    if access and access.store_id:
        return access.store_id

    if requested_store_id:
        return await db.scalar(select(Store.id).where(Store.id == requested_store_id))

    if not allow_default:
        return None

    return await db.scalar(select(Store.id).order_by(Store.created_at.asc()).limit(1))
