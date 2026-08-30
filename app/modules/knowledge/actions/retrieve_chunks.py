"""知识库统一检索器：BM25、向量和混合召回。"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.qwen.embedding import QwenEmbeddingClient
from app.integrations.qwen.rerank import QwenRerankClient
from app.modules.knowledge.exceptions import (
    KnowledgeDocumentNotFoundError,
    KnowledgeDocumentUploadError,
)
from app.modules.knowledge.repository import get_version_for_manifest
from app.modules.knowledge.schemas import (
    KnowledgeRetrievedChunk,
    KnowledgeRetrieveRequest,
    KnowledgeRetrieveResponse,
)


@dataclass(frozen=True, slots=True)
class RetrievedRow:
    chunk_id: uuid.UUID
    file_id: uuid.UUID
    relative_path: str
    title: str | None
    act: str | None
    role_name: str | None
    chunk_type: str
    content: str
    score: float
    score_type: str


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(item) for item in vector) + "]"


def _base_filters(payload: KnowledgeRetrieveRequest) -> tuple[str, dict[str, object]]:
    filters = [
        "c.version_id = :version_id",
        "d.deleted_at IS NULL",
    ]
    params: dict[str, object] = {
        "query": payload.query,
        "limit": payload.top_k,
    }
    if payload.role_name:
        filters.append("c.role_name = :role_name")
        params["role_name"] = payload.role_name
    if payload.act:
        filters.append("c.act = :act")
        params["act"] = payload.act
    if payload.chunk_type:
        filters.append("c.chunk_type = :chunk_type")
        params["chunk_type"] = payload.chunk_type
    return " AND ".join(filters), params


async def _bm25_search(
    *,
    version_id: uuid.UUID,
    payload: KnowledgeRetrieveRequest,
    db: AsyncSession,
) -> list[RetrievedRow]:
    filters, params = _base_filters(payload)
    params["version_id"] = version_id
    statement = text(
        f"""
        SELECT
            c.id AS chunk_id,
            c.file_id,
            f.relative_path,
            c.title,
            c.act,
            c.role_name,
            c.chunk_type::text AS chunk_type,
            c.content,
            pdb.score(c.id) AS score
        FROM knowledge_chunks c
        JOIN knowledge_files f ON f.id = c.file_id
        JOIN knowledge_documents d ON d.id = c.document_id
        WHERE {filters}
          AND (c.content ||| :query OR c.title ||| :query)
        ORDER BY score DESC
        LIMIT :limit
        """
    )
    rows = (await db.execute(statement, params)).mappings().all()
    return [
        RetrievedRow(
            chunk_id=row["chunk_id"],
            file_id=row["file_id"],
            relative_path=row["relative_path"],
            title=row["title"],
            act=row["act"],
            role_name=row["role_name"],
            chunk_type=row["chunk_type"],
            content=row["content"],
            score=float(row["score"]),
            score_type="bm25",
        )
        for row in rows
    ]


async def _vector_search(
    *,
    version_id: uuid.UUID,
    payload: KnowledgeRetrieveRequest,
    db: AsyncSession,
    client: QwenEmbeddingClient | None,
) -> list[RetrievedRow]:
    vector = (await (client or QwenEmbeddingClient()).embed_texts([payload.query]))[0]
    filters, params = _base_filters(payload)
    params.update(
        {
            "version_id": version_id,
            "model": settings.EMBEDDING_MODEL,
            "query_embedding": _vector_literal(vector),
        }
    )
    statement = text(
        f"""
        SELECT
            c.id AS chunk_id,
            c.file_id,
            f.relative_path,
            c.title,
            c.act,
            c.role_name,
            c.chunk_type::text AS chunk_type,
            c.content,
            1 - (e.embedding <=> CAST(:query_embedding AS vector)) AS score
        FROM knowledge_chunk_embeddings e
        JOIN knowledge_chunks c ON c.id = e.chunk_id
        JOIN knowledge_files f ON f.id = c.file_id
        JOIN knowledge_documents d ON d.id = c.document_id
        WHERE {filters}
          AND e.embedding_model = :model
          AND e.content_sha256 = c.content_sha256
        ORDER BY e.embedding <=> CAST(:query_embedding AS vector)
        LIMIT :limit
        """
    )
    rows = (await db.execute(statement, params)).mappings().all()
    return [
        RetrievedRow(
            chunk_id=row["chunk_id"],
            file_id=row["file_id"],
            relative_path=row["relative_path"],
            title=row["title"],
            act=row["act"],
            role_name=row["role_name"],
            chunk_type=row["chunk_type"],
            content=row["content"],
            score=float(row["score"]),
            score_type="vector",
        )
        for row in rows
    ]


RRF_K = 60


def _merge_results(rows: list[RetrievedRow], top_k: int) -> list[RetrievedRow]:
    """单路召回去重：保留同一 chunk 在当前召回方式下的最高分。"""
    merged: dict[uuid.UUID, RetrievedRow] = {}
    for row in rows:
        current = merged.get(row.chunk_id)
        if current is None or row.score > current.score:
            merged[row.chunk_id] = row
    return sorted(merged.values(), key=lambda item: item.score, reverse=True)[:top_k]


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievedRow]],
    *,
    top_k: int,
    k: int = RRF_K,
) -> list[RetrievedRow]:
    """用 RRF 融合多路召回结果。

    RRF 只关心每个 chunk 在每一路召回中的排名，不直接混加 BM25/向量原始分。
    同一个 chunk 被多路召回命中时，分数会累加，所以更容易排到前面。
    """
    fused: dict[uuid.UUID, tuple[RetrievedRow, float, set[str]]] = {}

    for ranked_rows in ranked_lists:
        seen_in_channel: set[uuid.UUID] = set()
        for rank, row in enumerate(ranked_rows, start=1):
            if row.chunk_id in seen_in_channel:
                continue
            seen_in_channel.add(row.chunk_id)

            base_row, current_score, score_types = fused.get(
                row.chunk_id, (row, 0.0, set())
            )
            if row.score > base_row.score:
                base_row = row
            score_types.add(row.score_type)
            fused[row.chunk_id] = (
                base_row,
                current_score + 1 / (k + rank),
                score_types,
            )

    results = [
        RetrievedRow(
            **{
                **asdict(row),
                "score": score,
                "score_type": "rrf" if len(score_types) > 1 else next(iter(score_types)),
            }
        )
        for row, score, score_types in fused.values()
    ]
    return sorted(results, key=lambda item: item.score, reverse=True)[:top_k]


async def rerank_results(
    *,
    query: str,
    rows: list[RetrievedRow],
    top_k: int,
    client: QwenRerankClient | None = None,
) -> list[RetrievedRow]:
    """对召回候选做精排。外部调用由 RERANK_ENABLED 显式控制。"""
    if not rows or not settings.RERANK_ENABLED:
        return []

    reranker = client or QwenRerankClient()
    reranked = await reranker.rerank(
        query=query,
        documents=[row.content for row in rows],
        top_n=min(top_k, settings.RERANK_TOP_N, len(rows)),
    )
    selected: list[RetrievedRow] = []
    for item in reranked:
        if item.index >= len(rows) or item.relevance_score < settings.RERANK_MIN_SCORE:
            continue
        row = rows[item.index]
        selected.append(
            RetrievedRow(
                **{
                    **asdict(row),
                    "score": item.relevance_score,
                    "score_type": "rerank",
                }
            )
        )
    return selected[:top_k]


class KnowledgeRetriever:
    def __init__(
        self,
        db: AsyncSession,
        embedding_client: QwenEmbeddingClient | None = None,
        rerank_client: QwenRerankClient | None = None,
    ) -> None:
        self.db = db
        self.embedding_client = embedding_client
        self.rerank_client = rerank_client

    async def retrieve(
        self,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
        store_id: uuid.UUID,
        payload: KnowledgeRetrieveRequest,
    ) -> KnowledgeRetrieveResponse:
        version = await get_version_for_manifest(document_id, version_id, store_id, self.db)
        if version is None:
            raise KnowledgeDocumentNotFoundError("知识库版本不存在")

        candidate_top_k = min(max(payload.top_k * 4, settings.RERANK_TOP_N), 30)
        candidate_payload = payload.model_copy(update={"top_k": candidate_top_k})
        bm25_rows: list[RetrievedRow] = []
        vector_rows: list[RetrievedRow] = []
        if payload.mode in {"bm25", "hybrid"}:
            bm25_rows = await _bm25_search(
                version_id=version_id, payload=candidate_payload, db=self.db
            )
        if payload.mode in {"vector", "hybrid"}:
            vector_rows = await _vector_search(
                version_id=version_id,
                payload=candidate_payload,
                db=self.db,
                client=self.embedding_client,
            )
        merged = (
            reciprocal_rank_fusion([bm25_rows, vector_rows], top_k=candidate_top_k)
            if payload.mode == "hybrid"
            else _merge_results(bm25_rows or vector_rows, candidate_top_k)
        )
        try:
            reranked = await rerank_results(
                query=payload.query,
                rows=merged,
                top_k=payload.top_k,
                client=self.rerank_client,
            )
            merged = reranked or merged[: payload.top_k]
        except KnowledgeDocumentUploadError:
            merged = merged[: payload.top_k]
        return KnowledgeRetrieveResponse(
            documentId=document_id,
            versionId=version_id,
            query=payload.query,
            mode=payload.mode,
            results=[
                KnowledgeRetrievedChunk(
                    chunkId=row.chunk_id,
                    fileId=row.file_id,
                    relativePath=row.relative_path,
                    title=row.title,
                    act=row.act,
                    roleName=row.role_name,
                    chunkType=row.chunk_type,
                    content=row.content,
                    score=row.score,
                    scoreType=row.score_type,
                )
                for row in merged
            ],
        )
