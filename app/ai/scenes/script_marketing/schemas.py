"""剧本营销物料生成入参与出参。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
    cover_image_url: str | None = Field(default=None, alias="coverImageUrl")
    detail_copy: str = Field(alias="detailCopy")
    detail_image_prompts: list[str] = Field(alias="detailImagePrompts")
    detail_image_urls: list[str] = Field(default_factory=list, alias="detailImageUrls")
    session_form_defaults: dict[str, object] = Field(
        default_factory=dict, alias="sessionFormDefaults"
    )
    image_status: str = Field(default="not_started", alias="imageStatus")
    image_error_message: str | None = Field(default=None, alias="imageErrorMessage")
    risk_notes: list[str] = Field(alias="riskNotes")
    sources: list[str]
    created_at: datetime | None = Field(default=None, alias="createdAt")
    approved_at: datetime | None = Field(default=None, alias="approvedAt")
