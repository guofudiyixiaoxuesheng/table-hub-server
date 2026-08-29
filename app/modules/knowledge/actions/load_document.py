"""加载知识库版本中的原始文件为 Markdown。"""

import hashlib
import re
import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.mineru.client import MineruAsset, MineruClient
from app.integrations.storage.oss import OssStorage
from app.modules.knowledge.exceptions import KnowledgeDocumentNotFoundError
from app.modules.knowledge.loaders import (
    LoadedMarkdown,
    detect_loader_type,
    load_markdown,
)
from app.modules.knowledge.models import (
    KnowledgeFile,
    KnowledgeParsedAsset,
    KnowledgeParsedAssetType,
    KnowledgeParsedFile,
    KnowledgeParsedFileStatus,
)
from app.modules.knowledge.repository import get_parsed_asset, get_version_for_manifest
from app.modules.knowledge.schemas import (
    AssetPreviewUrlResponse,
    LoadKnowledgeDocumentResponse,
    ParsedKnowledgeFileResponse,
    ParsedMarkdownResponse,
)


def _parsed_prefix(store_id: uuid.UUID, document_id: uuid.UUID, version_id: uuid.UUID) -> str:
    return f"stores/{store_id}/knowledge/{document_id}/versions/{version_id}/parsed"


def _to_response(parsed: KnowledgeParsedFile) -> ParsedKnowledgeFileResponse:
    assets = parsed.__dict__.get("assets", [])
    return ParsedKnowledgeFileResponse(
        id=parsed.id,
        fileId=parsed.file_id,
        relativePath=parsed.file.relative_path,
        loaderType=parsed.loader_type,
        status=parsed.status.value,
        markdownKey=parsed.markdown_key,
        textSha256=parsed.text_sha256,
        charCount=parsed.char_count,
        assetCount=len(assets),
        errorMessage=parsed.error_message,
        completedAt=parsed.completed_at,
    )


def _asset_prefix(store_id: uuid.UUID, document_id: uuid.UUID, version_id: uuid.UUID) -> str:
    return f"stores/{store_id}/knowledge/{document_id}/versions/{version_id}/assets"


def _image_markdown(file_name: str, asset_id: uuid.UUID) -> str:
    return (
        f"# {file_name}\n\n"
        f"![{file_name}](asset://{asset_id})\n\n"
        "## OCR 文本\n\n待识别\n\n"
        "## 图片描述\n\n待识别\n"
    )


def _replace_asset_refs(markdown: str, refs: dict[str, uuid.UUID]) -> str:
    def replace(match: re.Match[str]) -> str:
        alt, target = match.group(1), match.group(2)
        asset_id = refs.get(target) or refs.get(PurePosixPath(target).name)
        if asset_id is None:
            return match.group(0)
        return f"![{alt}](asset://{asset_id})"

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace, markdown)


async def _create_pdf_assets(
    *,
    assets: list[MineruAsset],
    parsed: KnowledgeParsedFile,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    storage: OssStorage,
    db: AsyncSession,
) -> dict[str, uuid.UUID]:
    refs: dict[str, uuid.UUID] = {}
    prefix = _asset_prefix(store_id, document_id, version_id)
    parsed.assets.clear()
    await db.flush()
    for asset in assets:
        asset_id = uuid.uuid4()
        suffix = PurePosixPath(asset.filename).suffix.lower() or ".png"
        asset_key = f"{prefix}/{parsed.id}/images/{asset_id}{suffix}"
        await storage.put_bytes(asset_key, asset.payload, asset.content_type)
        row = KnowledgeParsedAsset(
            id=asset_id,
            version_id=version_id,
            parsed_file_id=parsed.id,
            source_file_id=parsed.file_id,
            asset_type=KnowledgeParsedAssetType.IMAGE,
            asset_key=asset_key,
            original_ref=asset.original_ref,
            extra_metadata={"filename": asset.filename},
        )
        db.add(row)
        parsed.assets.append(row)
        refs[asset.original_ref] = asset_id
        refs[asset.filename] = asset_id
    return refs


def _create_standalone_image_asset(
    parsed: KnowledgeParsedFile,
) -> KnowledgeParsedAsset:
    return KnowledgeParsedAsset(
        id=uuid.uuid4(),
        version_id=parsed.version_id,
        parsed_file_id=parsed.id,
        source_file_id=parsed.file_id,
        asset_type=KnowledgeParsedAssetType.IMAGE,
        asset_key=parsed.file.object_key,
        original_ref=parsed.file.relative_path,
        extra_metadata={"filename": PurePosixPath(parsed.file.relative_path).name},
    )


async def _load_one_file(
    *,
    file: KnowledgeFile,
    parsed: KnowledgeParsedFile | None,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    prefix: str,
    db: AsyncSession,
    storage: OssStorage,
) -> KnowledgeParsedFile:
    parsed = parsed or KnowledgeParsedFile(
        id=uuid.uuid4(),
        version_id=version_id,
        file_id=file.id,
        loader_type=detect_loader_type(file),
    )
    parsed.file = file
    if "assets" not in parsed.__dict__:
        parsed.assets = []
    parsed.loader_type = detect_loader_type(file)
    parsed.status = KnowledgeParsedFileStatus.PROCESSING
    parsed.error_message = None
    parsed.markdown_key = None
    parsed.text_sha256 = None
    parsed.char_count = 0
    db.add(parsed)
    await db.flush()

    try:
        if parsed.assets:
            parsed.assets.clear()
        await db.flush()
        if parsed.loader_type == "mineru_pdf":
            source_url = storage.presign_get(file.object_key)
            mineru_result = await MineruClient().parse_pdf_url(
                source_url, file.relative_path
            )
            refs = await _create_pdf_assets(
                assets=mineru_result.assets,
                parsed=parsed,
                store_id=store_id,
                document_id=document_id,
                version_id=version_id,
                storage=storage,
                db=db,
            )
            loaded = LoadedMarkdown(
                loader_type="mineru_pdf",
                markdown=_replace_asset_refs(mineru_result.markdown, refs),
            )
        elif parsed.loader_type == "image_asset":
            asset = _create_standalone_image_asset(parsed)
            db.add(asset)
            parsed.assets.append(asset)
            loaded = LoadedMarkdown(
                loader_type="image_asset",
                markdown=_image_markdown(PurePosixPath(file.relative_path).name, asset.id),
            )
        else:
            source = await storage.get_bytes(file.object_key)
            loaded = load_markdown(file, source)
        markdown_key = f"{prefix}/{file.id}/content.md"
        await storage.put_text(markdown_key, loaded.markdown)
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
    return parsed


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

        parsed = await _load_one_file(
            file=file,
            parsed=parsed,
            store_id=store_id,
            document_id=document_id,
            version_id=version.id,
            prefix=prefix,
            db=db,
            storage=oss_storage,
        )
        parsed_files.append(parsed)

    await db.flush()
    return LoadKnowledgeDocumentResponse(
        documentId=document_id,
        versionId=version_id,
        files=[_to_response(parsed) for parsed in parsed_files],
    )


async def load_single_file_action(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    file_id: uuid.UUID,
    store_id: uuid.UUID,
    db: AsyncSession,
    storage: OssStorage | None = None,
) -> ParsedKnowledgeFileResponse:
    version = await get_version_for_manifest(document_id, version_id, store_id, db)
    if version is None:
        raise KnowledgeDocumentNotFoundError("知识库版本不存在")

    file = next((item for item in version.files if item.id == file_id), None)
    if file is None:
        raise KnowledgeDocumentNotFoundError("知识库文件不存在")

    existing = {parsed.file_id: parsed for parsed in version.parsed_files}
    parsed = await _load_one_file(
        file=file,
        parsed=existing.get(file.id),
        store_id=store_id,
        document_id=document_id,
        version_id=version.id,
        prefix=_parsed_prefix(store_id, document_id, version_id),
        db=db,
        storage=storage or OssStorage(),
    )
    await db.flush()
    return _to_response(parsed)


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


async def get_asset_preview_url_action(
    asset_id: uuid.UUID,
    store_id: uuid.UUID,
    db: AsyncSession,
    storage: OssStorage | None = None,
) -> AssetPreviewUrlResponse:
    asset = await get_parsed_asset(asset_id, store_id, db)
    if asset is None:
        raise KnowledgeDocumentNotFoundError("图片资产不存在")
    return AssetPreviewUrlResponse(
        assetId=asset.id,
        previewUrl=(storage or OssStorage()).presign_get(asset.asset_key),
    )
