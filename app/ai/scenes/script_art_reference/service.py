"""剧本杀美术参考素材包业务服务。"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.scenes.script_art_reference.models import (
    ArtReferenceImageStatus,
    ArtReferencePackageStatus,
    ScriptArtReferenceImage,
    ScriptArtReferencePackage,
    ScriptArtReferenceStyleProfile,
)
from app.ai.scenes.script_art_reference.schemas import (
    AnalyzeArtReferenceImagesRequest,
    ArtReferenceImageResponse,
    ArtReferencePackageListResponse,
    ArtReferencePackageResponse,
    ArtReferenceStyleProfileResponse,
    ArtReferenceTaxonomyResponse,
    ArtReferenceUploadTargetResponse,
    CompleteArtReferencePackageUploadRequest,
    CreateArtReferencePackageRequest,
    CreateArtReferencePackageResponse,
    CreateArtReferenceStyleProfileRequest,
    UpdateArtReferenceImageRequest,
    UpdateArtReferencePackageRequest,
)
from app.ai.scenes.script_art_reference.taxonomy import (
    canonical_taxonomy_value,
    guess_usage_type,
    taxonomy_payload,
    values_for_taxonomy_filter,
)
from app.core.exceptions import ApplicationError
from app.integrations.llm.client import (
    structured_chat_completion,
    structured_vision_completion,
)
from app.integrations.storage.oss import OssStorage


class ArtReferenceError(ApplicationError):
    """美术参考素材包业务异常。"""

    status_code = 422
    code = "art_reference_error"


class _ArtStyleProfileDraft(BaseModel):
    """LLM 产出的视觉规律草稿。"""

    name: str
    style_summary: str
    composition_rules: list[str] = Field(default_factory=list)
    color_and_lighting: list[str] = Field(default_factory=list)
    print_texture_rules: list[str] = Field(default_factory=list)
    visual_metaphors: list[str] = Field(default_factory=list)
    title_association_rules: list[str] = Field(default_factory=list)
    prompt_template: str
    negative_prompt: str


class _ArtImageCaptionDraft(BaseModel):
    """一张参考图的可检索视觉 caption。"""

    caption: str = Field(description="中文视觉描述，包含主体、场景、构图与画面叙事")
    main_subject: str = Field(description="画面主角或核心场景")
    design_language: str = Field(description="海报设计形式，例如恐怖电影海报、极简情感概念海报")
    rendering_medium: str = Field(description="表现媒介，例如数字厚涂、版画线稿、水彩拼贴")
    palette: list[str] = Field(default_factory=list)
    mood_keywords: list[str] = Field(default_factory=list)
    composition_keywords: list[str] = Field(default_factory=list)
    visual_symbols: list[str] = Field(default_factory=list, description="可复用的视觉符号")
    typography_layout: str = Field(description="标题/信息的排版方式，仅描述位置和风格，不复述文字")
    safe_text_area: str = Field(description="适合后续叠加门店信息的留白区域")
    title_visual_relation: str = Field(description="标题语义如何映射到画面元素")


def get_art_reference_taxonomy() -> ArtReferenceTaxonomyResponse:
    """返回前端可选的标签体系。"""

    return ArtReferenceTaxonomyResponse.from_payload(taxonomy_payload())


def _normalize_list(value: list[str] | None) -> list[str]:
    if not value:
        return []
    return list(dict.fromkeys(item.strip() for item in value if item.strip()))


def _safe_filename(file_name: str) -> str:
    """清理文件名，避免路径穿越，同时保留中文文件名。"""

    name = Path(file_name).name.strip() or "image"
    return re.sub(r"[\r\n\t/\\]+", "_", name)


def _build_image_object_key(
    *,
    store_id: uuid.UUID,
    package_id: uuid.UUID,
    image_id: uuid.UUID,
    file_name: str,
) -> str:
    return (
        f"stores/{store_id}/art-references/{package_id}/images/"
        f"{image_id}/{_safe_filename(file_name)}"
    )


def _preview_image_url(
    image: ScriptArtReferenceImage,
    storage: OssStorage | None,
) -> str | None:
    """生成图片预览地址。

    数据库里的 image_url 只作为历史兼容字段；真正可靠的是 object_key。
    OSS 预签名 GET URL 会过期，所以详情接口每次返回时都重新生成。
    """

    if image.status not in {
        ArtReferenceImageStatus.UPLOADED.value,
        ArtReferenceImageStatus.ANALYZING.value,
        ArtReferenceImageStatus.READY.value,
    }:
        return image.image_url
    if storage is None:
        return image.image_url
    try:
        return storage.presign_get(image.object_key)
    except Exception:  # noqa: BLE001
        return image.image_url


def _image_to_response(
    image: ScriptArtReferenceImage,
    *,
    storage: OssStorage | None = None,
) -> ArtReferenceImageResponse:
    return ArtReferenceImageResponse(
        id=image.id,
        packageId=image.package_id,
        clientFileId=image.client_file_id,
        usageType=image.usage_type,
        styleType=image.style_type,
        eraType=canonical_taxonomy_value("eraTypes", image.era_type) or "unknown",
        moodTypes=image.mood_types or [],
        compositionTypes=image.composition_types or [],
        fileName=image.file_name,
        relativePath=image.relative_path,
        contentType=image.content_type,
        size=image.size,
        objectKey=image.object_key,
        imageUrl=_preview_image_url(image, storage),
        caption=image.caption,
        analysisJson=image.analysis_json or {},
        status=image.status,
        errorMessage=image.error_message,
        sortOrder=image.sort_order,
        createdAt=image.created_at,
        updatedAt=image.updated_at,
    )


def _package_to_response(
    package: ScriptArtReferencePackage,
    *,
    include_images: bool = True,
    images: list[ScriptArtReferenceImage] | None = None,
    storage: OssStorage | None = None,
) -> ArtReferencePackageResponse:
    source_images = images if images is not None else []
    if include_images and images is None:
        source_images = package.images
    return ArtReferencePackageResponse(
        id=package.id,
        storeId=package.store_id,
        documentId=package.document_id,
        title=package.title,
        scriptName=package.script_name,
        scriptSummary=package.script_summary,
        scriptTags=package.script_tags or [],
        eraType=canonical_taxonomy_value("eraTypes", package.era_type) or "unknown",
        dominantStyleType=canonical_taxonomy_value("styleTypes", package.dominant_style_type) or "unknown",
        regionType=package.region_type,
        moodTypes=package.mood_types or [],
        copyrightScope=package.copyright_scope,
        copyrightNote=package.copyright_note,
        status=package.status,
        analysisJson=package.analysis_json or {},
        promptBriefJson=package.prompt_brief_json or {},
        imageCount=package.image_count,
        uploadedImageCount=package.uploaded_image_count,
        createdAt=package.created_at,
        updatedAt=package.updated_at,
        images=[
            _image_to_response(image, storage=storage)
            for image in sorted(source_images, key=lambda item: item.sort_order)
        ]
        if include_images
        else [],
    )


async def _get_package(
    *,
    store_id: uuid.UUID,
    package_id: uuid.UUID,
    db: AsyncSession,
) -> ScriptArtReferencePackage:
    result = await db.execute(
        select(ScriptArtReferencePackage)
        .options(selectinload(ScriptArtReferencePackage.images))
        .where(
            ScriptArtReferencePackage.store_id == store_id,
            ScriptArtReferencePackage.id == package_id,
            ScriptArtReferencePackage.deleted_at.is_(None),
        )
    )
    package = result.scalar_one_or_none()
    if package is None:
        raise ArtReferenceError("美术参考素材包不存在或已删除")
    return package


async def create_art_reference_package(
    *,
    store_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: CreateArtReferencePackageRequest,
    db: AsyncSession,
    storage: OssStorage | None = None,
) -> CreateArtReferencePackageResponse:
    """创建素材包记录，并返回每张图片的 OSS 直传地址。"""

    storage = storage or OssStorage()
    package = ScriptArtReferencePackage(
        store_id=store_id,
        document_id=payload.document_id,
        title=payload.title,
        script_name=payload.script_name,
        script_summary=payload.script_summary,
        script_tags=_normalize_list(payload.script_tags),
        era_type=payload.era_type,
        dominant_style_type=payload.dominant_style_type,
        region_type=payload.region_type,
        mood_types=_normalize_list(payload.mood_types),
        copyright_scope=payload.copyright_scope,
        copyright_note=payload.copyright_note,
        status=ArtReferencePackageStatus.UPLOADING.value,
        image_count=len(payload.images),
        uploaded_image_count=0,
        created_by_user_id=user_id,
    )
    db.add(package)
    await db.flush()

    upload_targets: list[ArtReferenceUploadTargetResponse] = []
    images: list[ScriptArtReferenceImage] = []
    for image_input in payload.images:
        image_id = uuid.uuid4()
        usage_type = image_input.usage_type
        if usage_type == "other":
            usage_type = guess_usage_type(
                image_input.relative_path,
                image_input.file_name,
            )
        object_key = _build_image_object_key(
            store_id=store_id,
            package_id=package.id,
            image_id=image_id,
            file_name=image_input.file_name,
        )
        upload = storage.presign_put(object_key, image_input.content_type)
        image = ScriptArtReferenceImage(
            id=image_id,
            package_id=package.id,
            client_file_id=image_input.client_file_id,
            usage_type=usage_type,
            style_type=image_input.style_type,
            era_type=image_input.era_type,
            mood_types=_normalize_list(image_input.mood_types),
            composition_types=_normalize_list(image_input.composition_types),
            file_name=image_input.file_name,
            relative_path=image_input.relative_path,
            content_type=image_input.content_type,
            size=image_input.size,
            object_key=object_key,
            status=ArtReferenceImageStatus.PENDING.value,
            sort_order=image_input.sort_order,
        )
        db.add(image)
        images.append(image)
        upload_targets.append(
            ArtReferenceUploadTargetResponse(
                clientFileId=image_input.client_file_id,
                objectKey=object_key,
                uploadUrl=upload.url,
                headers=upload.headers,
            )
        )

    await db.flush()
    return CreateArtReferencePackageResponse(
        package=_package_to_response(package, images=images),
        uploadTargets=upload_targets,
    )


async def list_art_reference_packages(
    *,
    store_id: uuid.UUID,
    page: int,
    page_size: int,
    db: AsyncSession,
    keyword: str | None = None,
    style_type: str | None = None,
    era_type: str | None = None,
    region_type: str | None = None,
    script_tag: str | None = None,
    mood_type: str | None = None,
    status: str | None = None,
) -> ArtReferencePackageListResponse:
    """分页查询素材包。"""

    conditions = [
        ScriptArtReferencePackage.store_id == store_id,
        ScriptArtReferencePackage.deleted_at.is_(None),
    ]
    if keyword:
        pattern = f"%{keyword.strip()}%"
        conditions.append(
            or_(
                ScriptArtReferencePackage.title.ilike(pattern),
                ScriptArtReferencePackage.script_name.ilike(pattern),
            )
        )
    if style_type:
        conditions.append(
            ScriptArtReferencePackage.dominant_style_type.in_(
                values_for_taxonomy_filter("styleTypes", style_type)
            )
        )
    if era_type:
        conditions.append(
            ScriptArtReferencePackage.era_type.in_(
                values_for_taxonomy_filter("eraTypes", era_type)
            )
        )
    if region_type:
        conditions.append(ScriptArtReferencePackage.region_type == region_type)
    if script_tag:
        conditions.append(ScriptArtReferencePackage.script_tags.contains([script_tag]))
    if mood_type:
        conditions.append(ScriptArtReferencePackage.mood_types.contains([mood_type]))
    if status:
        conditions.append(ScriptArtReferencePackage.status == status)

    total_result = await db.execute(
        select(func.count()).select_from(
            select(ScriptArtReferencePackage.id).where(*conditions).subquery()
        )
    )
    result = await db.execute(
        select(ScriptArtReferencePackage)
        .where(*conditions)
        .order_by(ScriptArtReferencePackage.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return ArtReferencePackageListResponse(
        total=int(total_result.scalar_one() or 0),
        items=[
            _package_to_response(package, include_images=False)
            for package in result.scalars().all()
        ],
    )


async def get_art_reference_package(
    *,
    store_id: uuid.UUID,
    package_id: uuid.UUID,
    db: AsyncSession,
) -> ArtReferencePackageResponse:
    package = await _get_package(store_id=store_id, package_id=package_id, db=db)
    return _package_to_response(package, storage=OssStorage())


async def update_art_reference_package(
    *,
    store_id: uuid.UUID,
    package_id: uuid.UUID,
    payload: UpdateArtReferencePackageRequest,
    db: AsyncSession,
) -> ArtReferencePackageResponse:
    package = await _get_package(store_id=store_id, package_id=package_id, db=db)
    values = payload.model_dump(exclude_unset=True)
    for field, value in values.items():
        if field in {"script_tags", "mood_types"}:
            value = _normalize_list(value)
        setattr(package, field, value)
    package.updated_at = datetime.now(UTC)
    await db.flush()
    return _package_to_response(package)


async def delete_art_reference_package(
    *,
    store_id: uuid.UUID,
    package_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    package = await _get_package(store_id=store_id, package_id=package_id, db=db)
    package.deleted_at = datetime.now(UTC)
    package.updated_at = datetime.now(UTC)
    await db.flush()


async def complete_art_reference_package_upload(
    *,
    store_id: uuid.UUID,
    package_id: uuid.UUID,
    payload: CompleteArtReferencePackageUploadRequest,
    db: AsyncSession,
    storage: OssStorage | None = None,
) -> ArtReferencePackageResponse:
    """确认图片已经上传到 OSS，并更新素材包上传状态。"""

    storage = storage or OssStorage()
    package = await _get_package(store_id=store_id, package_id=package_id, db=db)
    images_by_client_id = {image.client_file_id: image for image in package.images}

    for completed_file in payload.files:
        image = images_by_client_id.get(completed_file.client_file_id)
        if image is None:
            continue
        try:
            metadata = await storage.head_object(image.object_key)
        except Exception as error:  # noqa: BLE001
            image.status = ArtReferenceImageStatus.FAILED.value
            image.error_message = f"OSS 文件校验失败：{error}"
            continue
        if image.size and metadata.size and image.size != metadata.size:
            image.status = ArtReferenceImageStatus.FAILED.value
            image.error_message = "OSS 文件大小与前端选择的文件不一致"
            continue
        image.status = ArtReferenceImageStatus.UPLOADED.value
        image.image_url = None
        image.content_type = metadata.content_type or image.content_type
        image.error_message = None
        image.updated_at = datetime.now(UTC)

    uploaded_statuses = {
        ArtReferenceImageStatus.UPLOADED.value,
        ArtReferenceImageStatus.ANALYZING.value,
        ArtReferenceImageStatus.READY.value,
    }
    package.uploaded_image_count = sum(
        1 for image in package.images if image.status in uploaded_statuses
    )
    package.status = (
        ArtReferencePackageStatus.UPLOADED.value
        if package.uploaded_image_count >= package.image_count
        else ArtReferencePackageStatus.UPLOADING.value
    )
    package.updated_at = datetime.now(UTC)
    await db.flush()
    return _package_to_response(package, storage=storage)


async def update_art_reference_image(
    *,
    store_id: uuid.UUID,
    image_id: uuid.UUID,
    payload: UpdateArtReferenceImageRequest,
    db: AsyncSession,
) -> ArtReferenceImageResponse:
    result = await db.execute(
        select(ScriptArtReferenceImage)
        .join(ScriptArtReferenceImage.package)
        .where(
            ScriptArtReferenceImage.id == image_id,
            ScriptArtReferencePackage.store_id == store_id,
            ScriptArtReferencePackage.deleted_at.is_(None),
        )
    )
    image = result.scalar_one_or_none()
    if image is None:
        raise ArtReferenceError("美术参考图片不存在或已删除")

    values = payload.model_dump(exclude_unset=True)
    for field, value in values.items():
        if field in {"mood_types", "composition_types"}:
            value = _normalize_list(value)
        setattr(image, field, value)
    image.updated_at = datetime.now(UTC)
    await db.flush()
    return _image_to_response(image, storage=OssStorage())


async def delete_art_reference_image(
    *,
    store_id: uuid.UUID,
    image_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    result = await db.execute(
        select(ScriptArtReferenceImage)
        .options(selectinload(ScriptArtReferenceImage.package))
        .join(ScriptArtReferenceImage.package)
        .where(
            ScriptArtReferenceImage.id == image_id,
            ScriptArtReferencePackage.store_id == store_id,
            ScriptArtReferencePackage.deleted_at.is_(None),
        )
    )
    image = result.scalar_one_or_none()
    if image is None:
        raise ArtReferenceError("美术参考图片不存在或已删除")
    package = image.package
    await db.delete(image)
    package.image_count = max(0, package.image_count - 1)
    if image.status in {
        ArtReferenceImageStatus.UPLOADED.value,
        ArtReferenceImageStatus.ANALYZING.value,
        ArtReferenceImageStatus.READY.value,
    }:
        package.uploaded_image_count = max(0, package.uploaded_image_count - 1)
    package.updated_at = datetime.now(UTC)
    await db.flush()


def _style_profile_to_response(
    profile: ScriptArtReferenceStyleProfile,
) -> ArtReferenceStyleProfileResponse:
    return ArtReferenceStyleProfileResponse(
        id=profile.id,
        storeId=profile.store_id,
        name=profile.name,
        samplePackageIds=profile.sample_package_ids or [],
        sampleCount=profile.sample_count,
        filterSnapshot=profile.filter_snapshot or {},
        analysisJson=profile.analysis_json or {},
        promptTemplate=profile.prompt_template,
        negativePrompt=profile.negative_prompt,
        status=profile.status,
        errorMessage=profile.error_message,
        createdAt=profile.created_at,
        updatedAt=profile.updated_at,
    )


async def analyze_art_reference_images(
    *,
    store_id: uuid.UUID,
    payload: AnalyzeArtReferenceImagesRequest,
    db: AsyncSession,
    image_ids: set[uuid.UUID] | None = None,
) -> list[ArtReferencePackageResponse]:
    """把用户主动选择的 OSS 图片发送到视觉模型，补全可检索 caption。"""

    package_ids = list(dict.fromkeys(payload.package_ids))
    result = await db.execute(
        select(ScriptArtReferencePackage)
        .options(selectinload(ScriptArtReferencePackage.images))
        .where(
            ScriptArtReferencePackage.store_id == store_id,
            ScriptArtReferencePackage.id.in_(package_ids),
            ScriptArtReferencePackage.deleted_at.is_(None),
        )
    )
    packages = result.scalars().unique().all()
    if len(packages) != len(package_ids):
        raise ArtReferenceError("所选素材包中存在不存在或无权访问的记录")

    storage = OssStorage()
    analyzed = 0
    for package in packages:
        for image in package.images:
            if analyzed >= payload.max_images:
                break
            if image_ids is not None and image.id not in image_ids:
                continue
            allowed_statuses = (
                {ArtReferenceImageStatus.ANALYZING.value}
                if image_ids is not None
                else {ArtReferenceImageStatus.UPLOADED.value, ArtReferenceImageStatus.READY.value}
            )
            if image.status not in allowed_statuses:
                continue
            image.status = ArtReferenceImageStatus.ANALYZING.value
            try:
                draft = await structured_vision_completion(
                    _ArtImageCaptionDraft,
                    [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "分析这张剧本杀发行参考图。输出中文；不要复述 Logo、完整标题或版权文字。重点提炼可复用的画面规律，以及标题/故事概念到视觉隐喻的转化方式。",
                                },
                                {"type": "image_url", "image_url": {"url": storage.presign_get(image.object_key)}},
                            ],
                        }
                    ],
                    temperature=0.1,
                    max_tokens=700,
                )
                image.caption = draft.caption
                image.analysis_json = {
                    "designLanguage": draft.design_language,
                    "mainSubject": draft.main_subject,
                    "renderingMedium": draft.rendering_medium,
                    "palette": draft.palette,
                    "moodKeywords": draft.mood_keywords,
                    "compositionKeywords": draft.composition_keywords,
                    "visualSymbols": draft.visual_symbols,
                    "typographyLayout": draft.typography_layout,
                    "safeTextArea": draft.safe_text_area,
                    "titleVisualRelation": draft.title_visual_relation,
                }
                image.status = ArtReferenceImageStatus.READY.value
                image.error_message = None
            except Exception as error:  # noqa: BLE001
                image.status = ArtReferenceImageStatus.FAILED.value
                image.error_message = f"多模态分析失败：{error}"
            image.updated_at = datetime.now(UTC)
            analyzed += 1
        package.status = ArtReferencePackageStatus.READY.value
        package.updated_at = datetime.now(UTC)

    await db.flush()
    return [_package_to_response(item, storage=storage) for item in packages]


async def queue_art_reference_image_analysis(
    *,
    store_id: uuid.UUID,
    payload: AnalyzeArtReferenceImagesRequest,
    db: AsyncSession,
) -> list[uuid.UUID]:
    """将待分析图片标记为排队中，并返回本次后台任务的精确图片集合。"""

    package_ids = list(dict.fromkeys(payload.package_ids))
    result = await db.execute(
        select(ScriptArtReferencePackage)
        .options(selectinload(ScriptArtReferencePackage.images))
        .where(
            ScriptArtReferencePackage.store_id == store_id,
            ScriptArtReferencePackage.id.in_(package_ids),
            ScriptArtReferencePackage.deleted_at.is_(None),
        )
    )
    packages = result.scalars().unique().all()
    if len(packages) != len(package_ids):
        raise ArtReferenceError("所选素材包中存在不存在或无权访问的记录")

    queued_image_ids: list[uuid.UUID] = []
    for package in packages:
        queued_in_package = False
        for image in package.images:
            if len(queued_image_ids) >= payload.max_images:
                break
            if image.status not in {ArtReferenceImageStatus.UPLOADED.value, ArtReferenceImageStatus.READY.value}:
                continue
            image.status = ArtReferenceImageStatus.ANALYZING.value
            image.error_message = None
            image.updated_at = datetime.now(UTC)
            queued_image_ids.append(image.id)
            queued_in_package = True
        if queued_in_package:
            package.status = ArtReferencePackageStatus.ANALYZING.value
            package.updated_at = datetime.now(UTC)

    if not queued_image_ids:
        raise ArtReferenceError("所选素材没有可分析的已上传图片；分析中的图片请等待完成后再试")
    await db.flush()
    return queued_image_ids


async def create_art_reference_style_profile(
    *,
    store_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: CreateArtReferenceStyleProfileRequest,
    db: AsyncSession,
) -> ArtReferenceStyleProfileResponse:
    """把已勾选素材包的元数据、caption 与剧本语义汇总为视觉规律档案。"""

    package_ids = list(dict.fromkeys(payload.package_ids))
    result = await db.execute(
        select(ScriptArtReferencePackage)
        .options(selectinload(ScriptArtReferencePackage.images))
        .where(
            ScriptArtReferencePackage.store_id == store_id,
            ScriptArtReferencePackage.id.in_(package_ids),
            ScriptArtReferencePackage.deleted_at.is_(None),
        )
    )
    packages = result.scalars().unique().all()
    if len(packages) != len(package_ids):
        raise ArtReferenceError("所选素材包中存在不存在或无权访问的记录")

    samples: list[dict[str, object]] = []
    for package in packages:
        image_notes = [
            {
                "usage": image.usage_type,
                "caption": image.caption or "",
                "analysis": image.analysis_json or {},
                "fileName": image.file_name,
            }
            for image in package.images
            if image.status in {ArtReferenceImageStatus.UPLOADED.value, ArtReferenceImageStatus.READY.value}
        ]
        samples.append(
            {
                "scriptName": package.script_name,
                "scriptSummary": package.script_summary or "",
                "scriptTags": package.script_tags or [],
                "style": canonical_taxonomy_value("styleTypes", package.dominant_style_type),
                "era": canonical_taxonomy_value("eraTypes", package.era_type),
                "region": package.region_type,
                "moods": package.mood_types or [],
                "images": image_notes,
            }
        )

    prompt = (
        "你是剧本杀发行视觉总监。根据多套参考素材的结构化信息，提炼可复用的视觉规律。"
        "注意：这里沉淀的是跨剧本的形式规律，不是样本的剧情或世界观。"
        "不要复刻任何原图、角色姿势、Logo 或标题字。"
        "style_summary、composition_rules、color_and_lighting、print_texture_rules 只能描述构图、媒介、"
        "色彩、光影和印刷材质；不得出现样本剧本名、人名、怪物名、具体道具、具体场景、标签枚举或示例故事。"
        "visual_metaphors 与 title_association_rules 只能描述抽象方法，例如‘让一个与当前标题有关的物件成为视觉锚点’，"
        "不得列举蛇、兔子、糖果等样本专属元素。"
        "输出中文。除构图和光影外，必须提炼 print_texture_rules：例如吸墨纸纤维、网点、"
    "套色轻微错位、丝网印刷、干刷、刮擦、旧海报磨损等‘发行印刷粗粝感’；"
    "区分这种有意的材质感与低清晰度、脏画面。"
    "prompt_template 必须是可替换剧本标题、简介与场次信息的原创生图提示词模板。\n\n"
        f"筛选条件：{payload.filter_snapshot}\n样本：{samples}"
    )
    draft = await structured_chat_completion(
        _ArtStyleProfileDraft,
        [{"role": "user", "content": prompt}],
        temperature=0.25,
        max_tokens=1800,
    )
    profile = ScriptArtReferenceStyleProfile(
        store_id=store_id,
        name=payload.name or draft.name,
        sample_package_ids=[str(item) for item in package_ids],
        sample_count=len(packages),
        filter_snapshot=payload.filter_snapshot,
        analysis_json={
            "styleSummary": draft.style_summary,
            "compositionRules": draft.composition_rules,
            "colorAndLighting": draft.color_and_lighting,
            "printTextureRules": draft.print_texture_rules,
            "visualMetaphors": draft.visual_metaphors,
            "titleAssociationRules": draft.title_association_rules,
        },
        prompt_template=draft.prompt_template,
        negative_prompt=draft.negative_prompt,
        created_by_user_id=user_id,
        status="ready",
    )
    db.add(profile)
    await db.flush()
    return _style_profile_to_response(profile)


async def list_art_reference_style_profiles(
    *, store_id: uuid.UUID, db: AsyncSession
) -> list[ArtReferenceStyleProfileResponse]:
    result = await db.execute(
        select(ScriptArtReferenceStyleProfile)
        .where(ScriptArtReferenceStyleProfile.store_id == store_id)
        .order_by(ScriptArtReferenceStyleProfile.updated_at.desc())
    )
    return [_style_profile_to_response(item) for item in result.scalars().all()]
