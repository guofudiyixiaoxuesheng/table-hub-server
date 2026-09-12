"""剧本杀美术参考素材包接口。"""

# ruff: noqa: B008

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.scenes.script_art_reference.schemas import (
    AnalyzeArtReferenceImagesRequest,
    CompleteArtReferencePackageUploadRequest,
    CreateArtReferencePackageRequest,
    CreateArtReferenceStyleProfileRequest,
    UpdateArtReferenceImageRequest,
    UpdateArtReferencePackageRequest,
)
from app.ai.scenes.script_art_reference.service import (
    analyze_art_reference_images,
    complete_art_reference_package_upload,
    create_art_reference_package,
    delete_art_reference_image,
    delete_art_reference_package,
    get_art_reference_package,
    get_art_reference_taxonomy,
    list_art_reference_packages,
    list_art_reference_style_profiles,
    create_art_reference_style_profile,
    queue_art_reference_image_analysis,
    update_art_reference_image,
    update_art_reference_package,
)
from app.common.responses import success_response
from app.core.database import AsyncSessionLocal, get_database
from app.core.security import StoreManagerAccess

router = APIRouter(prefix="/script-art-references", tags=["script-art-references"])


async def run_art_reference_image_analysis_background(
    *,
    store_id: uuid.UUID,
    package_ids: list[uuid.UUID],
    image_ids: list[uuid.UUID],
    max_images: int,
) -> None:
    """后台任务必须使用独立数据库会话，不能复用已结束的 HTTP 请求会话。"""

    async with AsyncSessionLocal() as db:
        try:
            await analyze_art_reference_images(
                store_id=store_id,
                payload=AnalyzeArtReferenceImagesRequest(
                    packageIds=package_ids,
                    maxImages=max_images,
                ),
                image_ids=set(image_ids),
                db=db,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise


@router.get("/taxonomy")
async def get_art_reference_taxonomy_route():
    """查询美术参考素材分类标签。"""

    data = get_art_reference_taxonomy()
    return success_response(data=data.model_dump(mode="json", by_alias=True))


@router.get("/style-profiles")
async def list_art_reference_style_profiles_route(
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    data = await list_art_reference_style_profiles(store_id=access.store_id, db=db)
    return success_response(data=[item.model_dump(mode="json", by_alias=True) for item in data])


@router.post("/style-profiles")
async def create_art_reference_style_profile_route(
    payload: CreateArtReferenceStyleProfileRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """勾选多个素材包后，一键提炼可复用的视觉规律档案。"""

    data = await create_art_reference_style_profile(
        store_id=access.store_id,
        user_id=access.user_id,
        payload=payload,
        db=db,
    )
    return success_response(message="视觉规律档案已提炼", data=data.model_dump(mode="json", by_alias=True))


@router.post("/images/analyze")
async def analyze_art_reference_images_route(
    payload: AnalyzeArtReferenceImagesRequest,
    background_tasks: BackgroundTasks,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """将用户主动选择的素材图片放入后台多模态分析队列。"""

    image_ids = await queue_art_reference_image_analysis(
        store_id=access.store_id,
        payload=payload,
        db=db,
    )
    await db.commit()
    background_tasks.add_task(
        run_art_reference_image_analysis_background,
        store_id=access.store_id,
        package_ids=payload.package_ids,
        image_ids=image_ids,
        max_images=payload.max_images,
    )
    return success_response(
        message=f"已加入后台视觉分析队列，共 {len(image_ids)} 张图片",
        data={"queuedImageCount": len(image_ids)},
    )


@router.get("/packages")
async def list_art_reference_packages_route(
    access: StoreManagerAccess,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    keyword: str | None = Query(default=None),
    style_type: str | None = Query(default=None, alias="styleType"),
    era_type: str | None = Query(default=None, alias="eraType"),
    region_type: str | None = Query(default=None, alias="regionType"),
    script_tag: str | None = Query(default=None, alias="scriptTag"),
    mood_type: str | None = Query(default=None, alias="moodType"),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_database),
):
    """分页查询当前门店的美术参考素材包。"""

    data = await list_art_reference_packages(
        store_id=access.store_id,
        page=page,
        page_size=page_size,
        keyword=keyword,
        style_type=style_type,
        era_type=era_type,
        region_type=region_type,
        script_tag=script_tag,
        mood_type=mood_type,
        status=status,
        db=db,
    )
    return success_response(
        data=[item.model_dump(mode="json", by_alias=True) for item in data.items],
        meta={"total": data.total, "page": page, "pageSize": page_size},
    )


@router.post("/packages")
async def create_art_reference_package_route(
    payload: CreateArtReferencePackageRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """创建素材包，并返回 OSS 图片直传地址。"""

    data = await create_art_reference_package(
        store_id=access.store_id,
        user_id=access.user_id,
        payload=payload,
        db=db,
    )
    return success_response(
        message="美术参考素材包已创建",
        data=data.model_dump(mode="json", by_alias=True),
    )


@router.get("/packages/{package_id}")
async def get_art_reference_package_route(
    package_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """查询素材包详情。"""

    data = await get_art_reference_package(
        store_id=access.store_id,
        package_id=package_id,
        db=db,
    )
    return success_response(data=data.model_dump(mode="json", by_alias=True))


@router.put("/packages/{package_id}")
async def update_art_reference_package_route(
    package_id: uuid.UUID,
    payload: UpdateArtReferencePackageRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """修改素材包基础信息。"""

    data = await update_art_reference_package(
        store_id=access.store_id,
        package_id=package_id,
        payload=payload,
        db=db,
    )
    return success_response(
        message="美术参考素材包已更新",
        data=data.model_dump(mode="json", by_alias=True),
    )


@router.delete("/packages/{package_id}")
async def delete_art_reference_package_route(
    package_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """删除素材包。"""

    await delete_art_reference_package(
        store_id=access.store_id,
        package_id=package_id,
        db=db,
    )
    return success_response(message="美术参考素材包已删除")


@router.post("/packages/{package_id}/complete")
async def complete_art_reference_package_upload_route(
    package_id: uuid.UUID,
    payload: CompleteArtReferencePackageUploadRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """图片直传 OSS 后，确认素材包上传结果。"""

    data = await complete_art_reference_package_upload(
        store_id=access.store_id,
        package_id=package_id,
        payload=payload,
        db=db,
    )
    return success_response(
        message="美术参考素材包上传状态已确认",
        data=data.model_dump(mode="json", by_alias=True),
    )


@router.put("/images/{image_id}")
async def update_art_reference_image_route(
    image_id: uuid.UUID,
    payload: UpdateArtReferenceImageRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """修改单张图片分类、caption 等信息。"""

    data = await update_art_reference_image(
        store_id=access.store_id,
        image_id=image_id,
        payload=payload,
        db=db,
    )
    return success_response(
        message="美术参考图片已更新",
        data=data.model_dump(mode="json", by_alias=True),
    )


@router.delete("/images/{image_id}")
async def delete_art_reference_image_route(
    image_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """删除单张参考图片记录。"""

    await delete_art_reference_image(
        store_id=access.store_id,
        image_id=image_id,
        db=db,
    )
    return success_response(message="美术参考图片已删除")
