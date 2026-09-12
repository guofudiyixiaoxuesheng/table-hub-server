"""剧本 AI 视觉素材生产线接口。"""

# ruff: noqa: B008

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.scenes.script_visual.schemas import (
    GenerateScriptVisualAssetRequest,
    GenerateScriptVisualProfileRequest,
)
from app.ai.scenes.script_visual.service import (
    approve_script_visual_profile,
    delete_script_visual_asset,
    generate_script_visual_asset_image,
    generate_script_visual_assets,
    generate_script_visual_profile,
    get_script_visual_profile,
    list_script_visual_assets,
    list_visual_style_presets,
    select_script_visual_asset,
)
from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import StoreManagerAccess

router = APIRouter(prefix="/script-visual", tags=["script-visual"])


@router.get("/style-presets")
async def list_visual_style_presets_route(
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """查询系统内置 + 当前门店可用的视觉风格模板。"""

    data = await list_visual_style_presets(
        store_id=access.store_id,
        db=db,
    )
    return success_response(
        data=[item.model_dump(mode="json", by_alias=True) for item in data]
    )


@router.get("/{document_id}/profile")
async def get_script_visual_profile_route(
    document_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """查询某个剧本最新视觉档案。"""

    data = await get_script_visual_profile(
        store_id=access.store_id,
        document_id=document_id,
        db=db,
    )
    return success_response(
        data=data.model_dump(mode="json", by_alias=True) if data else None
    )


@router.post("/{document_id}/profile/generate")
async def generate_script_visual_profile_route(
    document_id: uuid.UUID,
    payload: GenerateScriptVisualProfileRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """基于剧本档案 + RAG 生成视觉档案。"""

    data = await generate_script_visual_profile(
        store_id=access.store_id,
        document_id=document_id,
        user_id=access.user_id,
        payload=payload,
        db=db,
    )
    return success_response(
        message="AI 视觉档案已生成",
        data=data.model_dump(mode="json", by_alias=True),
    )


@router.post("/profiles/{profile_id}/approve")
async def approve_script_visual_profile_route(
    profile_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """店长确认视觉档案可用于后续生成图片。"""

    data = await approve_script_visual_profile(
        store_id=access.store_id,
        profile_id=profile_id,
        user_id=access.user_id,
        db=db,
    )
    return success_response(
        message="视觉档案已确认",
        data=data.model_dump(mode="json", by_alias=True),
    )


@router.get("/{document_id}/assets")
async def list_script_visual_assets_route(
    document_id: uuid.UUID,
    access: StoreManagerAccess,
    usage_type: str | None = None,
    db: AsyncSession = Depends(get_database),
):
    """查询某个剧本的视觉素材候选图。"""

    data = await list_script_visual_assets(
        store_id=access.store_id,
        document_id=document_id,
        usage_type=usage_type,
        db=db,
    )
    return success_response(
        data=[item.model_dump(mode="json", by_alias=True) for item in data]
    )


@router.post("/{document_id}/assets/generate")
async def generate_script_visual_assets_route(
    document_id: uuid.UUID,
    payload: GenerateScriptVisualAssetRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """生成视觉素材候选图 Prompt。"""

    data = await generate_script_visual_assets(
        store_id=access.store_id,
        document_id=document_id,
        user_id=access.user_id,
        payload=payload,
        db=db,
    )
    return success_response(
        message="视觉素材候选已生成",
        data=[item.model_dump(mode="json", by_alias=True) for item in data],
    )


@router.post("/assets/{asset_id}/select")
async def select_script_visual_asset_route(
    asset_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """店长确认某张视觉素材为正式素材。"""

    data = await select_script_visual_asset(
        store_id=access.store_id,
        asset_id=asset_id,
        db=db,
    )
    return success_response(
        message="视觉素材已设为正式版本",
        data=data.model_dump(mode="json", by_alias=True),
    )


@router.post("/assets/{asset_id}/generate-image")
async def generate_script_visual_asset_image_route(
    asset_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """根据候选素材 Prompt 生成真实图片。"""

    data = await generate_script_visual_asset_image(
        store_id=access.store_id,
        asset_id=asset_id,
        db=db,
    )
    return success_response(
        message="视觉图片已生成",
        data=data.model_dump(mode="json", by_alias=True),
    )


@router.delete("/assets/{asset_id}")
async def delete_script_visual_asset_route(
    asset_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """删除视觉素材候选图。"""

    await delete_script_visual_asset(
        store_id=access.store_id,
        asset_id=asset_id,
        db=db,
    )
    return success_response(message="视觉素材已删除")
