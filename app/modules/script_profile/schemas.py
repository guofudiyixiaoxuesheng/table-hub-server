"""剧本档案请求和响应结构。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScriptProfileGenerateRequest(BaseModel):
    """生成/重新生成剧本档案的入参。"""

    extra_requirement: str | None = Field(default=None, alias="extraRequirement", max_length=1000)

    model_config = ConfigDict(populate_by_name=True, validate_by_name=True)


class ScriptProfileUpdateRequest(BaseModel):
    """店长/DM 手动修正剧本档案。"""

    name: str | None = Field(default=None, max_length=200)
    alias_names: list[str] | None = Field(default=None, alias="aliasNames")
    genres: list[str] | None = None
    player_count_min: int | None = Field(default=None, alias="playerCountMin", ge=0)
    player_count_max: int | None = Field(default=None, alias="playerCountMax", ge=0)
    duration_minutes: int | None = Field(default=None, alias="durationMinutes", ge=0)
    difficulty: str | None = Field(default=None, max_length=80)
    dm_difficulty: str | None = Field(default=None, alias="dmDifficulty", max_length=80)
    summary: str | None = None
    story_background: str | None = Field(default=None, alias="storyBackground")
    truth_summary: str | None = Field(default=None, alias="truthSummary")
    selling_points: list[str] | None = Field(default=None, alias="sellingPoints")
    suitable_players: list[str] | None = Field(default=None, alias="suitablePlayers")
    core_mechanics: list[str] | None = Field(default=None, alias="coreMechanics")
    roles: list[dict[str, object]] | None = None
    material_checklist: list[str] | None = Field(default=None, alias="materialChecklist")
    opening_risks: list[str] | None = Field(default=None, alias="openingRisks")
    spoiler_notes: list[str] | None = Field(default=None, alias="spoilerNotes")

    model_config = ConfigDict(populate_by_name=True, validate_by_name=True)


class ScriptProfileDraft(BaseModel):
    """LLM 输出的剧本档案草稿。"""

    name: str
    alias_names: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    player_count_min: int | None = None
    player_count_max: int | None = None
    duration_minutes: int | None = None
    difficulty: str | None = None
    dm_difficulty: str | None = None
    summary: str | None = None
    story_background: str | None = None
    truth_summary: str | None = None
    selling_points: list[str] = Field(default_factory=list)
    suitable_players: list[str] = Field(default_factory=list)
    core_mechanics: list[str] = Field(default_factory=list)
    roles: list[dict[str, object]] = Field(default_factory=list)
    material_checklist: list[str] = Field(default_factory=list)
    opening_risks: list[str] = Field(default_factory=list)
    spoiler_notes: list[str] = Field(default_factory=list)
    confidence_score: int = Field(default=60, ge=0, le=100)
    needs_review_reasons: list[str] = Field(default_factory=list)


class ScriptProfileResult(BaseModel):
    """剧本档案返回结构。"""

    id: uuid.UUID
    document_id: uuid.UUID = Field(alias="documentId")
    version_id: uuid.UUID | None = Field(alias="versionId")
    name: str
    alias_names: list[str] = Field(alias="aliasNames")
    genres: list[str]
    player_count_min: int | None = Field(alias="playerCountMin")
    player_count_max: int | None = Field(alias="playerCountMax")
    duration_minutes: int | None = Field(alias="durationMinutes")
    difficulty: str | None
    dm_difficulty: str | None = Field(alias="dmDifficulty")
    summary: str | None
    story_background: str | None = Field(alias="storyBackground")
    truth_summary: str | None = Field(alias="truthSummary")
    selling_points: list[str] = Field(alias="sellingPoints")
    suitable_players: list[str] = Field(alias="suitablePlayers")
    core_mechanics: list[str] = Field(alias="coreMechanics")
    roles: list[dict[str, object]]
    material_checklist: list[str] = Field(alias="materialChecklist")
    opening_risks: list[str] = Field(alias="openingRisks")
    spoiler_notes: list[str] = Field(alias="spoilerNotes")
    source_chunk_ids: list[str] = Field(alias="sourceChunkIds")
    sources: list[str]
    confidence_score: int | None = Field(alias="confidenceScore")
    review_status: str = Field(alias="reviewStatus")
    error_message: str | None = Field(alias="errorMessage")
    approved_at: datetime | None = Field(alias="approvedAt")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True)
