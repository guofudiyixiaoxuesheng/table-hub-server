"""DashScope / 通义万相文生图客户端。

生成平台返回的图片 URL 通常是短期有效地址，因此业务层会把图片下载后再转存到自己的 OSS。
"""

from __future__ import annotations

import asyncio
import time

import httpx

from app.core.config import settings
from app.core.exceptions import ApplicationError


class QwenImageGenerationError(ApplicationError):
    status_code = 422
    code = "qwen_image_generation_failed"


class QwenImageClient:
    """封装文生图提交、轮询和结果图片下载。"""

    def __init__(self) -> None:
        if not settings.QWEN_API_KEY:
            raise QwenImageGenerationError("图片生成需要配置 QWEN_API_KEY")
        self.headers = {
            "Authorization": f"Bearer {settings.QWEN_API_KEY}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }

    async def generate_one(self, prompt: str, *, size: str | None = None) -> bytes:
        """根据提示词生成一张图片，并返回图片二进制。"""

        image_size = size or settings.QWEN_IMAGE_SIZE
        if settings.QWEN_IMAGE_MODEL.lower().startswith("qwen-image-"):
            image_url = await self._generate_qwen_image_url(prompt, size=image_size)
        else:
            task_id = await self._submit_task(prompt, size=image_size)
            image_url = await self._poll_task(task_id)
        return await self._download_image(image_url)

    async def _generate_qwen_image_url(self, prompt: str, *, size: str) -> str:
        """Qwen Image 系列仅支持同步多模态生成，不可使用万相异步任务接口。"""

        payload = {
            "model": settings.QWEN_IMAGE_MODEL,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": prompt}],
                    }
                ]
            },
            "parameters": {"size": size, "n": 1},
        }
        headers = {
            "Authorization": f"Bearer {settings.QWEN_API_KEY}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                settings.QWEN_IMAGE_MULTIMODAL_API_URL,
                headers=headers,
                json=payload,
            )
        if response.status_code >= 400:
            raise QwenImageGenerationError(
                f"图片生成任务提交失败：HTTP {response.status_code} {response.text[:300]}"
            )

        output = response.json().get("output") or {}
        choices = output.get("choices") or []
        message = (choices[0] or {}).get("message") if choices else {}
        content = message.get("content") if isinstance(message, dict) else []
        for item in content or []:
            if not isinstance(item, dict):
                continue
            image_url = item.get("image") or item.get("image_url") or item.get("url")
            if image_url:
                return str(image_url)
        for item in output.get("results") or []:
            if not isinstance(item, dict):
                continue
            image_url = item.get("url") or item.get("image") or item.get("image_url")
            if image_url:
                return str(image_url)
        raise QwenImageGenerationError("图片生成成功但未返回图片地址")

    async def _submit_task(self, prompt: str, *, size: str) -> str:
        uses_qwen_image_api = settings.QWEN_IMAGE_MODEL.lower().startswith(
            "qwen-image-"
        )
        input_payload: dict[str, object]
        if uses_qwen_image_api:
            input_payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": prompt}],
                    }
                ]
            }
        else:
            input_payload = {"prompt": prompt}
        payload = {
            "model": settings.QWEN_IMAGE_MODEL,
            "input": input_payload,
            "parameters": {"size": size, "n": 1},
        }
        api_url = (
            settings.QWEN_IMAGE_MULTIMODAL_API_URL
            if uses_qwen_image_api
            else settings.QWEN_IMAGE_API_URL
        )
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(api_url, headers=self.headers, json=payload)
        if response.status_code >= 400:
            raise QwenImageGenerationError(
                f"图片生成任务提交失败：HTTP {response.status_code} {response.text[:200]}"
            )
        task_id = (response.json().get("output") or {}).get("task_id")
        if not task_id:
            raise QwenImageGenerationError("图片生成任务提交失败：未返回 task_id")
        return str(task_id)

    async def _poll_task(self, task_id: str) -> str:
        deadline = time.monotonic() + settings.QWEN_IMAGE_POLL_TIMEOUT_SECONDS
        task_url = f"{settings.QWEN_IMAGE_TASK_URL.rstrip('/')}/{task_id}"
        headers = {"Authorization": f"Bearer {settings.QWEN_API_KEY}"}
        async with httpx.AsyncClient(timeout=30) as client:
            while time.monotonic() < deadline:
                response = await client.get(task_url, headers=headers)
                if response.status_code >= 400:
                    raise QwenImageGenerationError(
                        f"图片生成任务查询失败：HTTP {response.status_code}"
                    )
                payload = response.json()
                output = payload.get("output") or {}
                status = str(output.get("task_status") or "").upper()
                if status == "SUCCEEDED":
                    results = output.get("results") or []
                    image_url = (results[0] or {}).get("url") if results else None
                    if not image_url:
                        raise QwenImageGenerationError("图片生成成功但未返回图片地址")
                    return str(image_url)
                if status in {"FAILED", "CANCELED", "UNKNOWN"}:
                    message = (
                        output.get("message")
                        or output.get("task_metrics")
                        or "未知错误"
                    )
                    raise QwenImageGenerationError(f"图片生成失败：{message}")
                await asyncio.sleep(settings.QWEN_IMAGE_POLL_INTERVAL_SECONDS)
        raise QwenImageGenerationError("图片生成超时，请稍后重试")

    async def _download_image(self, image_url: str) -> bytes:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            response = await client.get(image_url)
        if response.status_code >= 400:
            raise QwenImageGenerationError(
                f"生成图片下载失败：HTTP {response.status_code}"
            )
        return response.content
