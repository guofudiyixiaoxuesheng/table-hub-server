"""AI 生成主持人 / DM 开本手册的数据结构。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OpeningManualGenerateRequest(BaseModel):
    """生成主持人手册的请求。"""

    model_config = ConfigDict(
        populate_by_name=True,
        validate_by_name=True,
        str_strip_whitespace=True,
    )

    style: str = Field(
        default="professional", pattern=r"^(professional|simple|training)$"
    )
    target_dm_level: str = Field(
        default="newbie", alias="targetDmLevel", pattern=r"^(newbie|experienced)$"
    )
    extra_requirement: str | None = Field(
        default=None, alias="extraRequirement", max_length=1000
    )


class OpeningManualSectionResult(BaseModel):
    """手册章节摘要，正文最终组装到完整 Markdown。"""

    model_config = ConfigDict(populate_by_name=True, validate_by_name=True)

    key: str
    title: str
    summary: str
    source_count: int = Field(default=0, alias="sourceCount")


class OpeningManualValidationResult(BaseModel):
    """主持人手册 LLM 审核结果。"""

    model_config = ConfigDict(populate_by_name=True, validate_by_name=True)

    passed: bool
    score: float = Field(ge=0, le=1)
    completeness: float = Field(ge=0, le=1)
    actionability: float = Field(ge=0, le=1)
    faithfulness: float = Field(ge=0, le=1)
    spoiler_safety: float = Field(alias="spoilerSafety", ge=0, le=1)
    missing_sections: list[str] = Field(default_factory=list, alias="missingSections")
    risk_notes: list[str] = Field(default_factory=list, alias="riskNotes")
    suggestions: list[str] = Field(default_factory=list)
    reason: str


class OpeningManualResult(BaseModel):
    """主持人手册列表/详情返回结构。"""

    model_config = ConfigDict(populate_by_name=True, validate_by_name=True)

    id: uuid.UUID
    document_id: uuid.UUID = Field(alias="documentId")
    version_id: uuid.UUID | None = Field(default=None, alias="versionId")
    manual_version_no: int = Field(alias="manualVersionNo")
    title: str
    style: str
    target_dm_level: str = Field(alias="targetDmLevel")
    status: str
    sections: list[OpeningManualSectionResult]
    sources: list[str]
    markdown_preview: str | None = Field(default=None, alias="markdownPreview")
    markdown: str | None = None
    validation_result: dict[str, object] = Field(
        default_factory=dict, alias="validationResult"
    )
    error_message: str | None = Field(default=None, alias="errorMessage")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    approved_at: datetime | None = Field(default=None, alias="approvedAt")


class ScriptFacts(BaseModel):
    """生成主持人手册前抽取的剧本全局事实锚点。"""

    model_config = ConfigDict(populate_by_name=True, validate_by_name=True)

    script_name: str = Field(alias="scriptName")
    player_count: str | None = Field(default=None, alias="playerCount")
    duration: str | None = None
    genre: str | None = None
    core_mechanics: list[str] = Field(default_factory=list, alias="coreMechanics")
    truth_summary: str | None = Field(default=None, alias="truthSummary")
    killer_or_culprit: str | None = Field(default=None, alias="killerOrCulprit")
    key_relationships: list[str] = Field(default_factory=list, alias="keyRelationships")
    timeline: list[str] = Field(default_factory=list)
    ending_conditions: list[str] = Field(default_factory=list, alias="endingConditions")
    spoiler_warnings: list[str] = Field(default_factory=list, alias="spoilerWarnings")
    conflicts: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
