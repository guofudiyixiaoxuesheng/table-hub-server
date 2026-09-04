"""运营指标、AI 质量评估响应数据结构。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RagEvaluationStatusValue = Literal["pending", "running", "completed", "failed", "skipped"]


class RagEvaluationCreateRequest(BaseModel):
    """手动创建评估任务；通常用于调试或补录样本。"""

    model_config = ConfigDict(populate_by_name=True)

    thread_id: str | None = Field(default=None, alias="threadId", max_length=120)
    question: str = Field(min_length=1, max_length=4000)
    answer: str = Field(min_length=1)
    rewritten_query: str | None = Field(default=None, alias="rewrittenQuery")
    contexts: list[dict[str, object]] = Field(default_factory=list)
    citations: list[dict[str, object]] = Field(default_factory=list)
    document_id: uuid.UUID | None = Field(default=None, alias="documentId")
    document_name: str | None = Field(default=None, alias="documentName", max_length=180)
    intent: str | None = Field(default=None, max_length=80)


class RagEvaluationJobResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    store_id: uuid.UUID | None = Field(alias="storeId")
    chat_session_id: uuid.UUID | None = Field(alias="chatSessionId")
    user_id: uuid.UUID | None = Field(alias="userId")
    guest_id: str | None = Field(alias="guestId")
    trace_id: str | None = Field(alias="traceId")
    thread_id: str | None = Field(alias="threadId")
    scene: str
    intent: str | None
    document_id: uuid.UUID | None = Field(alias="documentId")
    document_name: str | None = Field(alias="documentName")
    question: str
    rewritten_query: str | None = Field(alias="rewrittenQuery")
    answer: str
    contexts: list[dict[str, object]]
    citations: list[dict[str, object]]
    metrics: dict[str, object]
    overall_score: float | None = Field(alias="overallScore")
    needs_review: bool = Field(alias="needsReview")
    judge_reason: str | None = Field(alias="judgeReason")
    status: RagEvaluationStatusValue
    error_message: str | None = Field(alias="errorMessage")
    created_at: datetime = Field(alias="createdAt")
    started_at: datetime | None = Field(alias="startedAt")
    completed_at: datetime | None = Field(alias="completedAt")


class RagEvaluationListMeta(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    total: int
    page: int
    page_size: int = Field(alias="pageSize")


class RagEvaluationListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[RagEvaluationJobResponse]
    meta: RagEvaluationListMeta


class RagEvaluationSummaryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    total: int
    pending: int
    completed: int
    failed: int
    needs_review: int = Field(alias="needsReview")
    average_score: float | None = Field(alias="averageScore")


class RagEvaluationJudgeResult(BaseModel):
    """LLM Judge 输出结构。"""

    faithfulness: float = Field(ge=0, le=1)
    answer_relevancy: float = Field(ge=0, le=1)
    context_utilization: float = Field(ge=0, le=1)
    spoiler_safety: float = Field(ge=0, le=1)
    dm_usefulness: float = Field(ge=0, le=1)
    needs_review: bool
    reason: str = Field(default="模型未返回评估说明。", max_length=1000)
