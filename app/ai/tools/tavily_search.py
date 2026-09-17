"""Tavily 外部事实检索工具。

仅用于天气、公共活动、交通等会随时间变化的外部信息。门店资料、场次、
价格、余位和用户信息必须继续走本系统的 service，不允许用网页搜索替代。
"""

from __future__ import annotations

from datetime import date
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from app.ai.tools.runtime_context import current_datetime
from app.core.config import settings


class TavilySearchUnavailableError(RuntimeError):
    """未配置 Tavily 时抛出，调用方可优雅降级而非阻塞核心业务。"""


class TavilySearchError(RuntimeError):
    """Tavily 请求或返回异常。"""


class TavilySearchItem(BaseModel):
    title: str = ""
    url: str = ""
    content: str = ""
    score: float | None = None


class TavilySearchResponse(BaseModel):
    query: str
    answer: str | None = None
    results: list[TavilySearchItem] = Field(default_factory=list)


async def search_tavily(
    query: str,
    *,
    max_results: int | None = None,
    topic: Literal["general", "news"] = "general",
) -> TavilySearchResponse:
    """检索公开网页并返回有限、可引用的结果。

    请求规模受配置限制，避免 AI 一次对话触发大范围搜索或把原始页面内容
    无限制灌入上下文。
    """

    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("搜索关键词不能为空")
    if not settings.TAVILY_API_KEY:
        raise TavilySearchUnavailableError("未配置 TAVILY_API_KEY")

    limit = min(max(max_results or settings.TAVILY_MAX_RESULTS, 1), settings.TAVILY_MAX_RESULTS)
    payload = {
        "query": normalized_query,
        "topic": topic,
        "search_depth": "basic",
        "max_results": limit,
        "include_answer": True,
        "include_raw_content": False,
    }
    endpoint = f"{settings.TAVILY_BASE_URL.rstrip('/')}/search"
    try:
        async with httpx.AsyncClient(timeout=settings.TAVILY_TIMEOUT_SECONDS) as client:
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {settings.TAVILY_API_KEY}"},
                json=payload,
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise TavilySearchError("Tavily 检索失败") from exc

    data = response.json()
    return TavilySearchResponse(
        query=normalized_query,
        answer=str(data.get("answer") or "") or None,
        results=[
            TavilySearchItem.model_validate(item)
            for item in data.get("results", [])[:limit]
            if isinstance(item, dict)
        ],
    )


async def search_weather(
    location: str,
    *,
    target_date: date | None = None,
) -> TavilySearchResponse:
    """用 Tavily 查询某地点当日或指定日期的天气公开信息。"""

    normalized_location = location.strip()
    if not normalized_location:
        raise ValueError("查询天气需要城市或具体地点")
    day_label = (target_date or current_datetime().date()).isoformat()
    return await search_tavily(f"{normalized_location} {day_label} 天气预报", max_results=3)
