from __future__ import annotations

from pydantic import BaseModel


class ImageGenerationRequest(BaseModel):
    """统一图片生成请求。"""

    prompt: str
    negative_prompt: str | None = None
    aspect_ratio: str = "1:1"


class ImageGenerationResult(BaseModel):
    """统一图片生成结果。"""

    image_url: str | None = None
    image_bytes: bytes | None = None
    provider: str
    raw_response: dict[str, object] | None = None
