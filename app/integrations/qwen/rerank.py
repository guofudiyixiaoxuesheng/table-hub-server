"""Qwen Rerank 客户端，用于 RAG 召回后的精排。

默认不会被调用；只有配置 RERANK_ENABLED=true 后，检索器才会把候选 chunk
发送给外部 rerank 服务。
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.modules.knowledge.exceptions import KnowledgeDocumentUploadError


@dataclass(frozen=True, slots=True)
class RerankResult:
    index: int
    relevance_score: float


class QwenRerankClient:
    def __init__(self) -> None:
        if not settings.QWEN_API_KEY:
            raise KnowledgeDocumentUploadError("精排需要配置 QWEN_API_KEY")
        self.api_url = self._resolve_api_url()
        self.headers = {
            "Authorization": f"Bearer {settings.QWEN_API_KEY}",
            "Content-Type": "application/json",
        }

    def _resolve_api_url(self) -> str:
        if settings.RERANK_API_URL:
            return settings.RERANK_API_URL
        base_url = settings.QWEN_BASE_URL.rstrip("/").replace(
            "/compatible-mode/v1", "/compatible-api/v1"
        )
        return f"{base_url}/reranks"

    async def rerank(
        self,
        *,
        query: str,
        documents: list[str],
        top_n: int,
    ) -> list[RerankResult]:
        if not documents:
            return []
        async with httpx.AsyncClient(timeout=settings.RERANK_TIMEOUT_SECONDS) as client:
            response = await client.post(
                self.api_url,
                headers=self.headers,
                json={
                    "model": settings.RERANK_MODEL,
                    "query": query,
                    "documents": documents,
                    "top_n": min(top_n, len(documents)),
                    "instruct": settings.RERANK_INSTRUCT,
                },
            )
        if response.status_code >= 400:
            raise KnowledgeDocumentUploadError(
                f"Rerank 请求失败：HTTP {response.status_code}"
            )
        payload = response.json()
        return [
            RerankResult(
                index=int(item.get("index", -1)),
                relevance_score=float(item.get("relevance_score", 0.0)),
            )
            for item in payload.get("results", [])
            if int(item.get("index", -1)) >= 0
        ]
