"""聊天会话和消息仓储。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.chat.models import (
    ChatMessage,
    ChatMessageRole,
    ChatMessageType,
    ChatSession,
    ChatSessionStatus,
)


def build_session_title(message: str) -> str:
    title = " ".join(message.strip().split())
    return title[:28] or "新对话"


async def get_visible_session(
    *,
    thread_id: str,
    user_id: uuid.UUID | None,
    store_id: uuid.UUID | None,
    guest_id: str | None,
    db: AsyncSession,
) -> ChatSession | None:
    filters = [
        ChatSession.thread_id == thread_id,
        ChatSession.status == ChatSessionStatus.ACTIVE,
    ]
    if user_id:
        filters.append(ChatSession.user_id == user_id)
    else:
        filters.append(ChatSession.user_id.is_(None))
        filters.append(ChatSession.guest_id == guest_id)
        filters.append(ChatSession.store_id == store_id)
    return await db.scalar(select(ChatSession).where(*filters))


async def list_sessions(
    *,
    user_id: uuid.UUID | None,
    store_id: uuid.UUID | None,
    guest_id: str | None,
    db: AsyncSession,
) -> list[ChatSession]:
    filters = [ChatSession.status == ChatSessionStatus.ACTIVE]
    if user_id:
        filters.append(ChatSession.user_id == user_id)
    else:
        filters.append(ChatSession.user_id.is_(None))
        filters.append(ChatSession.guest_id == guest_id)
        filters.append(ChatSession.store_id == store_id)
    rows = await db.scalars(
        select(ChatSession)
        .where(*filters)
        .order_by(ChatSession.updated_at.desc())
        .limit(50)
    )
    return list(rows)


async def get_session_with_messages(
    *,
    thread_id: str,
    user_id: uuid.UUID | None,
    store_id: uuid.UUID | None,
    guest_id: str | None,
    db: AsyncSession,
) -> ChatSession | None:
    filters = [
        ChatSession.thread_id == thread_id,
        ChatSession.status == ChatSessionStatus.ACTIVE,
    ]
    if user_id:
        filters.append(ChatSession.user_id == user_id)
    else:
        filters.append(ChatSession.user_id.is_(None))
        filters.append(ChatSession.guest_id == guest_id)
        filters.append(ChatSession.store_id == store_id)
    return await db.scalar(
        select(ChatSession).options(selectinload(ChatSession.messages)).where(*filters)
    )


async def ensure_visible_session(
    *,
    thread_id: str,
    user_id: uuid.UUID | None,
    store_id: uuid.UUID | None,
    guest_id: str | None,
    first_message: str,
    db: AsyncSession,
) -> ChatSession:
    session = await get_visible_session(
        thread_id=thread_id, user_id=user_id, store_id=store_id, guest_id=guest_id, db=db
    )
    if session is not None:
        return session

    session = ChatSession(
        thread_id=thread_id,
        user_id=user_id,
        store_id=store_id,
        guest_id=None if user_id else guest_id,
        title=build_session_title(first_message),
    )
    db.add(session)
    await db.flush()
    return session


async def list_recent_messages(
    *,
    session_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 20,
) -> list[ChatMessage]:
    rows = await db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    return list(reversed(list(rows)))


async def upsert_session_message_pair(
    *,
    thread_id: str,
    user_id: uuid.UUID | None,
    store_id: uuid.UUID | None,
    guest_id: str | None,
    user_message: str,
    assistant_message: str,
    scene: str,
    db: AsyncSession,
) -> ChatSession:
    session = await ensure_visible_session(
        thread_id=thread_id,
        user_id=user_id,
        store_id=store_id,
        guest_id=guest_id,
        first_message=user_message,
        db=db,
    )
    session.scene = scene
    session.updated_at = datetime.now(UTC)

    db.add_all(
        [
            ChatMessage(
                session_id=session.id,
                role=ChatMessageRole.USER,
                message_type=ChatMessageType.TEXT,
                content=user_message,
            ),
            ChatMessage(
                session_id=session.id,
                role=ChatMessageRole.ASSISTANT,
                message_type=ChatMessageType.TEXT,
                content=assistant_message,
                message_metadata={"scene": scene},
            ),
        ]
    )
    await db.flush()
    return session


async def soft_delete_session(
    *,
    thread_id: str,
    user_id: uuid.UUID | None,
    store_id: uuid.UUID | None,
    guest_id: str | None,
    db: AsyncSession,
) -> bool:
    session = await get_visible_session(
        thread_id=thread_id, user_id=user_id, store_id=store_id, guest_id=guest_id, db=db
    )
    if session is None:
        return False
    session.status = ChatSessionStatus.DELETED
    session.deleted_at = datetime.now(UTC)
    await db.flush()
    return True
