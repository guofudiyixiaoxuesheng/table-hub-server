"""将已加载 Markdown 切成适合 RAG 的结构化 chunk。"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.storage.oss import OssStorage
from app.modules.knowledge.exceptions import KnowledgeDocumentNotFoundError
from app.modules.knowledge.models import (
    KnowledgeChunk,
    KnowledgeChunkStatus,
    KnowledgeChunkType,
    KnowledgeParsedFile,
    KnowledgeParsedFileStatus,
)
from app.modules.knowledge.repository import get_version_for_manifest
from app.modules.knowledge.schemas import (
    KnowledgeChunkFileSummary,
    KnowledgeChunkListResponse,
    KnowledgeChunkResponse,
)

MAX_CHARS = 900
OVERLAP_CHARS = 100
MARKDOWN_HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3"), ("####", "h4")]
MARKDOWN_HEADER_SPLITTER = MarkdownHeaderTextSplitter(
    headers_to_split_on=MARKDOWN_HEADERS,
    # 标题作为 metadata 保存；保留在正文中会让连续标题产生仅含标题的空 chunk。
    strip_headers=True,
)
RECURSIVE_TEXT_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=MAX_CHARS,
    chunk_overlap=OVERLAP_CHARS,
    length_function=len,
    separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
)


@dataclass(frozen=True, slots=True)
class DraftChunk:
    title: str | None
    act: str | None
    chunk_type: KnowledgeChunkType
    content: str
    heading_path: list[str]


def _to_chunk_response(chunk: KnowledgeChunk) -> KnowledgeChunkResponse:
    return KnowledgeChunkResponse(
        id=chunk.id,
        documentId=chunk.document_id,
        versionId=chunk.version_id,
        parsedFileId=chunk.parsed_file_id,
        fileId=chunk.file_id,
        relativePath=chunk.file.relative_path,
        chunkIndex=chunk.chunk_index,
        chunkType=chunk.chunk_type.value,
        status=chunk.status.value,
        title=chunk.title,
        act=chunk.act,
        roleName=chunk.role_name,
        content=chunk.content,
        contentSha256=chunk.content_sha256,
        charCount=chunk.char_count,
        metadata=chunk.extra_metadata,
        createdAt=chunk.created_at,
    )


def _guess_role_name(relative_path: str) -> str | None:
    stem = PurePosixPath(relative_path).stem
    for suffix in ("手册", "角色本", "剧本", "玩家本"):
        stem = stem.removesuffix(suffix)
    stem = re.sub(r"^\d+[\s._-]*", "", stem).strip()
    return stem or None


def _classify_heading(title: str, loader_type: str) -> KnowledgeChunkType:
    if loader_type == "image_asset":
        return KnowledgeChunkType.IMAGE
    if "任务" in title:
        return KnowledgeChunkType.TASK
    if "印象" in title or "人物" in title:
        return KnowledgeChunkType.CHARACTER_IMPRESSION
    if "规则" in title or "玩法" in title:
        return KnowledgeChunkType.RULE
    if re.search(r"第[一二三四五六七八九十0-9]+幕", title):
        return KnowledgeChunkType.STORY
    return KnowledgeChunkType.NOTE


def _extract_act(title: str) -> str | None:
    match = re.search(r"第[一二三四五六七八九十0-9]+幕", title)
    return match.group(0) if match else None


def _heading_path(metadata: dict[str, object]) -> list[str]:
    return [
        str(metadata[key]).strip() for _, key in MARKDOWN_HEADERS if metadata.get(key)
    ]


def build_chunks(
    markdown: str, *, relative_path: str, loader_type: str
) -> list[DraftChunk]:
    drafts: list[DraftChunk] = []
    sections = MARKDOWN_HEADER_SPLITTER.split_text(markdown)
    for section in sections:
        heading_path = _heading_path(section.metadata)
        title = heading_path[-1] if heading_path else PurePosixPath(relative_path).name
        content = section.page_content.strip()
        if not content:
            continue
        chunk_type = _classify_heading(title or "", loader_type)
        act = next(
            (
                act
                for heading in reversed(heading_path)
                if (act := _extract_act(heading))
            ),
            None,
        )
        for index, piece in enumerate(
            RECURSIVE_TEXT_SPLITTER.split_text(content), start=1
        ):
            draft_title = title if index == 1 else f"{title} {index}"
            drafts.append(
                DraftChunk(
                    title=draft_title,
                    act=act,
                    chunk_type=chunk_type,
                    content=piece,
                    heading_path=heading_path,
                )
            )

    if not drafts and markdown.strip():
        drafts.append(
            DraftChunk(
                title=PurePosixPath(relative_path).name,
                act=None,
                chunk_type=_classify_heading("", loader_type),
                content=markdown.strip(),
                heading_path=[],
            )
        )
    return drafts[:80]


async def _chunk_parsed_file(
    *,
    parsed: KnowledgeParsedFile,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession,
    storage: OssStorage,
) -> list[KnowledgeChunk]:
    if parsed.status is not KnowledgeParsedFileStatus.READY or not parsed.markdown_key:
        return []

    await db.execute(
        delete(KnowledgeChunk).where(KnowledgeChunk.parsed_file_id == parsed.id)
    )
    markdown = await storage.get_text(parsed.markdown_key)
    role_name = _guess_role_name(parsed.file.relative_path)
    rows: list[KnowledgeChunk] = []
    for index, draft in enumerate(
        build_chunks(
            markdown,
            relative_path=parsed.file.relative_path,
            loader_type=parsed.loader_type,
        )
    ):
        row = KnowledgeChunk(
            id=uuid.uuid4(),
            document_id=document_id,
            version_id=version_id,
            parsed_file_id=parsed.id,
            file_id=parsed.file_id,
            chunk_index=index,
            chunk_type=draft.chunk_type,
            status=KnowledgeChunkStatus.READY,
            title=draft.title,
            act=draft.act,
            role_name=role_name,
            content=draft.content,
            content_sha256=hashlib.sha256(draft.content.encode("utf-8")).hexdigest(),
            char_count=len(draft.content),
            extra_metadata={
                "source_path": parsed.file.relative_path,
                "heading_path": draft.heading_path,
            },
        )
        db.add(row)
        rows.append(row)
    await db.flush()
    return rows


def _summarize_chunks(
    *,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    total_files: int,
    chunks: list[KnowledgeChunk],
) -> KnowledgeChunkListResponse:
    by_file: dict[uuid.UUID, list[KnowledgeChunk]] = defaultdict(list)
    for chunk in chunks:
        by_file[chunk.file_id].append(chunk)

    file_summaries = [
        KnowledgeChunkFileSummary(
            fileId=file_id,
            parsedFileId=file_chunks[0].parsed_file_id,
            relativePath=file_chunks[0].file.relative_path,
            roleName=file_chunks[0].role_name,
            acts=sorted({chunk.act for chunk in file_chunks if chunk.act}),
            chunkCount=len(file_chunks),
            typeCounts=dict(Counter(chunk.chunk_type.value for chunk in file_chunks)),
            status="ready",
            updatedAt=max((chunk.created_at for chunk in file_chunks), default=None),
        )
        for file_id, file_chunks in by_file.items()
    ]
    return KnowledgeChunkListResponse(
        documentId=document_id,
        versionId=version_id,
        totalChunks=len(chunks),
        chunkedFiles=len(by_file),
        totalFiles=total_files,
        typeCounts=dict(Counter(chunk.chunk_type.value for chunk in chunks)),
        files=sorted(file_summaries, key=lambda item: item.relative_path),
        chunks=[
            _to_chunk_response(chunk)
            for chunk in sorted(
                chunks, key=lambda item: (item.file.relative_path, item.chunk_index)
            )
        ],
    )


async def chunk_document_action(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    store_id: uuid.UUID,
    db: AsyncSession,
    storage: OssStorage | None = None,
) -> KnowledgeChunkListResponse:
    version = await get_version_for_manifest(document_id, version_id, store_id, db)
    if version is None:
        raise KnowledgeDocumentNotFoundError("知识库版本不存在")
    oss_storage = storage or OssStorage()
    chunks: list[KnowledgeChunk] = []
    for parsed in version.parsed_files:
        chunks.extend(
            await _chunk_parsed_file(
                parsed=parsed,
                document_id=document_id,
                version_id=version_id,
                db=db,
                storage=oss_storage,
            )
        )
    return _summarize_chunks(
        document_id=document_id,
        version_id=version_id,
        total_files=len(version.files),
        chunks=chunks,
    )


async def list_chunks_action(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    store_id: uuid.UUID,
    db: AsyncSession,
) -> KnowledgeChunkListResponse:
    version = await get_version_for_manifest(document_id, version_id, store_id, db)
    if version is None:
        raise KnowledgeDocumentNotFoundError("知识库版本不存在")
    return _summarize_chunks(
        document_id=document_id,
        version_id=version_id,
        total_files=len(version.files),
        chunks=version.chunks,
    )
