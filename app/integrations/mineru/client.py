"""MinerU API 客户端。"""

import asyncio
import io
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

import httpx

from app.core.config import settings
from app.modules.knowledge.exceptions import KnowledgeDocumentUploadError


@dataclass(frozen=True, slots=True)
class MineruAsset:
    original_ref: str
    filename: str
    content_type: str
    payload: bytes


@dataclass(frozen=True, slots=True)
class MineruResult:
    markdown: str
    assets: list[MineruAsset]


class MineruClient:
    """提交 PDF 解析任务并读取 MinerU 产出的 Markdown。"""

    def __init__(self) -> None:
        if not settings.MINERU_TOKEN:
            raise KnowledgeDocumentUploadError("PDF 需要配置 MINERU_TOKEN 后才能加载")
        self.base_url = settings.MINERU_BASE_URL.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {settings.MINERU_TOKEN}",
            "Content-Type": "application/json",
        }

    async def parse_pdf_url(self, file_url: str, file_name: str) -> MineruResult:
        async with httpx.AsyncClient(timeout=60) as client:
            task_id = await self._create_task(client, file_url, file_name)
            zip_url = await self._wait_for_zip_url(client, task_id)
            return await self._download_result(client, zip_url)

    async def _create_task(
        self, client: httpx.AsyncClient, file_url: str, file_name: str
    ) -> str:
        response = await client.post(
            f"{self.base_url}/api/v4/extract/task",
            headers=self.headers,
            json={
                "url": file_url,
                "is_ocr": True,
                "enable_formula": True,
                "enable_table": True,
                "language": "ch",
                "data_id": file_name,
                "model_version": settings.MINERU_MODEL_VERSION,
            },
        )
        payload = self._read_response(response)
        task_id = str(payload.get("data", {}).get("task_id") or "")
        if not task_id:
            raise KnowledgeDocumentUploadError(f"MinerU 未返回任务 ID：{file_name}")
        return task_id

    async def _wait_for_zip_url(self, client: httpx.AsyncClient, task_id: str) -> str:
        deadline = asyncio.get_running_loop().time() + settings.MINERU_POLL_TIMEOUT_SECONDS
        while asyncio.get_running_loop().time() < deadline:
            response = await client.get(
                f"{self.base_url}/api/v4/extract/task/{task_id}",
                headers=self.headers,
            )
            payload = self._read_response(response)
            data = payload.get("data", {})
            state = str(data.get("state") or "")
            if state == "done":
                zip_url = str(data.get("full_zip_url") or "")
                if zip_url:
                    return zip_url
                raise KnowledgeDocumentUploadError("MinerU 任务完成但未返回 full_zip_url")
            if state == "failed":
                raise KnowledgeDocumentUploadError(
                    str(data.get("err_msg") or "MinerU PDF 解析失败")
                )
            await asyncio.sleep(settings.MINERU_POLL_INTERVAL_SECONDS)
        raise KnowledgeDocumentUploadError("MinerU PDF 解析超时")

    async def _download_result(
        self, client: httpx.AsyncClient, zip_url: str
    ) -> MineruResult:
        response = await client.get(zip_url)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            markdown_name = next(
                (name for name in archive.namelist() if name.endswith("full.md")),
                None,
            )
            if not markdown_name:
                raise KnowledgeDocumentUploadError("MinerU 结果包中没有 full.md")
            assets = [
                MineruAsset(
                    original_ref=name,
                    filename=PurePosixPath(name).name,
                    content_type=_guess_image_content_type(name),
                    payload=archive.read(name),
                )
                for name in archive.namelist()
                if _is_image_name(name)
            ]
            return MineruResult(
                markdown=archive.read(markdown_name).decode("utf-8"),
                assets=assets,
            )

    @staticmethod
    def _read_response(response: httpx.Response) -> dict:
        if response.status_code >= 400:
            raise KnowledgeDocumentUploadError(
                f"MinerU 请求失败：HTTP {response.status_code}"
            )
        payload = response.json()
        code = payload.get("code")
        if code not in (0, "0", None):
            raise KnowledgeDocumentUploadError(
                str(payload.get("msg") or payload.get("message") or "MinerU 请求失败")
            )
        return payload


def _is_image_name(name: str) -> bool:
    return PurePosixPath(name).suffix.lower() in {
        ".jpg",
        ".jpeg",
        ".jfif",
        ".png",
        ".webp",
        ".gif",
        ".bmp",
        ".heic",
        ".heif",
    }


def _guess_image_content_type(name: str) -> str:
    suffix = PurePosixPath(name).suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".jfif": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".heic": "image/heic",
        ".heif": "image/heif",
    }.get(suffix, "application/octet-stream")
