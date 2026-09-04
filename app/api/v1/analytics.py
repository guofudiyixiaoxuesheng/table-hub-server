"""热门剧本、高频问题、预约转化和 AI 质量评估接口。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import StoreManagerAccess
from app.modules.analytics.models import RagEvaluationStatus
from app.modules.analytics.schemas import RagEvaluationCreateRequest
from app.modules.analytics.service import (
    create_rag_evaluation_job,
    get_rag_evaluation_job,
    get_rag_evaluation_summary,
    list_rag_evaluation_jobs,
    run_rag_evaluation_job,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/rag-evaluations")
async def list_rag_evaluations_route(
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
    status_value: RagEvaluationStatus | None = Query(default=None, alias="status"),
    keyword: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
):
    data = await list_rag_evaluation_jobs(
        store_id=access.store_id,
        db=db,
        status=status_value,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return success_response(
        data=[item.model_dump(mode="json", by_alias=True) for item in data.items],
        meta=data.meta.model_dump(mode="json", by_alias=True),
    )


@router.get("/rag-evaluations/summary")
async def rag_evaluations_summary_route(
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    data = await get_rag_evaluation_summary(store_id=access.store_id, db=db)
    return success_response(data=data.model_dump(mode="json", by_alias=True))


@router.post("/rag-evaluations", status_code=status.HTTP_201_CREATED)
async def create_rag_evaluation_route(
    payload: RagEvaluationCreateRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    data = await create_rag_evaluation_job(
        store_id=access.store_id,
        user_id=access.user_id,
        guest_id=None,
        chat_session_id=None,
        payload=payload,
        db=db,
    )
    return success_response(message="评估任务已创建", data=data.model_dump(mode="json", by_alias=True))


@router.get("/rag-evaluations/{job_id}")
async def get_rag_evaluation_route(
    job_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    data = await get_rag_evaluation_job(store_id=access.store_id, job_id=job_id, db=db)
    return success_response(data=data.model_dump(mode="json", by_alias=True))


@router.post("/rag-evaluations/{job_id}/run")
async def run_rag_evaluation_route(
    job_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    data = await run_rag_evaluation_job(store_id=access.store_id, job_id=job_id, db=db)
    return success_response(message="评估完成", data=data.model_dump(mode="json", by_alias=True))
