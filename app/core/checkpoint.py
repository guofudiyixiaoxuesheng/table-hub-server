"""LangGraph checkpoint 生命周期管理。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import settings


@asynccontextmanager
async def checkpoint_lifespan() -> AsyncIterator[AsyncPostgresSaver]:
    """应用启动时创建一次 checkpointer，关闭时统一释放。"""

    async with AsyncPostgresSaver.from_conn_string(
        settings.CHECKPOINT_DATABASE_URL
    ) as checkpointer:
        await checkpointer.setup()
        yield checkpointer
