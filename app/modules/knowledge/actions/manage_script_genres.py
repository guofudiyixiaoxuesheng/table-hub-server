"""维护门店剧本类型字典。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ApplicationError
from app.modules.knowledge.models import ScriptGenreOption
from app.modules.knowledge.schemas import (
    ScriptGenreOptionCreateRequest,
    ScriptGenreOptionResponse,
    ScriptGenreOptionUpdateRequest,
)


class ScriptGenreOptionNotFoundError(ApplicationError):
    status_code = 404
    code = "script_genre_option_not_found"


class ScriptGenreOptionConflictError(ApplicationError):
    status_code = 409
    code = "script_genre_option_conflict"


def _to_response(option: ScriptGenreOption) -> ScriptGenreOptionResponse:
    return ScriptGenreOptionResponse(
        id=option.id,
        value=option.value,
        label=option.label,
        description=option.description,
        sortOrder=option.sort_order,
        isActive=option.is_active,
        createdAt=option.created_at,
        updatedAt=option.updated_at,
    )


async def list_script_genre_options(
    *, store_id: uuid.UUID, active_only: bool, db: AsyncSession
) -> list[ScriptGenreOptionResponse]:
    statement = select(ScriptGenreOption).where(ScriptGenreOption.store_id == store_id)
    if active_only:
        statement = statement.where(ScriptGenreOption.is_active.is_(True))
    statement = statement.order_by(ScriptGenreOption.sort_order.asc(), ScriptGenreOption.created_at.asc())
    options = (await db.scalars(statement)).all()
    return [_to_response(item) for item in options]


async def create_script_genre_option(
    *, store_id: uuid.UUID, payload: ScriptGenreOptionCreateRequest, db: AsyncSession
) -> ScriptGenreOptionResponse:
    exists = await db.scalar(
        select(ScriptGenreOption.id).where(
            ScriptGenreOption.store_id == store_id,
            ScriptGenreOption.value == payload.value,
        )
    )
    if exists:
        raise ScriptGenreOptionConflictError("该剧本类型值已存在")

    option = ScriptGenreOption(
        store_id=store_id,
        value=payload.value,
        label=payload.label,
        description=payload.description,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
    )
    db.add(option)
    await db.flush()
    return _to_response(option)


async def update_script_genre_option(
    *,
    store_id: uuid.UUID,
    option_id: uuid.UUID,
    payload: ScriptGenreOptionUpdateRequest,
    db: AsyncSession,
) -> ScriptGenreOptionResponse:
    option = await db.scalar(
        select(ScriptGenreOption).where(
            ScriptGenreOption.id == option_id,
            ScriptGenreOption.store_id == store_id,
        )
    )
    if option is None:
        raise ScriptGenreOptionNotFoundError("剧本类型不存在")

    values = payload.model_dump(exclude_unset=True)
    if "label" in values:
        option.label = payload.label or option.label
    if "description" in values:
        option.description = payload.description
    if "sort_order" in values:
        option.sort_order = payload.sort_order if payload.sort_order is not None else option.sort_order
    if "is_active" in values:
        option.is_active = bool(payload.is_active)
    await db.flush()
    return _to_response(option)


async def delete_script_genre_option(
    *, store_id: uuid.UUID, option_id: uuid.UUID, db: AsyncSession
) -> None:
    option = await db.scalar(
        select(ScriptGenreOption).where(
            ScriptGenreOption.id == option_id,
            ScriptGenreOption.store_id == store_id,
        )
    )
    if option is None:
        raise ScriptGenreOptionNotFoundError("剧本类型不存在")
    # 删除字典项不改历史文档；历史文档仍保存 value，前端可按原值兜底展示。
    await db.delete(option)
