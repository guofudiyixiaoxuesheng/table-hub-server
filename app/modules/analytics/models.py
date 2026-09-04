"""AI 质量评估相关 ORM 模型。"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RagEvaluationStatus(str, enum.Enum):
    """RAG 评估任务状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RagEvaluationJob(Base):
    """RAG 问答质量评估任务。

    这张表保存“当时那次 RAG 问答”的快照，避免后续知识库重切片、
    重向量化后无法复现当时回答质量。
    """

    __tablename__ = "rag_evaluation_jobs"
    __table_args__ = (
        Index("ix_rag_eval_store_status_created", "store_id", "status", "created_at"),
        Index("ix_rag_eval_session_created", "chat_session_id", "created_at"),
        Index("ix_rag_eval_document_created", "document_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=True
    )
    chat_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    guest_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    scene: Mapped[str] = mapped_column(String(40), nullable=False, server_default="script_rag")
    intent: Mapped[str | None] = mapped_column(String(80), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL"), nullable=True
    )
    document_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    contexts_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    citations_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    metrics_json: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    overall_score: Mapped[float | None] = mapped_column(nullable=True)
    needs_review: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    judge_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[RagEvaluationStatus] = mapped_column(
        Enum(
            RagEvaluationStatus,
            name="rag_evaluation_status",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=RagEvaluationStatus.PENDING,
        server_default=RagEvaluationStatus.PENDING.value,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
