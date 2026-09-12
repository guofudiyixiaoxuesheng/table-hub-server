"""剧本营销物料生成入参与出参。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MarketingSessionFormDefaults(BaseModel):
    """创建场次时可一键填充的表单默认值。"""

    model_config = ConfigDict(populate_by_name=True)

    title: str | None = None
    description: str | None = None
    duration_minutes: int | None = Field(default=None, alias="durationMinutes")
    capacity: int | None = None
    min_players: int | None = Field(default=None, alias="minPlayers")
    price_yuan: float | None = Field(default=None, alias="priceYuan")
    notes: str | None = None


class MarketingPlayerCard(BaseModel):
    """玩家端拼车列表卡片物料。"""

    model_config = ConfigDict(populate_by_name=True)

    title: str | None = None
    subtitle: str | None = None
    summary: str | None = None
    cover_prompt: str | None = Field(default=None, alias="coverPrompt")
    cover_image_url: str | None = Field(default=None, alias="coverImageUrl")


class MarketingPlayerDetail(BaseModel):
    """玩家端详情页物料。"""

    model_config = ConfigDict(populate_by_name=True)

    detail_copy: str | None = Field(default=None, alias="detailCopy")
    image_prompts: list[str] = Field(default_factory=list, alias="imagePrompts")
    image_urls: list[str] = Field(default_factory=list, alias="imageUrls")


class MarketingMoments(BaseModel):
    """朋友圈私域传播物料。"""

    model_config = ConfigDict(populate_by_name=True)

    copy: str | None = None
    poster_title: str | None = Field(default=None, alias="posterTitle")
    poster_subtitle: str | None = Field(default=None, alias="posterSubtitle")
    poster_prompt: str | None = Field(default=None, alias="posterPrompt")
    poster_image_url: str | None = Field(default=None, alias="posterImageUrl")


class ScriptMarketingGenerateRequest(BaseModel):
    """生成剧本运营物料的请求。

    第一版不落库，作为“AI 草稿”返回给前端；店长确认后可复制或填入场次。
    """

    model_config = ConfigDict(populate_by_name=True)

    purpose: str = Field(
        default="session_fill",
        pattern=r"^(script_profile|session_fill|cover_and_detail)$",
    )
    tone: str = Field(default="新手友好、商业宣传", max_length=80)
    avoid_spoilers: bool = Field(default=True, alias="avoidSpoilers")
    extra_requirement: str | None = Field(
        default=None, alias="extraRequirement", max_length=500
    )
    usage_type: str = Field(
        default="session_recruiting", alias="usageType", max_length=60
    )
    usage_label: str = Field(default="拼车招募版", alias="usageLabel", max_length=80)
    style_profile_id: uuid.UUID | None = Field(
        default=None,
        alias="styleProfileId",
        description="可选：创建物料时绑定的美术视觉规律档案",
    )


class ScriptMarketingApproveRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    manager_feedback: str | None = Field(
        default=None, alias="managerFeedback", max_length=1000
    )


class ScriptMarketingGenerateImagesRequest(BaseModel):
    """为已确认的运营物料生成真实展示图片。"""

    model_config = ConfigDict(populate_by_name=True)

    include_cover: bool = Field(default=True, alias="includeCover")
    include_detail: bool = Field(default=False, alias="includeDetail")
    prompt_override: str | None = Field(
        default=None, alias="promptOverride", max_length=1200
    )
    style_profile_id: uuid.UUID | None = Field(
        default=None,
        alias="styleProfileId",
        description="可选：美术素材库沉淀出的视觉规律档案",
    )


class ScriptMarketingAssetResult(BaseModel):
    """剧本运营物料草稿。"""

    model_config = ConfigDict(populate_by_name=True)

    document_id: uuid.UUID = Field(alias="documentId")
    version_id: uuid.UUID | None = Field(alias="versionId")
    asset_id: uuid.UUID | None = Field(default=None, alias="assetId")
    version_no: int | None = Field(default=None, alias="versionNo")
    status: str = "draft"
    manager_feedback: str | None = Field(default=None, alias="managerFeedback")
    title: str
    summary: str
    selling_points: list[str] = Field(alias="sellingPoints")
    suitable_players: list[str] = Field(alias="suitablePlayers")
    tags: list[str]
    cover_prompt: str = Field(alias="coverPrompt")
    style_profile_id: uuid.UUID | None = Field(default=None, alias="styleProfileId")
    final_image_prompts: dict[str, object] = Field(default_factory=dict, alias="finalImagePrompts")
    cover_image_url: str | None = Field(default=None, alias="coverImageUrl")
    detail_copy: str = Field(alias="detailCopy")
    detail_image_prompts: list[str] = Field(alias="detailImagePrompts")
    detail_image_urls: list[str] = Field(default_factory=list, alias="detailImageUrls")
    image_status: str = Field(default="not_started", alias="imageStatus")
    image_error_message: str | None = Field(default=None, alias="imageErrorMessage")
    image_generations: list[dict[str, object]] = Field(
        default_factory=list, alias="imageGenerations"
    )
    risk_notes: list[str] = Field(alias="riskNotes")
    sources: list[str]
    created_at: datetime | None = Field(default=None, alias="createdAt")
    approved_at: datetime | None = Field(default=None, alias="approvedAt")
    usage_type: str = Field(default="session_recruiting", alias="usageType")
    usage_label: str = Field(default="拼车招募版", alias="usageLabel")
    session_form_defaults: MarketingSessionFormDefaults = Field(
        default_factory=MarketingSessionFormDefaults, alias="sessionFormDefaults"
    )
    player_card: MarketingPlayerCard = Field(
        default_factory=MarketingPlayerCard, alias="playerCard"
    )
    player_detail: MarketingPlayerDetail = Field(
        default_factory=MarketingPlayerDetail, alias="playerDetail"
    )
    moments: MarketingMoments = Field(default_factory=MarketingMoments)
