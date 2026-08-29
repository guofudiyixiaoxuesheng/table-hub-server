"""Qwen 兼容 OpenAI Embeddings API 客户端。"""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.modules.knowledge.exceptions import KnowledgeDocumentUploadError


class QwenEmbeddingClient:
    def __init__(self) -> None:
        if not settings.QWEN_API_KEY:
            raise KnowledgeDocumentUploadError("向量化需要配置 QWEN_API_KEY")
        self.base_url = settings.QWEN_BASE_URL.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {settings.QWEN_API_KEY}",
            "Content-Type": "application/json",
        }

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers=self.headers,
                json={"model": settings.EMBEDDING_MODEL, "input": texts},
            )
        if response.status_code >= 400:
            raise KnowledgeDocumentUploadError(
                f"Embedding 请求失败：HTTP {response.status_code}"
            )
        payload = response.json()
        vectors = [
            item.get("embedding", [])
            for item in sorted(payload.get("data", []), key=lambda item: item.get("index", 0))
        ]
        if len(vectors) != len(texts):
            raise KnowledgeDocumentUploadError("Embedding 返回数量与请求文本数量不一致")
        return [[float(value) for value in vector] for vector in vectors]
