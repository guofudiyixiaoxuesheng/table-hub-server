"""统一展示当前门店的知识库资源。"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import StoreAccessContext, get_optional_access
from app.modules.auth.models import Store
from app.modules.knowledge.actions.search_documents import (
    KnowledgeDocumentSearchFilters,
    search_knowledge_documents,
)
from app.modules.knowledge.models import KnowledgeDocumentStatus, KnowledgeResourceType

router = APIRouter()


@router.get("/documents")
async def get_knowledge_documents(
    access: Annotated[StoreAccessContext | None, Depends(get_optional_access)],
    resource_type: Annotated[
        KnowledgeResourceType | None, Query(alias="resourceType")
    ] = None,
    keyword: Annotated[str | None, Query(max_length=100)] = None,
    status: KnowledgeDocumentStatus | None = None,
    has_active_version: Annotated[
        bool | None, Query(alias="hasActiveVersion")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
    store_id: Annotated[uuid.UUID | None, Query(alias="storeId")] = None,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    resolved_store_id = access.store_id if access and access.store_id else None
    if resolved_store_id is None and store_id:
        resolved_store_id = await db.scalar(select(Store.id).where(Store.id == store_id))
    if resolved_store_id is None:
        resolved_store_id = await db.scalar(select(Store.id).order_by(Store.created_at.asc()).limit(1))
    if resolved_store_id is None:
        return success_response(data=[], meta={"total": 0, "page": page, "pageSize": page_size})

    is_manager = bool(access and access.store_id and access.role in {"admin", "manager"})
    result = await search_knowledge_documents(
        KnowledgeDocumentSearchFilters(
            store_id=resolved_store_id,
            keyword=keyword,
            resource_type=resource_type or (KnowledgeResourceType.SCRIPT if not is_manager else None),
            status=status or (KnowledgeDocumentStatus.ACTIVE if not is_manager else None),
            has_active_version=has_active_version,
            page=page,
            page_size=page_size,
        ),
        db,
    )
    # 目前前端知识库列表仍按数组消费，为了不破坏页面先保持 data 为 items。
    # 后续接分页 UI 时，可以改为返回 result.model_dump(...)。
    return success_response(
        data=[
            item.model_dump(mode="json", by_alias=True)
            for item in result.items
        ],
        meta={
            "total": result.total,
            "page": result.page,
            "pageSize": result.page_size,
        },
    )
