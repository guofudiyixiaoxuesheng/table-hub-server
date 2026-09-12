"""剧本 AI 视觉素材生产线接口 Schema。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CharacterVisual(BaseModel):
    """单个角色的玩家可见视觉设定。"""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    public_identity: str | None = Field(default=None, alias="publicIdentity")
    gender: str | None = None
    outfit: str | None = None
    props: list[str] = Field(default_factory=list)
    emotion_keywords: list[str] = Field(default_factory=list, alias="emotionKeywords")
    visual_prompt: str | None = Field(default=None, alias="visualPrompt")
    spoiler_level: str = Field(default="public", alias="spoilerLevel")


class ScriptVisualProfileResult(BaseModel):
    """剧本视觉档案返回结构。"""

    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    document_id: uuid.UUID = Field(alias="documentId")
    script_profile_id: uuid.UUID | None = Field(default=None, alias="scriptProfileId")
    name: str
    era: str | None = None
    world_setting: str | None = Field(default=None, alias="worldSetting")
    main_scenes: list[str] = Field(default_factory=list, alias="mainScenes")
    visual_symbols: list[str] = Field(default_factory=list, alias="visualSymbols")
    color_palette: list[str] = Field(default_factory=list, alias="colorPalette")
    atmosphere_keywords: list[str] = Field(
        default_factory=list, alias="atmosphereKeywords"
    )
    character_visuals: list[CharacterVisual] = Field(
        default_factory=list, alias="characterVisuals"
    )
    spoiler_safe_rules: list[str] = Field(
        default_factory=list, alias="spoilerSafeRules"
    )
    copyright_safe_rules: list[str] = Field(
        default_factory=list, alias="copyrightSafeRules"
    )
    reference_image_urls: list[str] = Field(
        default_factory=list, alias="referenceImageUrls"
    )
    confidence_score: int | None = Field(default=None, alias="confidenceScore")
    status: str
    error_message: str | None = Field(default=None, alias="errorMessage")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    approved_at: datetime | None = Field(default=None, alias="approvedAt")


class GenerateScriptVisualProfileRequest(BaseModel):
    """生成剧本视觉档案请求。"""

    model_config = ConfigDict(populate_by_name=True)

    reference_image_urls: list[str] = Field(
        default_factory=list, alias="referenceImageUrls"
    )
    extra_requirement: str | None = Field(
        default=None, alias="extraRequirement", max_length=800
    )


class VisualStylePresetResult(BaseModel):
    """视觉风格模板返回结构。"""

    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    name: str
    style_type: str = Field(alias="styleType")
    description: str | None = None
    prompt_template: str = Field(alias="promptTemplate")
    negative_prompt: str | None = Field(default=None, alias="negativePrompt")
    recommended_aspect_ratios: list[str] = Field(
        default_factory=list, alias="recommendedAspectRatios"
    )
    is_system: bool = Field(alias="isSystem")
    is_active: bool = Field(alias="isActive")
    sort_order: int = Field(alias="sortOrder")


class CreateVisualStylePresetRequest(BaseModel):
    """创建视觉风格模板请求。"""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(max_length=100)
    style_type: str = Field(alias="styleType", max_length=60)
    description: str | None = None
    prompt_template: str = Field(alias="promptTemplate")
    negative_prompt: str | None = Field(default=None, alias="negativePrompt")
    recommended_aspect_ratios: list[str] = Field(
        default_factory=list, alias="recommendedAspectRatios"
    )
    is_active: bool = Field(default=True, alias="isActive")
    sort_order: int = Field(default=100, alias="sortOrder")


class GenerateScriptVisualAssetRequest(BaseModel):
    """生成视觉素材请求。"""

    model_config = ConfigDict(populate_by_name=True)

    visual_profile_id: uuid.UUID | None = Field(default=None, alias="visualProfileId")
    style_preset_id: uuid.UUID | None = Field(default=None, alias="stylePresetId")
    usage_type: str = Field(default="session_cover", alias="usageType")
    usage_label: str = Field(default="拼车主图", alias="usageLabel")
    aspect_ratio: str = Field(default="1:1", alias="aspectRatio")
    count: int = Field(default=1, ge=1, le=4)
    extra_requirement: str | None = Field(
        default=None, alias="extraRequirement", max_length=800
    )


class ScriptVisualAssetResult(BaseModel):
    """视觉候选图返回结构。"""

    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    document_id: uuid.UUID = Field(alias="documentId")
    visual_profile_id: uuid.UUID | None = Field(default=None, alias="visualProfileId")
    style_preset_id: uuid.UUID | None = Field(default=None, alias="stylePresetId")
    usage_type: str = Field(alias="usageType")
    usage_label: str = Field(alias="usageLabel")
    prompt: str
    negative_prompt: str | None = Field(default=None, alias="negativePrompt")
    aspect_ratio: str = Field(alias="aspectRatio")
    object_key: str | None = Field(default=None, alias="objectKey")
    image_url: str | None = Field(default=None, alias="imageUrl")
    status: str
    error_message: str | None = Field(default=None, alias="errorMessage")
    is_selected: bool = Field(alias="isSelected")
    selected_at: datetime | None = Field(default=None, alias="selectedAt")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
