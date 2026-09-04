"""后台玩家客户池接口。"""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import CurrentAccess, StoreManagerAccess
from app.core.store_context import resolve_request_store_id
from app.modules.user.actions import (
    create_store_player,
    delete_store_player,
    get_current_player_behavior_summary,
    get_player_behavior_summary,
    get_store_player_analytics,
    list_store_players,
    update_store_player,
)
from app.modules.user.actions.manage_store_players import StorePlayerNotFoundError
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


@router.get("/analytics/summary")
async def player_analytics_route(
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    data = await get_store_player_analytics(access.store_id, db)
    return success_response(data=data.model_dump(mode="json", by_alias=True))


@router.get("/me/behavior")
async def my_player_behavior_route(
    access: CurrentAccess,
    store_id: uuid.UUID | None = Query(default=None, alias="storeId"),
    db: AsyncSession = Depends(get_database),
):
    resolved_store_id = await resolve_request_store_id(
        db=db,
        access=access,
        requested_store_id=store_id,
    )
    if resolved_store_id is None:
        return success_response(data=None)
    try:
        data = await get_current_player_behavior_summary(resolved_store_id, access.user_id, db)
    except StorePlayerNotFoundError:
        return success_response(data=None)
    return success_response(data=data.model_dump(mode="json", by_alias=True))


@router.get("/{store_player_id}/behavior")
async def player_behavior_route(
    store_player_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    data = await get_player_behavior_summary(access.store_id, store_player_id, db)
    return success_response(data=data.model_dump(mode="json", by_alias=True))


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
