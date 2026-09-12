"""剧本杀美术参考素材包 API 数据结构。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaxonomyOptionResponse(BaseModel):
    """前端下拉框使用的标签项。"""

    label: str
    value: str
    description: str


class ArtReferenceTaxonomyResponse(BaseModel):
    """美术参考分析的全部标签体系。"""

    script_tags: list[TaxonomyOptionResponse] = Field(alias="scriptTags")
    usage_types: list[TaxonomyOptionResponse] = Field(alias="usageTypes")
    style_types: list[TaxonomyOptionResponse] = Field(alias="styleTypes")
    era_types: list[TaxonomyOptionResponse] = Field(alias="eraTypes")
    region_types: list[TaxonomyOptionResponse] = Field(alias="regionTypes")
    mood_types: list[TaxonomyOptionResponse] = Field(alias="moodTypes")
    composition_types: list[TaxonomyOptionResponse] = Field(alias="compositionTypes")
    aliases: dict[str, dict[str, str]] = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def from_payload(
        cls, payload: dict[str, object]
    ) -> ArtReferenceTaxonomyResponse:
        return cls.model_validate(payload)


class ArtReferenceImageInput(BaseModel):
    """创建素材包时，前端传入的单张图片元数据。"""

    client_file_id: str = Field(alias="clientFileId", min_length=1, max_length=120)
    file_name: str = Field(alias="fileName", min_length=1, max_length=255)
    relative_path: str = Field(alias="relativePath", min_length=1, max_length=1024)
    content_type: str = Field(alias="contentType", min_length=1, max_length=255)
    size: int = Field(ge=0)
    usage_type: str = Field(default="character", alias="usageType", max_length=80)
    style_type: str = Field(default="unknown", alias="styleType", max_length=80)
    era_type: str = Field(default="unknown", alias="eraType", max_length=80)
    mood_types: list[str] = Field(default_factory=list, alias="moodTypes", max_length=20)
    composition_types: list[str] = Field(
        default_factory=list,
        alias="compositionTypes",
        max_length=20,
    )
    sort_order: int = Field(default=100, alias="sortOrder")

    model_config = ConfigDict(populate_by_name=True)


class CreateArtReferencePackageRequest(BaseModel):
    """创建美术参考素材包，并申请 OSS 直传地址。"""

    document_id: uuid.UUID | None = Field(default=None, alias="documentId")
    title: str = Field(min_length=1, max_length=160)
    script_name: str = Field(alias="scriptName", min_length=1, max_length=200)
    script_summary: str | None = Field(default=None, alias="scriptSummary", max_length=3000)
    script_tags: list[str] = Field(default_factory=list, alias="scriptTags", max_length=30)
    era_type: str = Field(default="unknown", alias="eraType", max_length=80)
    dominant_style_type: str = Field(
        default="unknown",
        alias="dominantStyleType",
        max_length=80,
    )
    region_type: str = Field(default="unknown", alias="regionType", max_length=80)
    mood_types: list[str] = Field(default_factory=list, alias="moodTypes", max_length=20)
    copyright_scope: str = Field(
        default="reference_only",
        alias="copyrightScope",
        max_length=60,
    )
    copyright_note: str | None = Field(default=None, alias="copyrightNote", max_length=2000)
    images: list[ArtReferenceImageInput] = Field(min_length=1, max_length=300)

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def normalize_tags(self) -> CreateArtReferencePackageRequest:
        self.script_tags = list(dict.fromkeys(item.strip() for item in self.script_tags if item.strip()))
        self.mood_types = list(dict.fromkeys(item.strip() for item in self.mood_types if item.strip()))
        return self


class UpdateArtReferencePackageRequest(BaseModel):
    """修改素材包基础信息。"""

    title: str | None = Field(default=None, min_length=1, max_length=160)
    script_name: str | None = Field(default=None, alias="scriptName", min_length=1, max_length=200)
    script_summary: str | None = Field(default=None, alias="scriptSummary", max_length=3000)
    script_tags: list[str] | None = Field(default=None, alias="scriptTags", max_length=30)
    era_type: str | None = Field(default=None, alias="eraType", max_length=80)
    dominant_style_type: str | None = Field(default=None, alias="dominantStyleType", max_length=80)
    region_type: str | None = Field(default=None, alias="regionType", max_length=80)
    mood_types: list[str] | None = Field(default=None, alias="moodTypes", max_length=20)
    copyright_scope: str | None = Field(default=None, alias="copyrightScope", max_length=60)
    copyright_note: str | None = Field(default=None, alias="copyrightNote", max_length=2000)

    model_config = ConfigDict(populate_by_name=True)


class UpdateArtReferenceImageRequest(BaseModel):
    """修改单张图片分类和 caption。"""

    usage_type: str | None = Field(default=None, alias="usageType", max_length=80)
    style_type: str | None = Field(default=None, alias="styleType", max_length=80)
    era_type: str | None = Field(default=None, alias="eraType", max_length=80)
    mood_types: list[str] | None = Field(default=None, alias="moodTypes", max_length=20)
    composition_types: list[str] | None = Field(default=None, alias="compositionTypes", max_length=20)
    caption: str | None = Field(default=None, max_length=4000)

    model_config = ConfigDict(populate_by_name=True)


class CompletedArtReferenceFileRequest(BaseModel):
    """前端图片上传 OSS 成功后回传的文件标识。"""

    client_file_id: str = Field(alias="clientFileId", min_length=1, max_length=120)
    etag: str | None = Field(default=None, max_length=120)

    model_config = ConfigDict(populate_by_name=True)


class CompleteArtReferencePackageUploadRequest(BaseModel):
    """确认一个素材包内哪些图片已经完成 OSS 上传。"""

    files: list[CompletedArtReferenceFileRequest] = Field(min_length=1)


class ArtReferenceUploadTargetResponse(BaseModel):
    """前端直传 OSS 所需信息。"""

    client_file_id: str = Field(alias="clientFileId")
    object_key: str = Field(alias="objectKey")
    upload_url: str = Field(alias="uploadUrl")
    headers: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True)


class ArtReferenceImageResponse(BaseModel):
    """素材包单张图片响应。"""

    id: uuid.UUID
    package_id: uuid.UUID = Field(alias="packageId")
    client_file_id: str = Field(alias="clientFileId")
    usage_type: str = Field(alias="usageType")
    style_type: str = Field(alias="styleType")
    era_type: str = Field(alias="eraType")
    mood_types: list[str] = Field(alias="moodTypes")
    composition_types: list[str] = Field(alias="compositionTypes")
    file_name: str = Field(alias="fileName")
    relative_path: str = Field(alias="relativePath")
    content_type: str = Field(alias="contentType")
    size: int
    object_key: str = Field(alias="objectKey")
    image_url: str | None = Field(default=None, alias="imageUrl")
    caption: str | None = None
    analysis_json: dict[str, object] = Field(alias="analysisJson")
    status: str
    error_message: str | None = Field(default=None, alias="errorMessage")
    sort_order: int = Field(alias="sortOrder")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class ArtReferencePackageResponse(BaseModel):
    """素材包详情响应。"""

    id: uuid.UUID
    store_id: uuid.UUID = Field(alias="storeId")
    document_id: uuid.UUID | None = Field(default=None, alias="documentId")
    title: str
    script_name: str = Field(alias="scriptName")
    script_summary: str | None = Field(default=None, alias="scriptSummary")
    script_tags: list[str] = Field(alias="scriptTags")
    era_type: str = Field(alias="eraType")
    dominant_style_type: str = Field(alias="dominantStyleType")
    region_type: str = Field(alias="regionType")
    mood_types: list[str] = Field(alias="moodTypes")
    copyright_scope: str = Field(alias="copyrightScope")
    copyright_note: str | None = Field(default=None, alias="copyrightNote")
    status: str
    analysis_json: dict[str, object] = Field(alias="analysisJson")
    prompt_brief_json: dict[str, object] = Field(alias="promptBriefJson")
    image_count: int = Field(alias="imageCount")
    uploaded_image_count: int = Field(alias="uploadedImageCount")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    images: list[ArtReferenceImageResponse] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class CreateArtReferencePackageResponse(BaseModel):
    """创建素材包响应：素材包记录 + 每张图的上传地址。"""

    package: ArtReferencePackageResponse
    upload_targets: list[ArtReferenceUploadTargetResponse] = Field(alias="uploadTargets")

    model_config = ConfigDict(populate_by_name=True)


class ArtReferencePackageListResponse(BaseModel):
    """素材包分页列表。"""

    total: int
    items: list[ArtReferencePackageResponse]


class CreateArtReferenceStyleProfileRequest(BaseModel):
    """从用户勾选的一批素材包中提炼视觉规律。"""

    package_ids: list[uuid.UUID] = Field(alias="packageIds", min_length=2, max_length=60)
    name: str | None = Field(default=None, max_length=160)
    filter_snapshot: dict[str, object] = Field(default_factory=dict, alias="filterSnapshot")

    model_config = ConfigDict(populate_by_name=True)


class AnalyzeArtReferenceImagesRequest(BaseModel):
    """批量为已上传图片生成多模态 caption。"""

    package_ids: list[uuid.UUID] = Field(alias="packageIds", min_length=1, max_length=60)
    max_images: int = Field(default=300, alias="maxImages", ge=1, le=300)

    model_config = ConfigDict(populate_by_name=True)


class ArtReferenceStyleProfileResponse(BaseModel):
    id: uuid.UUID
    store_id: uuid.UUID = Field(alias="storeId")
    name: str
    sample_package_ids: list[str] = Field(alias="samplePackageIds")
    sample_count: int = Field(alias="sampleCount")
    filter_snapshot: dict[str, object] = Field(alias="filterSnapshot")
    analysis_json: dict[str, object] = Field(alias="analysisJson")
    prompt_template: str = Field(alias="promptTemplate")
    negative_prompt: str | None = Field(default=None, alias="negativePrompt")
    status: str
    error_message: str | None = Field(default=None, alias="errorMessage")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)
