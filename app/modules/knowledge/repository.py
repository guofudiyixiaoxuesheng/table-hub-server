"""知识库资源数据库访问函数。"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.knowledge.models import (
    KnowledgeChunk,
    KnowledgeChunkEmbedding,
    KnowledgeDocument,
    KnowledgeFile,
    KnowledgeParsedAsset,
    KnowledgeParsedFile,
    KnowledgeUploadSession,
    KnowledgeVersion,
)


async def list_documents(
    store_id: uuid.UUID,
    resource_type: str | None,
    db: AsyncSession,
) -> list[tuple[KnowledgeDocument, KnowledgeVersion | None]]:
    statement = (
        select(KnowledgeDocument, KnowledgeVersion)
        .outerjoin(
            KnowledgeVersion,
            KnowledgeDocument.active_version_id == KnowledgeVersion.id,
        )
        .where(
            KnowledgeDocument.store_id == store_id,
            KnowledgeDocument.deleted_at.is_(None),
        )
        .order_by(KnowledgeDocument.updated_at.desc())
    )
    if resource_type:
        statement = statement.where(KnowledgeDocument.resource_type == resource_type)
    result = await db.execute(statement)
    return list(result.tuples().all())


async def get_document(
    document_id: uuid.UUID, store_id: uuid.UUID, db: AsyncSession
) -> KnowledgeDocument | None:
    statement = select(KnowledgeDocument).where(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.store_id == store_id,
        KnowledgeDocument.deleted_at.is_(None),
    )
    return await db.scalar(statement)


async def get_document_with_versions(
    document_id: uuid.UUID, store_id: uuid.UUID, db: AsyncSession
) -> KnowledgeDocument | None:
    statement = (
        select(KnowledgeDocument)
        .where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.store_id == store_id,
            KnowledgeDocument.deleted_at.is_(None),
        )
        .options(
            selectinload(KnowledgeDocument.versions).selectinload(
                KnowledgeVersion.upload_sessions
            )
        )
    )
    return await db.scalar(statement)


async def version_exists(
    document_id: uuid.UUID, version_label: str, db: AsyncSession
) -> bool:
    statement = select(KnowledgeVersion.id).where(
        KnowledgeVersion.document_id == document_id,
        KnowledgeVersion.version_label == version_label,
    )
    return await db.scalar(statement) is not None


async def add_upload_graph(
    document: KnowledgeDocument,
    version: KnowledgeVersion,
    files: list[KnowledgeFile],
    upload_session: KnowledgeUploadSession,
    db: AsyncSession,
) -> None:
    db.add_all([document, version, *files, upload_session])
    await db.flush()


async def get_upload_session(
    upload_id: uuid.UUID, db: AsyncSession
) -> KnowledgeUploadSession | None:
    statement = (
        select(KnowledgeUploadSession)
        .where(KnowledgeUploadSession.id == upload_id)
        .options(
            selectinload(KnowledgeUploadSession.version).selectinload(
                KnowledgeVersion.document
            ),
            selectinload(KnowledgeUploadSession.version).selectinload(
                KnowledgeVersion.files
            ),
        )
    )
    return await db.scalar(statement)


async def get_version_for_manifest(
    document_id: uuid.UUID, version_id: uuid.UUID, store_id: uuid.UUID, db: AsyncSession
) -> KnowledgeVersion | None:
    statement = (
        select(KnowledgeVersion)
        .join(
            KnowledgeDocument,
            KnowledgeVersion.document_id == KnowledgeDocument.id,
        )
        .where(
            KnowledgeVersion.id == version_id,
            KnowledgeVersion.document_id == document_id,
            KnowledgeDocument.store_id == store_id,
            KnowledgeDocument.deleted_at.is_(None),
        )
        .options(
            selectinload(KnowledgeVersion.document),
            selectinload(KnowledgeVersion.files),
            selectinload(KnowledgeVersion.parsed_files).selectinload(
                KnowledgeParsedFile.file
            ),
            selectinload(KnowledgeVersion.parsed_files).selectinload(
                KnowledgeParsedFile.assets
            ),
            selectinload(KnowledgeVersion.parsed_assets).selectinload(
                KnowledgeParsedAsset.source_file
            ),
            selectinload(KnowledgeVersion.chunks).selectinload(KnowledgeChunk.file),
            selectinload(KnowledgeVersion.chunks).selectinload(
                KnowledgeChunk.parsed_file
            ),
            selectinload(KnowledgeVersion.chunks).selectinload(
                KnowledgeChunk.embeddings
            ),
            selectinload(KnowledgeVersion.chunk_embeddings).selectinload(
                KnowledgeChunkEmbedding.chunk
            ),
        )
    )
    return await db.scalar(statement)


async def get_parsed_asset(
    asset_id: uuid.UUID, store_id: uuid.UUID, db: AsyncSession
) -> KnowledgeParsedAsset | None:
    statement = (
        select(KnowledgeParsedAsset)
        .join(KnowledgeVersion, KnowledgeParsedAsset.version_id == KnowledgeVersion.id)
        .join(KnowledgeDocument, KnowledgeVersion.document_id == KnowledgeDocument.id)
        .where(
            KnowledgeParsedAsset.id == asset_id,
            KnowledgeDocument.store_id == store_id,
            KnowledgeDocument.deleted_at.is_(None),
        )
    )
    return await db.scalar(statement)
