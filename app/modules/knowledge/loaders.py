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
    if PurePosixPath(file.relative_path).name in {".DS_Store", "Thumbs.db", "desktop.ini"}:
        return "ignored_system_file"
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
    if suffix == ".doc":
        return "legacy_doc"
    if suffix == ".docx":
        return "docx"
    if suffix in {".xlsx", ".xlsm"} or "spreadsheetml" in content_type:
        return "xlsx"
    if suffix == ".xls" or content_type == "application/vnd.ms-excel":
        return "xls"
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
    if loader_type == "legacy_doc":
        raise KnowledgeDocumentUploadError("旧版 Word（.doc）已跳过。请复制正文保存为 .txt/.md，或另存为 .docx/PDF 后通过“上传新版本”重新上传")
    if loader_type == "xlsx":
        return LoadedMarkdown(loader_type=loader_type, markdown=_xlsx_to_markdown(file, payload))
    if loader_type == "xls":
        raise KnowledgeDocumentUploadError("暂不支持旧版 .xls，请先转换为 .xlsx")
    if loader_type == "ignored_system_file":
        raise KnowledgeDocumentUploadError("系统隐藏文件已忽略，请重新上传过滤后的文件夹")
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
        raise KnowledgeDocumentUploadError("旧版 Word（.doc）已跳过。请复制正文保存为 .txt/.md，或另存为 .docx/PDF 后通过“上传新版本”重新上传")
    if not payload.startswith(b"PK"):
        raise KnowledgeDocumentUploadError(
            "这个 .docx 文件内容不是标准 DOCX，可能是直接从 .doc 改后缀得到的。"
            "请用 Word/WPS/LibreOffice 另存为 .docx/PDF，或复制正文保存为 .txt/.md 后通过“上传新版本”重新上传"
        )

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            xml = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as error:
        raise KnowledgeDocumentUploadError(
            f"DOCX 文件无法读取：{file.relative_path}。"
            "请确认它是通过 Word/WPS/LibreOffice 另存为得到的标准 .docx 文件"
        ) from error

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

def _xlsx_to_markdown(file: KnowledgeFile, payload: bytes) -> str:
    """读取 XLSX 为 Markdown。

    XLSX 本质是 zip + XML，这里只做轻量解析，足够用于 RAG 检索表格文本。
    复杂样式、公式计算、合并单元格暂不处理。
    """

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            shared_strings = _read_xlsx_shared_strings(archive)
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            sheet_targets = _read_xlsx_sheet_targets(workbook, relationships)
            sections = [
                _read_xlsx_sheet(archive, name, target, shared_strings)
                for name, target in sheet_targets
            ]
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as error:
        raise KnowledgeDocumentUploadError(f"XLSX 文件无法读取：{file.relative_path}") from error

    title = PurePosixPath(file.relative_path).name
    content = "\n\n".join(section for section in sections if section.strip()).strip()
    return f"# {title}\n\n{content or '空表格'}\n"


def _read_xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    values: list[str] = []
    for item in root.findall(".//s:si", namespace):
        texts = [node.text or "" for node in item.findall(".//s:t", namespace)]
        values.append("".join(texts))
    return values


def _read_xlsx_sheet_targets(
    workbook: ElementTree.Element,
    relationships: ElementTree.Element,
) -> list[tuple[str, str]]:
    workbook_namespace = {
        "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }
    rel_namespace = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
    rels = {
        item.attrib.get("Id"): item.attrib.get("Target", "")
        for item in relationships.findall(".//r:Relationship", rel_namespace)
    }
    sheets: list[tuple[str, str]] = []
    for sheet in workbook.findall(".//s:sheet", workbook_namespace):
        name = sheet.attrib.get("name", "Sheet")
        rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = rels.get(rel_id)
        if target:
            sheets.append((name, target if target.startswith("worksheets/") else f"worksheets/{target.split('/')[-1]}"))
    return sheets


def _xlsx_cell_value(
    cell: ElementTree.Element,
    shared_strings: list[str],
    namespace: dict[str, str],
) -> str:
    cell_type = cell.attrib.get("t")
    value_node = cell.find("s:v", namespace)
    if value_node is None or value_node.text is None:
        inline_node = cell.find(".//s:t", namespace)
        return inline_node.text if inline_node is not None and inline_node.text else ""
    raw_value = value_node.text
    if cell_type == "s":
        try:
            return shared_strings[int(raw_value)]
        except (ValueError, IndexError):
            return raw_value
    return raw_value


def _read_xlsx_sheet(
    archive: zipfile.ZipFile,
    name: str,
    target: str,
    shared_strings: list[str],
) -> str:
    namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ElementTree.fromstring(archive.read(f"xl/{target}"))
    rows: list[list[str]] = []
    for row in root.findall(".//s:sheetData/s:row", namespace):
        values = [_xlsx_cell_value(cell, shared_strings, namespace).strip() for cell in row.findall("s:c", namespace)]
        if any(values):
            rows.append(values)
    if not rows:
        return f"## {name}\n\n空表格"
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    header = [cell or f"列{index + 1}" for index, cell in enumerate(normalized[0])]
    body = normalized[1:]
    lines = [
        f"## {name}",
        "",
        "| " + " | ".join(_escape_table_cell(cell) for cell in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend(
        "| " + " | ".join(_escape_table_cell(cell) for cell in row) + " |"
        for row in body
    )
    return "\n".join(lines)
