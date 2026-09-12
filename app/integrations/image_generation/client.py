from __future__ import annotations

from app.core.config import settings
from app.integrations.image_generation.schemas import (
    ImageGenerationRequest,
    ImageGenerationResult,
)
from app.integrations.qwen.image_generation import QwenImageClient

QWEN_SIZE_BY_ASPECT_RATIO = {
    "1:1": "1024*1024",
    "3:4": "768*1024",
    "4:3": "1024*768",
    "9:16": "720*1280",
    "16:9": "1280*720",
}


def _build_provider_prompt(request: ImageGenerationRequest) -> str:
    """把统一请求转换成阿里图片模型更容易理解的 prompt。"""

    if not request.negative_prompt:
        return request.prompt
    return (
        f"{request.prompt}\n\n"
        f"负向要求：{request.negative_prompt}"
    )


async def generate_image(request: ImageGenerationRequest) -> ImageGenerationResult:
    """统一图片生成入口。

    业务层只依赖这个函数；后续如果切换豆包、OpenAI、即梦，
    只需要在这里扩展 provider 分发逻辑。
    """

    provider = settings.IMAGE_GENERATION_PROVIDER.strip().lower()
    if provider == "disabled":
        raise NotImplementedError("图片生成服务已关闭")
    if provider != "qwen":
        raise NotImplementedError(
            "IMAGE_GENERATION_PROVIDER 仅支持 qwen / disabled，请检查 .env 配置"
        )

    image_bytes = await QwenImageClient().generate_one(
        _build_provider_prompt(request),
        size=QWEN_SIZE_BY_ASPECT_RATIO.get(request.aspect_ratio),
    )
    return ImageGenerationResult(
        image_bytes=image_bytes,
        provider="qwen_dashscope",
    )
