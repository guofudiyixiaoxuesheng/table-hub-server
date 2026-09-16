"""剧本档案接口。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import StoreManagerAccess
from app.modules.script_profile.schemas import (
    ScriptProfileGenerateRequest,
    ScriptProfileUpdateRequest,
)
from app.modules.script_profile.service import (
    approve_script_profile,
    delete_script_profile,
    get_script_profile_by_document,
    queue_script_profile_generation,
    run_script_profile_generation_background,
    update_script_profile,
)

router = APIRouter(prefix="/script-profiles", tags=["script-profiles"])


@router.get("/by-document/{document_id}")
async def get_script_profile_by_document_route(
    document_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """查询某个知识库剧本对应的剧本档案。"""

    data = await get_script_profile_by_document(db, store_id=access.store_id, document_id=document_id)
    return success_response(data=data.model_dump(mode="json", by_alias=True) if data else None)


@router.post("/{document_id}/generate")
async def generate_script_profile_route(
    document_id: uuid.UUID,
    payload: ScriptProfileGenerateRequest,
    background_tasks: BackgroundTasks,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """将耗时的剧本档案生成排入后台，页面手动刷新查看状态。"""

    data, should_enqueue = await queue_script_profile_generation(
        db,
        store_id=access.store_id,
        document_id=document_id,
        user_id=access.user_id,
    )
    if should_enqueue:
        # BackgroundTasks 使用独立数据库会话，先提交 queued 状态避免读取旧数据。
        await db.commit()
        background_tasks.add_task(
            run_script_profile_generation_background,
            document_id=document_id,
            store_id=access.store_id,
            user_id=access.user_id,
            payload=payload,
        )
        message = "剧本档案已加入后台生成队列，请稍后手动刷新查看结果"
    else:
        message = "剧本档案正在后台生成，请稍后手动刷新查看结果"
    return success_response(message=message, data=data.model_dump(mode="json", by_alias=True))


@router.patch("/{profile_id}")
async def update_script_profile_route(
    profile_id: uuid.UUID,
    payload: ScriptProfileUpdateRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """人工修正剧本档案。"""

    data = await update_script_profile(db, store_id=access.store_id, profile_id=profile_id, payload=payload)
    return success_response(message="剧本档案已更新", data=data.model_dump(mode="json", by_alias=True))


@router.post("/{profile_id}/approve")
async def approve_script_profile_route(
    profile_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """店长/DM 确认剧本档案正式可用。"""

    data = await approve_script_profile(db, store_id=access.store_id, profile_id=profile_id, user_id=access.user_id)
    return success_response(message="剧本档案已确认使用", data=data.model_dump(mode="json", by_alias=True))


@router.delete("/{profile_id}")
async def delete_script_profile_route(
    profile_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """软删除剧本档案。"""

    await delete_script_profile(db, store_id=access.store_id, profile_id=profile_id)
    return success_response(message="剧本档案已删除")
