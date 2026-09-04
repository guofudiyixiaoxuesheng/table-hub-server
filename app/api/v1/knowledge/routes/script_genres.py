"""剧本类型字典接口。"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import StoreAccessContext, StoreManagerAccess, get_optional_access
from app.core.store_context import resolve_request_store_id
from app.modules.knowledge.actions.manage_script_genres import (
    create_script_genre_option,
    delete_script_genre_option,
    list_script_genre_options,
    update_script_genre_option,
)
from app.modules.knowledge.schemas import (
    ScriptGenreOptionCreateRequest,
    ScriptGenreOptionUpdateRequest,
)

router = APIRouter()


@router.get("/script-genres")
async def get_script_genres(
    access: Annotated[StoreAccessContext | None, Depends(get_optional_access)],
    store_id: Annotated[uuid.UUID | None, Query(alias="storeId")] = None,
    active_only: Annotated[bool, Query(alias="activeOnly")] = True,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    resolved_store_id = await resolve_request_store_id(
        db=db,
        access=access,
        requested_store_id=store_id,
    )
    if resolved_store_id is None:
        return success_response(data=[])
    data = await list_script_genre_options(store_id=resolved_store_id, active_only=active_only, db=db)
    return success_response(data=[item.model_dump(mode="json", by_alias=True) for item in data])


@router.post("/script-genres")
async def create_script_genre(
    access: StoreManagerAccess,
    payload: ScriptGenreOptionCreateRequest,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    data = await create_script_genre_option(store_id=access.store_id, payload=payload, db=db)
    return success_response(data=data.model_dump(mode="json", by_alias=True))


@router.patch("/script-genres/{option_id}")
async def update_script_genre(
    option_id: uuid.UUID,
    access: StoreManagerAccess,
    payload: ScriptGenreOptionUpdateRequest,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    data = await update_script_genre_option(
        store_id=access.store_id,
        option_id=option_id,
        payload=payload,
        db=db,
    )
    return success_response(data=data.model_dump(mode="json", by_alias=True))


@router.delete("/script-genres/{option_id}")
async def delete_script_genre(
    option_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    await delete_script_genre_option(store_id=access.store_id, option_id=option_id, db=db)
    return success_response(data={"deleted": True})
