"""剧本 AI 运营物料接口。"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.scenes.script_marketing.models import ScriptMarketingAssetStatus
from app.ai.scenes.script_marketing.schemas import (
    ScriptMarketingApproveRequest,
    ScriptMarketingGenerateImagesRequest,
    ScriptMarketingGenerateRequest,
)
from app.ai.scenes.script_marketing.service import (
    approve_script_marketing_asset,
    generate_script_marketing_images,
    generate_script_marketing_assets,
    list_script_marketing_assets,
)
from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import StoreManagerAccess

router = APIRouter(prefix="/script-marketing", tags=["script-marketing"])


@router.get("/{document_id}")
async def list_script_marketing_route(
    document_id: uuid.UUID,
    access: StoreManagerAccess,
    status_filter: ScriptMarketingAssetStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_database),
):
    """查询某个剧本已生成的运营物料版本。"""

    data = await list_script_marketing_assets(
        store_id=access.store_id,
        document_id=document_id,
        status=status_filter,
        db=db,
    )
    return success_response(data=[item.model_dump(mode="json", by_alias=True) for item in data])


@router.post("/{document_id}/generate")
async def generate_script_marketing_route(
    document_id: uuid.UUID,
    payload: ScriptMarketingGenerateRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """基于剧本 RAG 内容生成宣传文案和图片提示词草稿。"""

    data = await generate_script_marketing_assets(
        store_id=access.store_id,
        document_id=document_id,
        user_id=access.user_id,
        payload=payload,
        db=db,
    )
    return success_response(message="AI 运营物料已生成", data=data.model_dump(mode="json", by_alias=True))


@router.post("/assets/{asset_id}/approve")
async def approve_script_marketing_route(
    asset_id: uuid.UUID,
    payload: ScriptMarketingApproveRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """店长确认采用某个 AI 运营物料版本。"""

    data = await approve_script_marketing_asset(
        store_id=access.store_id,
        asset_id=asset_id,
        user_id=access.user_id,
        payload=payload,
        db=db,
    )
    return success_response(message="AI 运营物料已确认为正式版本", data=data.model_dump(mode="json", by_alias=True))


@router.post("/assets/{asset_id}/images")
async def generate_script_marketing_images_route(
    asset_id: uuid.UUID,
    payload: ScriptMarketingGenerateImagesRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """为正式物料生成真实图片，并保存到 OSS 供场次和移动端复用。"""

    data = await generate_script_marketing_images(
        store_id=access.store_id,
        asset_id=asset_id,
        payload=payload,
        db=db,
    )
    return success_response(message="图片已生成并保存到 OSS", data=data.model_dump(mode="json", by_alias=True))
