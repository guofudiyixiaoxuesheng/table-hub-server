"""后台玩家客户池接口。"""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import StoreManagerAccess
from app.modules.user.actions import (
    create_store_player,
    delete_store_player,
    list_store_players,
    update_store_player,
)
from app.modules.user.schemas import UpdateStorePlayerRequest, UpsertStorePlayerRequest

router = APIRouter(prefix="/players")


@router.get("")
async def list_players_route(
    access: StoreManagerAccess,
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    db: AsyncSession = Depends(get_database),
):
    data = await list_store_players(
        access.store_id,
        db,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return success_response(
        data=[item.model_dump(mode="json") for item in data.items],
        meta={"total": data.total, "page": data.page, "pageSize": data.page_size},
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_player_route(
    payload: UpsertStorePlayerRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    data = await create_store_player(access.store_id, payload, db)
    return success_response(message="玩家创建成功", data=data.model_dump(mode="json"))


@router.put("/{store_player_id}")
async def update_player_route(
    store_player_id: uuid.UUID,
    payload: UpdateStorePlayerRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    data = await update_store_player(access.store_id, store_player_id, payload, db)
    return success_response(message="玩家已更新", data=data.model_dump(mode="json"))


@router.delete("/{store_player_id}")
async def delete_player_route(
    store_player_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    await delete_store_player(access.store_id, store_player_id, db)
    return success_response(message="玩家已删除")
