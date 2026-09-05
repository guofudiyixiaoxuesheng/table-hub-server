from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.scenes.script_opening_manual.schemas import OpeningManualGenerateRequest
from app.ai.scenes.script_opening_manual.service import (
    create_opening_manual_generation,
    delete_opening_manual,
    get_opening_manual,
    list_opening_manuals,
    run_opening_manual_generation,
    to_opening_manual_result,
)
from app.common.responses import success_response
from app.core.database import AsyncSessionLocal, get_database
from app.core.security import StoreManagerAccess

router = APIRouter(prefix="/script-opening-manuals", tags=["script-opening-manuals"])


async def run_opening_manual_generation_background(
    *,
    store_id: uuid.UUID,
    manual_id: uuid.UUID,
) -> None:
    async with AsyncSessionLocal() as db:
        await run_opening_manual_generation(
            db,
            store_id=store_id,
            manual_id=manual_id,
        )


@router.get("/{document_id}")
async def list_opening_manuals_route(
    document_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    manuals = await list_opening_manuals(
        db,
        store_id=access.store_id,
        document_id=document_id,
    )
    return success_response(data=[item.model_dump(mode="json", by_alias=True) for item in manuals])


@router.post("/{document_id}/generate")
async def generate_opening_manual(
    document_id: uuid.UUID,
    payload: OpeningManualGenerateRequest,
    background_tasks: BackgroundTasks,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    manual = await create_opening_manual_generation(
        db,
        store_id=access.store_id,
        document_id=document_id,
        payload=payload,
        created_by_user_id=access.user_id,
    )

    await db.refresh(manual)
    data = to_opening_manual_result(manual).model_dump(mode="json", by_alias=True)
    await db.commit()

    background_tasks.add_task(
        run_opening_manual_generation_background,
        store_id=access.store_id,
        manual_id=manual.id,
    )

    return success_response(
        data=data,
        message="主持人手册生成任务已创建，系统将在后台继续生成",
    )


@router.get("/manuals/{manual_id}")
async def get_opening_manual_route(
    manual_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    manual = await get_opening_manual(db, store_id=access.store_id, manual_id=manual_id)
    return success_response(data=manual.model_dump(mode="json", by_alias=True))


@router.delete("/manuals/{manual_id}")
async def delete_opening_manual_route(
    manual_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    await delete_opening_manual(db, store_id=access.store_id, manual_id=manual_id)
    await db.commit()
    return success_response(message="主持人手册已删除")
