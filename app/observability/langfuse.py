"""Langfuse 接入封装。

当前只在 AI 对话入口创建 LangGraph/LangChain callback。
后续如果要换成 Phoenix/OpenTelemetry，业务代码不需要大面积改动。
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

from app.core.config import settings


def langfuse_enabled() -> bool:
    """判断当前环境是否启用 Langfuse。"""

    return bool(
        settings.LANGFUSE_ENABLED
        and settings.LANGFUSE_PUBLIC_KEY
        and settings.LANGFUSE_SECRET_KEY
    )


def _sync_langfuse_env() -> None:
    """把项目配置同步成 Langfuse SDK 默认读取的环境变量。"""

    if settings.LANGFUSE_PUBLIC_KEY:
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.LANGFUSE_PUBLIC_KEY)
    if settings.LANGFUSE_SECRET_KEY:
        os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.LANGFUSE_SECRET_KEY)
    base_url = settings.LANGFUSE_BASE_URL or settings.LANGFUSE_HOST
    if base_url:
        # Langfuse v4 推荐 LANGFUSE_BASE_URL；兼容老写法 LANGFUSE_HOST。
        os.environ.setdefault("LANGFUSE_BASE_URL", base_url)
        os.environ.setdefault("LANGFUSE_HOST", base_url)


def langfuse_callbacks() -> list[Any]:
    """创建本次请求使用的 Langfuse callback。"""

    if not langfuse_enabled():
        return []
    _sync_langfuse_env()
    try:
        from langfuse.langchain import CallbackHandler
    except ImportError:
        return []
    return [CallbackHandler()]


def merge_callbacks(*groups: Sequence[Any] | None) -> list[Any]:
    """合并 callback 列表，过滤空值。"""

    callbacks: list[Any] = []
    for group in groups:
        if group:
            callbacks.extend(group)
    return callbacks
