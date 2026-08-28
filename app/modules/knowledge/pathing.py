"""OSS 对象键和用户相对路径安全规则。"""

import unicodedata
import uuid
from pathlib import PurePosixPath

from app.modules.knowledge.exceptions import KnowledgeDocumentUploadError


def normalize_relative_path(raw_path: str) -> str:
    value = unicodedata.normalize("NFC", raw_path.strip()).replace("\\", "/")
    path = PurePosixPath(value)
    parts = path.parts
    if (
        not parts
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise KnowledgeDocumentUploadError(f"非法文件路径：{raw_path}")
    if any(any(ord(char) < 32 for char in part) for part in parts):
        raise KnowledgeDocumentUploadError(f"文件路径包含控制字符：{raw_path}")
    normalized = "/".join(parts)
    if len(normalized.encode("utf-8")) > 700:
        raise KnowledgeDocumentUploadError(f"文件路径过长：{raw_path}")
    return normalized


def build_version_prefix(
    store_id: uuid.UUID, document_id: uuid.UUID, version_id: uuid.UUID
) -> str:
    return f"stores/{store_id}/knowledge/{document_id}/versions/{version_id}"
