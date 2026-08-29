"""加载知识库版本中的原始文件为 Markdown。"""

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.mineru.client import MineruClient
from app.integrations.storage.oss import OssStorage
from app.modules.knowledge.exceptions import KnowledgeDocumentNotFoundError
from app.modules.knowledge.loaders import (
    LoadedMarkdown,
    detect_loader_type,
    load_markdown,
)
from app.modules.knowledge.models import KnowledgeParsedFile, KnowledgeParsedFileStatus
from app.modules.knowledge.repository import get_version_for_manifest
from app.modules.knowledge.schemas import (
    LoadKnowledgeDocumentResponse,
    ParsedKnowledgeFileResponse,
    ParsedMarkdownResponse,
)


def _parsed_prefix(store_id: uuid.UUID, document_id: uuid.UUID, version_id: uuid.UUID) -> str:
    return f"stores/{store_id}/knowledge/{document_id}/versions/{version_id}/parsed"


def _to_response(parsed: KnowledgeParsedFile) -> ParsedKnowledgeFileResponse:
    return ParsedKnowledgeFileResponse(
        id=parsed.id,
        fileId=parsed.file_id,
        relativePath=parsed.file.relative_path,
        loaderType=parsed.loader_type,
        status=parsed.status.value,
        markdownKey=parsed.markdown_key,
        textSha256=parsed.text_sha256,
        charCount=parsed.char_count,
        errorMessage=parsed.error_message,
        completedAt=parsed.completed_at,
    )


async def load_document_action(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    store_id: uuid.UUID,
    db: AsyncSession,
    storage: OssStorage | None = None,
) -> LoadKnowledgeDocumentResponse:
    version = await get_version_for_manifest(document_id, version_id, store_id, db)
    if version is None:
        raise KnowledgeDocumentNotFoundError("知识库版本不存在")

    existing = {parsed.file_id: parsed for parsed in version.parsed_files}
    oss_storage = storage or OssStorage()
    parsed_files: list[KnowledgeParsedFile] = []
    prefix = _parsed_prefix(store_id, document_id, version_id)

    for file in version.files:
        parsed = existing.get(file.id)
        if parsed and parsed.status is KnowledgeParsedFileStatus.READY:
            parsed_files.append(parsed)
            continue

        parsed = parsed or KnowledgeParsedFile(
            id=uuid.uuid4(),
            version_id=version.id,
            file_id=file.id,
            loader_type=detect_loader_type(file),
        )
        parsed.file = file
        parsed.status = KnowledgeParsedFileStatus.PROCESSING
        parsed.error_message = None
        db.add(parsed)
        await db.flush()

        try:
            if parsed.loader_type == "mineru_pdf":
                source_url = oss_storage.presign_get(file.object_key)
                markdown = await MineruClient().parse_pdf_url(
                    source_url, file.relative_path
                )
                loaded = LoadedMarkdown(loader_type="mineru_pdf", markdown=markdown)
            else:
                source = await oss_storage.get_bytes(file.object_key)
                loaded = load_markdown(file, source)
            markdown_key = f"{prefix}/{file.id}/content.md"
            await oss_storage.put_text(markdown_key, loaded.markdown)
            parsed.loader_type = loaded.loader_type
            parsed.markdown_key = markdown_key
            parsed.text_sha256 = hashlib.sha256(loaded.markdown.encode("utf-8")).hexdigest()
            parsed.char_count = len(loaded.markdown)
            parsed.status = KnowledgeParsedFileStatus.READY
            parsed.completed_at = datetime.now(UTC)
        except Exception as error:  # noqa: BLE001
            parsed.status = KnowledgeParsedFileStatus.FAILED
            parsed.error_message = str(error)
            parsed.completed_at = datetime.now(UTC)
        parsed_files.append(parsed)

    await db.flush()
    return LoadKnowledgeDocumentResponse(
        documentId=document_id,
        versionId=version_id,
        files=[_to_response(parsed) for parsed in parsed_files],
    )


async def list_loaded_files_action(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    store_id: uuid.UUID,
    db: AsyncSession,
) -> LoadKnowledgeDocumentResponse:
    version = await get_version_for_manifest(document_id, version_id, store_id, db)
    if version is None:
        raise KnowledgeDocumentNotFoundError("知识库版本不存在")

    return LoadKnowledgeDocumentResponse(
        documentId=document_id,
        versionId=version_id,
        files=[_to_response(parsed) for parsed in version.parsed_files],
    )


async def get_loaded_markdown_action(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    parsed_file_id: uuid.UUID,
    store_id: uuid.UUID,
    db: AsyncSession,
    storage: OssStorage | None = None,
) -> ParsedMarkdownResponse:
    version = await get_version_for_manifest(document_id, version_id, store_id, db)
    if version is None:
        raise KnowledgeDocumentNotFoundError("知识库版本不存在")

    parsed = next(
        (item for item in version.parsed_files if item.id == parsed_file_id),
        None,
    )
    if parsed is None or not parsed.markdown_key:
        raise KnowledgeDocumentNotFoundError("加载后的 Markdown 不存在")

    markdown = await (storage or OssStorage()).get_text(parsed.markdown_key)
    return ParsedMarkdownResponse(
        parsedFileId=parsed.id,
        fileId=parsed.file_id,
        relativePath=parsed.file.relative_path,
        markdown=markdown,
    )
