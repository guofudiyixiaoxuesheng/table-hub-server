"""将知识库 chunk 向量化并保存到 pgvector。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.qwen.embedding import QwenEmbeddingClient
from app.modules.knowledge.exceptions import (
    KnowledgeDocumentNotFoundError,
    KnowledgeDocumentUploadError,
)
from app.modules.knowledge.models import (
    KnowledgeChunk,
    KnowledgeChunkEmbedding,
    KnowledgeEmbeddingStatus,
)
from app.modules.knowledge.repository import get_version_for_manifest
from app.modules.knowledge.schemas import KnowledgeEmbeddingSummaryResponse


def _summarize_embeddings(
    *,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    chunks: list[KnowledgeChunk],
) -> KnowledgeEmbeddingSummaryResponse:
    ready = 0
    failed = 0
    latest: datetime | None = None
    for chunk in chunks:
        matched = [
            item
            for item in chunk.embeddings
            if item.embedding_model == settings.EMBEDDING_MODEL
            and item.content_sha256 == chunk.content_sha256
        ]
        if not matched:
            continue
        embedding = matched[0]
        if embedding.status is KnowledgeEmbeddingStatus.READY:
            ready += 1
        elif embedding.status is KnowledgeEmbeddingStatus.FAILED:
            failed += 1
        if latest is None or embedding.updated_at > latest:
            latest = embedding.updated_at

    total = len(chunks)
    return KnowledgeEmbeddingSummaryResponse(
        documentId=document_id,
        versionId=version_id,
        model=settings.EMBEDDING_MODEL,
        dimension=settings.EMBEDDING_DIMENSION,
        totalChunks=total,
        embeddedChunks=ready,
        failedChunks=failed,
        pendingChunks=max(total - ready - failed, 0),
        updatedAt=latest,
    )


async def list_embeddings_action(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    store_id: uuid.UUID,
    db: AsyncSession,
) -> KnowledgeEmbeddingSummaryResponse:
    version = await get_version_for_manifest(document_id, version_id, store_id, db)
    if version is None:
        raise KnowledgeDocumentNotFoundError("知识库版本不存在")
    return _summarize_embeddings(
        document_id=document_id,
        version_id=version_id,
        chunks=version.chunks,
    )


async def embed_chunks_action(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    store_id: uuid.UUID,
    db: AsyncSession,
    client: QwenEmbeddingClient | None = None,
) -> KnowledgeEmbeddingSummaryResponse:
    version = await get_version_for_manifest(document_id, version_id, store_id, db)
    if version is None:
        raise KnowledgeDocumentNotFoundError("知识库版本不存在")

    pending = [
        chunk
        for chunk in version.chunks
        if not any(
            item.embedding_model == settings.EMBEDDING_MODEL
            and item.content_sha256 == chunk.content_sha256
            and item.status is KnowledgeEmbeddingStatus.READY
            for item in chunk.embeddings
        )
    ]
    embedding_client = client or QwenEmbeddingClient()
    for start in range(0, len(pending), settings.EMBEDDING_BATCH_SIZE):
        batch = pending[start : start + settings.EMBEDDING_BATCH_SIZE]
        vectors = await embedding_client.embed_texts([chunk.content for chunk in batch])
        for chunk, vector in zip(batch, vectors, strict=True):
            if len(vector) != settings.EMBEDDING_DIMENSION:
                raise KnowledgeDocumentUploadError(
                    f"向量维度不一致：期望 {settings.EMBEDDING_DIMENSION}，实际 {len(vector)}"
                )
            existing = next(
                (
                    item
                    for item in chunk.embeddings
                    if item.embedding_model == settings.EMBEDDING_MODEL
                ),
                None,
            )
            embedding = existing or KnowledgeChunkEmbedding(
                id=uuid.uuid4(),
                chunk_id=chunk.id,
                document_id=document_id,
                version_id=version_id,
                file_id=chunk.file_id,
                embedding_model=settings.EMBEDDING_MODEL,
                embedding_dimension=settings.EMBEDDING_DIMENSION,
                embedding=vector,
                content_sha256=chunk.content_sha256,
                status=KnowledgeEmbeddingStatus.READY,
            )
            embedding.embedding_dimension = settings.EMBEDDING_DIMENSION
            embedding.embedding = vector
            embedding.content_sha256 = chunk.content_sha256
            embedding.status = KnowledgeEmbeddingStatus.READY
            embedding.error_message = None
            db.add(embedding)
            if existing is None:
                chunk.embeddings.append(embedding)
    await db.flush()
    return _summarize_embeddings(
        document_id=document_id,
        version_id=version_id,
        chunks=version.chunks,
    )
