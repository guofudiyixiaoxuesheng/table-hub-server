"""AI 对话 trace 上下文。

第一版目标：
1. 记录每次 AI 对话的 LangGraph 调用链路。
2. 支持在 Langfuse 里查看节点耗时、LLM token、报错。
3. 统一挂载 user/store/thread 信息，便于线上排查。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from typing import Any

from app.observability.langfuse import langfuse_enabled


@contextmanager
def trace_chat(
    *,
    trace_name: str,
    user_id: str | None,
    session_id: str | None,
    store_id: str | None,
    guest_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Iterator[None]:
    """为一次 AI 对话创建 Langfuse trace 属性上下文。"""

    if not langfuse_enabled():
        with nullcontext():
            yield
        return

    from langfuse import propagate_attributes

    tags = ["tablehub", "ai-chat", "langgraph"]
    if user_id:
        tags.append("user")
    if guest_id:
        tags.append("guest")

    with propagate_attributes(
        trace_name=trace_name,
        user_id=user_id or guest_id,
        session_id=session_id,
        tags=tags,
        metadata={
            "store_id": store_id,
            "guest_id": guest_id,
            **(metadata or {}),
        },
    ):
        yield
