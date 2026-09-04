"""计算运营指标与 AI 对话质量评估。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from openai import LengthFinishReasonError, OpenAIError
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ApplicationError
from app.integrations.llm.client import ChatModelNotConfiguredError, structured_chat_completion
from app.modules.analytics.models import RagEvaluationJob, RagEvaluationStatus
from app.modules.analytics.schemas import (
    RagEvaluationCreateRequest,
    RagEvaluationJudgeResult,
    RagEvaluationJobResponse,
    RagEvaluationListResponse,
    RagEvaluationSummaryResponse,
)
from app.modules.chat.models import ChatSession
from app.observability.langfuse import langfuse_enabled


class RagEvaluationNotFoundError(ApplicationError):
    status_code = 404
    code = "rag_evaluation_not_found"


JUDGE_PROMPT = """你是剧本杀门店 AI 回答质量评估员。
请根据用户问题、问题改写、RAG 召回上下文和 AI 回答，评估回答质量。
你必须返回 valid JSON，且 JSON 字段必须符合 schema。

评分范围 0 到 1：
- faithfulness：回答是否忠于召回上下文，有没有胡编。
- answer_relevancy：回答是否直接回应用户问题。
- context_utilization：回答是否充分利用召回资料。
- spoiler_safety：是否避免泄露用户权限外的剧透。
- dm_usefulness：如果是 DM/剧本运营问题，回答是否有执行价值；否则按通用实用性评分。

如果存在明显胡编、答非所问、资料不足却强答、剧透风险，请 needs_review=true。
reason 必须用中文简要说明评分原因。
请严格输出符合 schema 的 JSON 结构化结果。
"""


def _to_response(job: RagEvaluationJob) -> RagEvaluationJobResponse:
    return RagEvaluationJobResponse(
        id=job.id,
        storeId=job.store_id,
        chatSessionId=job.chat_session_id,
        userId=job.user_id,
        guestId=job.guest_id,
        traceId=job.trace_id,
        threadId=job.thread_id,
        scene=job.scene,
        intent=job.intent,
        documentId=job.document_id,
        documentName=job.document_name,
        question=job.question,
        rewrittenQuery=job.rewritten_query,
        answer=job.answer,
        contexts=job.contexts_json or [],
        citations=job.citations_json or [],
        metrics=job.metrics_json or {},
        overallScore=job.overall_score,
        needsReview=job.needs_review,
        judgeReason=job.judge_reason,
        status=job.status.value,
        errorMessage=job.error_message,
        createdAt=job.created_at,
        startedAt=job.started_at,
        completedAt=job.completed_at,
    )


def _extract_document(
    chunks: list[dict[str, object]], citations: list[dict[str, object]]
) -> tuple[uuid.UUID | None, str | None]:
    for item in [*chunks, *citations]:
        raw_id = item.get("document_id") or item.get("documentId") or item.get("script_id") or item.get("scriptId")
        if not raw_id:
            continue
        try:
            return uuid.UUID(str(raw_id)), str(item.get("document_name") or item.get("documentName") or "")
        except ValueError:
            continue
    return None, None


async def create_rag_evaluation_job(
    *,
    store_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    guest_id: str | None,
    chat_session_id: uuid.UUID | None,
    payload: RagEvaluationCreateRequest,
    db: AsyncSession,
) -> RagEvaluationJobResponse:
    job = RagEvaluationJob(
        store_id=store_id,
        user_id=user_id,
        guest_id=guest_id,
        chat_session_id=chat_session_id,
        thread_id=payload.thread_id,
        scene="script_rag",
        intent=payload.intent,
        document_id=payload.document_id,
        document_name=payload.document_name,
        question=payload.question,
        rewritten_query=payload.rewritten_query,
        answer=payload.answer,
        contexts_json=payload.contexts,
        citations_json=payload.citations,
    )
    db.add(job)
    await db.flush()
    return _to_response(job)


async def maybe_create_rag_evaluation_from_state(
    *,
    thread_id: str,
    store_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    guest_id: str | None,
    chat_session: ChatSession,
    question: str,
    state: dict[str, Any],
    db: AsyncSession,
) -> RagEvaluationJob | None:
    """RAG 对话完成后创建待评估快照。"""

    if state.get("scene") != "script_rag":
        return None
    chunks = state.get("retrieved_chunks") or []
    answer = str(state.get("answer") or "").strip()
    if not answer or not isinstance(chunks, list) or not chunks:
        return None

    citations = state.get("citations") if isinstance(state.get("citations"), list) else []
    document_id = None
    if state.get("script_id"):
        try:
            document_id = uuid.UUID(str(state.get("script_id")))
        except ValueError:
            document_id = None
    fallback_document_id, fallback_document_name = _extract_document(chunks, citations)
    job = RagEvaluationJob(
        store_id=store_id,
        user_id=user_id,
        guest_id=guest_id,
        chat_session_id=chat_session.id,
        thread_id=thread_id,
        scene="script_rag",
        intent=str(state.get("intent") or "") or None,
        document_id=document_id or fallback_document_id,
        document_name=str(state.get("script_name") or fallback_document_name or "") or None,
        question=question,
        rewritten_query=str(state.get("context_rewritten_query") or state.get("rewritten_query") or "") or None,
        answer=answer,
        contexts_json=chunks[:10],
        citations_json=citations[:10],
        status=RagEvaluationStatus.PENDING,
    )
    db.add(job)
    await db.flush()
    return job


async def list_rag_evaluation_jobs(
    *,
    store_id: uuid.UUID,
    db: AsyncSession,
    status: RagEvaluationStatus | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> RagEvaluationListResponse:
    filters = [RagEvaluationJob.store_id == store_id]
    if status:
        filters.append(RagEvaluationJob.status == status)
    if keyword and keyword.strip():
        term = f"%{keyword.strip()}%"
        filters.append(or_(RagEvaluationJob.question.ilike(term), RagEvaluationJob.answer.ilike(term)))

    total = int(await db.scalar(select(func.count()).select_from(RagEvaluationJob).where(*filters)) or 0)
    rows = list(
        await db.scalars(
            select(RagEvaluationJob)
            .where(*filters)
            .order_by(RagEvaluationJob.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    )
    return RagEvaluationListResponse(
        items=[_to_response(row) for row in rows],
        meta={"total": total, "page": page, "pageSize": page_size},
    )


async def get_rag_evaluation_job(
    *,
    store_id: uuid.UUID,
    job_id: uuid.UUID,
    db: AsyncSession,
) -> RagEvaluationJobResponse:
    job = await db.scalar(select(RagEvaluationJob).where(RagEvaluationJob.id == job_id, RagEvaluationJob.store_id == store_id))
    if job is None:
        raise RagEvaluationNotFoundError("评估任务不存在")
    return _to_response(job)


async def get_rag_evaluation_summary(
    *,
    store_id: uuid.UUID,
    db: AsyncSession,
) -> RagEvaluationSummaryResponse:
    rows = (
        await db.execute(
            select(RagEvaluationJob.status, func.count())
            .where(RagEvaluationJob.store_id == store_id)
            .group_by(RagEvaluationJob.status)
        )
    ).all()
    counts = {status.value: int(count) for status, count in rows}
    average_score = await db.scalar(
        select(func.avg(RagEvaluationJob.overall_score)).where(
            RagEvaluationJob.store_id == store_id,
            RagEvaluationJob.status == RagEvaluationStatus.COMPLETED,
        )
    )
    needs_review = int(
        await db.scalar(
            select(func.count()).select_from(RagEvaluationJob).where(
                RagEvaluationJob.store_id == store_id,
                RagEvaluationJob.needs_review.is_(True),
            )
        )
        or 0
    )
    return RagEvaluationSummaryResponse(
        total=sum(counts.values()),
        pending=counts.get("pending", 0),
        completed=counts.get("completed", 0),
        failed=counts.get("failed", 0),
        needsReview=needs_review,
        averageScore=round(float(average_score), 4) if average_score is not None else None,
    )


def _local_quality_metrics(job: RagEvaluationJob) -> dict[str, object]:
    """不调用外部模型的本地启发式评分。

    这不是 RAGAS/LLM Judge，只用于第一版把流程跑通和标记明显风险。
    """

    answer_len = len(job.answer.strip())
    context_count = len(job.contexts_json or [])
    citations_count = len(job.citations_json or [])
    has_context = context_count > 0
    faithfulness = 0.75 if has_context else 0.2
    answer_relevancy = 0.7 if answer_len >= 30 else 0.35
    context_utilization = min(1.0, 0.35 + context_count * 0.08 + citations_count * 0.05)
    spoiler_safety = 0.65 if any(word in job.question for word in ["凶手", "真相", "复盘", "答案"]) else 0.85
    dm_usefulness = 0.78 if any(word.lower() in job.question.lower() for word in ["dm", "开本", "流程", "控场"]) else 0.65
    overall = round(
        (faithfulness + answer_relevancy + context_utilization + spoiler_safety + dm_usefulness) / 5,
        4,
    )
    return {
        "faithfulness": round(faithfulness, 4),
        "answer_relevancy": round(answer_relevancy, 4),
        "context_utilization": round(context_utilization, 4),
        "spoiler_safety": round(spoiler_safety, 4),
        "dm_usefulness": round(dm_usefulness, 4),
        "overall_score": overall,
        "judge_type": "local_heuristic",
    }


def _overall(metrics: RagEvaluationJudgeResult) -> float:
    values = [
        metrics.faithfulness,
        metrics.answer_relevancy,
        metrics.context_utilization,
        metrics.spoiler_safety,
        metrics.dm_usefulness,
    ]
    return round(sum(values) / len(values), 4)


def _evaluation_prompt(job: RagEvaluationJob) -> str:
    context_preview = "\n\n".join(
        f"[{index}] {item.get('relative_path') or item.get('relativePath') or item.get('title') or '未知来源'}\n"
        f"{str(item.get('content') or '')[:1200]}"
        for index, item in enumerate((job.contexts_json or [])[:8], start=1)
    )
    return (
        f"用户问题：{job.question}\n\n"
        f"问题改写：{job.rewritten_query or '无'}\n\n"
        f"召回上下文：\n{context_preview or '无'}\n\n"
        f"AI 回答：\n{job.answer[:6000]}"
    )


async def _llm_quality_metrics(job: RagEvaluationJob) -> tuple[dict[str, object], float, bool, str]:
    result = await structured_chat_completion(
        RagEvaluationJudgeResult,
        [SystemMessage(content=JUDGE_PROMPT), HumanMessage(content=_evaluation_prompt(job))],
        temperature=0,
        max_tokens=1200,
    )
    overall_score = _overall(result)
    metrics = result.model_dump(mode="json")
    metrics["overall_score"] = overall_score
    metrics["judge_type"] = "llm_judge"
    return metrics, overall_score, result.needs_review or overall_score < 0.72, result.reason


def _try_write_langfuse_scores(job: RagEvaluationJob) -> None:
    """将评估分数回写到 Langfuse。

    trace_id 还没接入时直接跳过；Langfuse 网络失败不能影响业务评估入库。
    """

    if not job.trace_id or not langfuse_enabled():
        return
    try:
        from langfuse import get_client

        client = get_client()
        for key in [
            "faithfulness",
            "answer_relevancy",
            "context_utilization",
            "spoiler_safety",
            "dm_usefulness",
            "overall_score",
        ]:
            value = job.metrics_json.get(key)
            if isinstance(value, int | float):
                client.create_score(
                    trace_id=job.trace_id,
                    name=key,
                    value=float(value),
                    data_type="NUMERIC",
                    comment=job.judge_reason,
                )
    except Exception:
        return


async def run_rag_evaluation_job(
    *,
    store_id: uuid.UUID,
    job_id: uuid.UUID,
    db: AsyncSession,
) -> RagEvaluationJobResponse:
    job = await db.scalar(select(RagEvaluationJob).where(RagEvaluationJob.id == job_id, RagEvaluationJob.store_id == store_id))
    if job is None:
        raise RagEvaluationNotFoundError("评估任务不存在")

    job.status = RagEvaluationStatus.RUNNING
    job.started_at = datetime.now(UTC)
    job.error_message = None
    await db.flush()

    try:
        metrics, overall_score, needs_review, reason = await _llm_quality_metrics(job)
        job.metrics_json = metrics
        job.overall_score = overall_score
        job.needs_review = needs_review
        job.judge_reason = reason
        job.status = RagEvaluationStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
        _try_write_langfuse_scores(job)
    except (
        ChatModelNotConfiguredError,
        LengthFinishReasonError,
        OpenAIError,
        ValidationError,
        ValueError,
    ) as exc:
        metrics = _local_quality_metrics(job)
        job.metrics_json = metrics
        job.overall_score = float(metrics["overall_score"])
        job.needs_review = job.overall_score < 0.72
        job.judge_reason = f"LLM Judge 调用失败，已降级为本地启发式评分：{exc}"
        job.status = RagEvaluationStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
    await db.flush()
    return _to_response(job)
