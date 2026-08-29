"""将 OSS 原始文件加载为 Markdown 文本。"""

from __future__ import annotations

import csv
import html
import io
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from xml.etree import ElementTree

from app.modules.knowledge.exceptions import KnowledgeDocumentUploadError
from app.modules.knowledge.models import KnowledgeFile


@dataclass(frozen=True, slots=True)
class LoadedMarkdown:
    loader_type: str
    markdown: str


def detect_loader_type(file: KnowledgeFile) -> str:
    suffix = PurePosixPath(file.relative_path).suffix.lower()
    content_type = file.content_type.lower()
    if suffix in {
        ".jpg",
        ".jpeg",
        ".jfif",
        ".png",
        ".webp",
        ".gif",
        ".bmp",
        ".heic",
        ".heif",
    } or content_type.startswith("image/"):
        return "image_asset"
    if suffix == ".pdf" or content_type == "application/pdf":
        return "mineru_pdf"
    if suffix in {".docx", ".doc"}:
        return "docx"
    if suffix == ".csv" or "csv" in content_type:
        return "csv"
    if suffix in {".txt", ".md"} or content_type.startswith("text/"):
        return "text"
    return "unsupported"


def load_markdown(file: KnowledgeFile, payload: bytes) -> LoadedMarkdown:
    loader_type = detect_loader_type(file)
    if loader_type == "text":
        return LoadedMarkdown(loader_type=loader_type, markdown=_text_to_markdown(file, payload))
    if loader_type == "csv":
        return LoadedMarkdown(loader_type=loader_type, markdown=_csv_to_markdown(file, payload))
    if loader_type == "docx":
        return LoadedMarkdown(loader_type=loader_type, markdown=_docx_to_markdown(file, payload))
    raise KnowledgeDocumentUploadError(f"暂不支持该文件类型：{file.relative_path}")


def _decode_text(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def _text_to_markdown(file: KnowledgeFile, payload: bytes) -> str:
    text = _decode_text(payload).strip()
    title = PurePosixPath(file.relative_path).name
    return f"# {title}\n\n{text}\n"


def _csv_to_markdown(file: KnowledgeFile, payload: bytes) -> str:
    text = _decode_text(payload)
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return _text_to_markdown(file, payload)

    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    header = [cell.strip() or f"列{index + 1}" for index, cell in enumerate(normalized[0])]
    body = normalized[1:]
    lines = [
        f"# {PurePosixPath(file.relative_path).name}",
        "",
        "| " + " | ".join(_escape_table_cell(cell) for cell in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend(
        "| " + " | ".join(_escape_table_cell(cell) for cell in row) + " |"
        for row in body
    )
    return "\n".join(lines) + "\n"


def _escape_table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _docx_to_markdown(file: KnowledgeFile, payload: bytes) -> str:
    if PurePosixPath(file.relative_path).suffix.lower() == ".doc":
        raise KnowledgeDocumentUploadError("暂不支持旧版 .doc，请先转换为 .docx")

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            xml = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as error:
        raise KnowledgeDocumentUploadError(f"DOCX 文件无法读取：{file.relative_path}") from error

    root = ElementTree.fromstring(xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for paragraph in root.findall(".//w:p", namespace):
        chunks = [
            text.text or ""
            for text in paragraph.findall(".//w:t", namespace)
            if text.text
        ]
        content = "".join(chunks).strip()
        if content:
            paragraphs.append(html.unescape(content))

    title = PurePosixPath(file.relative_path).name
    return f"# {title}\n\n" + "\n\n".join(paragraphs) + "\n"
