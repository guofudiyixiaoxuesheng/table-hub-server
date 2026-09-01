"""开本场次查询和后台场次管理接口。"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import StoreAccessContext, StoreManagerAccess, get_optional_access
from app.modules.auth.models import Store
from app.modules.game_session.schemas import (
    CreateGameSessionRequest,
    SessionPlayerRequest,
    UpdateGameSessionRequest,
    UpdateSessionPlayerRequest,
)
from app.modules.game_session.models import GameSessionStatus
from app.modules.game_session.service import (
    add_session_player,
    create_game_session,
    delete_game_session,
    delete_session_player,
    get_game_session_detail,
    list_dm_options,
    list_game_sessions,
    list_script_options,
    update_game_session,
    update_session_player,
)

router = APIRouter(prefix="/game-sessions", tags=["game-sessions"])


async def _resolve_store_id(
    db: AsyncSession,
    access: StoreAccessContext | None,
    store_id: uuid.UUID | None,
) -> uuid.UUID | None:
    if access and access.store_id:
        return access.store_id
    if store_id:
        return await db.scalar(select(Store.id).where(Store.id == store_id))
    return await db.scalar(select(Store.id).order_by(Store.created_at.asc()).limit(1))


def _is_manager(access: StoreAccessContext | None) -> bool:
    return bool(access and access.store_id and access.role in {"admin", "manager"})


def _public_session(item) -> dict[str, object]:
    payload = item.model_dump(mode="json", by_alias=True)
    payload.pop("notes", None)
    return payload


@router.get("/script-options")
async def script_options(
    access: StoreManagerAccess,
    keyword: str | None = Query(default=None),
    db: AsyncSession = Depends(get_database),
):
    return success_response(data=[item.model_dump(mode="json", by_alias=True) for item in await list_script_options(access.store_id, keyword, db)])


@router.get("/dm-options")
async def dm_options(
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    return success_response(data=[item.model_dump(mode="json", by_alias=True) for item in await list_dm_options(access.store_id, db)])


@router.get("")
async def list_sessions(
    access: StoreAccessContext | None = Depends(get_optional_access),
    keyword: str | None = Query(default=None),
    day: date | None = Query(default=None, description="按某一天过滤，格式 YYYY-MM-DD"),
    status_filter: GameSessionStatus | None = Query(default=None, alias="status"),
    script_document_id: uuid.UUID | None = Query(default=None, alias="scriptDocumentId"),
    store_id: uuid.UUID | None = Query(default=None, alias="storeId"),
    db: AsyncSession = Depends(get_database),
):
    resolved_store_id = await _resolve_store_id(db, access, store_id)
    if not resolved_store_id:
        return success_response(data=[])
    data = await list_game_sessions(
        resolved_store_id,
        keyword,
        db,
        day=day,
        status=status_filter if _is_manager(access) else (status_filter or GameSessionStatus.RECRUITING),
        script_document_id=script_document_id,
    )
    return success_response(
        data=[
            item.model_dump(mode="json", by_alias=True) if _is_manager(access) else _public_session(item)
            for item in data
        ]
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_session_route(
    payload: CreateGameSessionRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    data = await create_game_session(access.store_id, payload, db)
    return success_response(message="场次创建成功", data=data.model_dump(mode="json", by_alias=True))


@router.get("/{session_id}")
async def get_session_route(
    session_id: uuid.UUID,
    access: StoreAccessContext | None = Depends(get_optional_access),
    store_id: uuid.UUID | None = Query(default=None, alias="storeId"),
    db: AsyncSession = Depends(get_database),
):
    resolved_store_id = await _resolve_store_id(db, access, store_id)
    if not resolved_store_id:
        return success_response(data=None)
    data = await get_game_session_detail(resolved_store_id, session_id, db)
    payload = data.model_dump(mode="json", by_alias=True)
    if not _is_manager(access):
        payload.pop("notes", None)
        payload.pop("players", None)
    return success_response(data=payload)


@router.put("/{session_id}")
async def update_session_route(
    session_id: uuid.UUID,
    payload: UpdateGameSessionRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    data = await update_game_session(access.store_id, session_id, payload, db)
    return success_response(message="场次已更新", data=data.model_dump(mode="json", by_alias=True))


@router.delete("/{session_id}")
async def delete_session_route(
    session_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    await delete_game_session(access.store_id, session_id, db)
    return success_response(message="场次已删除")


@router.post("/{session_id}/players", status_code=status.HTTP_201_CREATED)
async def add_player_route(
    session_id: uuid.UUID,
    payload: SessionPlayerRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    data = await add_session_player(access.store_id, session_id, payload, db)
    return success_response(message="约车玩家已添加", data=data.model_dump(mode="json", by_alias=True))


@router.put("/{session_id}/players/{player_id}")
async def update_player_route(
    session_id: uuid.UUID,
    player_id: uuid.UUID,
    payload: UpdateSessionPlayerRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    data = await update_session_player(access.store_id, session_id, player_id, payload, db)
    return success_response(message="约车玩家已更新", data=data.model_dump(mode="json", by_alias=True))


@router.delete("/{session_id}/players/{player_id}")
async def delete_player_route(
    session_id: uuid.UUID,
    player_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    await delete_session_player(access.store_id, session_id, player_id, db)
    return success_response(message="约车玩家已移除")
