"""编排会话持久化、限流和 AI 回答。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.graph import run_parent_graph
from app.ai.state import AiMessage
from app.core.security import StoreAccessContext
from app.modules.chat.exceptions import ChatSessionNotFoundError
from app.modules.chat.repository import (
    get_session_with_messages,
    list_sessions,
    soft_delete_session,
    upsert_session_message_pair,
)
from app.modules.chat.schemas import (
    ChatHistoryMessage,
    ChatRequest,
    ChatResponse,
    ChatSessionMessages,
    ChatSessionSummary,
)


def _normalize_thread_id(value: str | None) -> str:
    return value.strip() if value and value.strip() else f"chat-{uuid.uuid4()}"


def _owner(access: StoreAccessContext | None, guest_id: str | None) -> tuple[uuid.UUID | None, uuid.UUID | None, str | None]:
    if access:
        return access.user_id, access.store_id, None
    return None, None, guest_id


async def chat_with_parent_graph(
    *,
    graph: Any,
    payload: ChatRequest,
    db: AsyncSession,
    access: StoreAccessContext | None = None,
) -> ChatResponse:
    thread_id = _normalize_thread_id(payload.thread_id)
    user_id, store_id, guest_id = _owner(access, payload.guest_id)
    messages: list[AiMessage] = [
        {"role": item.role, "content": item.content}
        for item in payload.messages
    ]
    messages.append({"role": "user", "content": payload.message})

    result = await run_parent_graph(
        graph,
        {
            "user_id": str(user_id) if user_id else None,
            "store_id": str(store_id) if store_id else None,
            "role": access.role if access else None,
            "message": payload.message,
            "messages": messages,
        },
        thread_id,
    )
    response = ChatResponse(
        threadId=thread_id,
        scene=result.get("scene", "fallback"),
        answer=result.get("answer", "暂时无法回答，请稍后再试。"),
        nextAction=result.get("next_action", ""),
        citations=result.get("citations", []),
    )
    await upsert_session_message_pair(
        thread_id=thread_id,
        user_id=user_id,
        store_id=store_id,
        guest_id=guest_id,
        user_message=payload.message,
        assistant_message=response.answer,
        scene=response.scene,
        db=db,
    )
    return response


async def list_chat_sessions(
    *,
    db: AsyncSession,
    access: StoreAccessContext | None = None,
    guest_id: str | None = None,
) -> list[ChatSessionSummary]:
    user_id, _, owner_guest_id = _owner(access, guest_id)
    sessions = await list_sessions(user_id=user_id, guest_id=owner_guest_id, db=db)
    return [
        ChatSessionSummary(
            id=str(item.id),
            threadId=item.thread_id,
            title=item.title,
            scene=item.scene,
            updatedAt=item.updated_at,
            createdAt=item.created_at,
        )
        for item in sessions
    ]


async def get_chat_messages(
    *,
    thread_id: str,
    db: AsyncSession,
    access: StoreAccessContext | None = None,
    guest_id: str | None = None,
) -> ChatSessionMessages:
    user_id, _, owner_guest_id = _owner(access, guest_id)
    session = await get_session_with_messages(
        thread_id=thread_id, user_id=user_id, guest_id=owner_guest_id, db=db
    )
    if session is None:
        raise ChatSessionNotFoundError("对话不存在或已删除")
    return ChatSessionMessages(
        threadId=session.thread_id,
        title=session.title,
        messages=[
            ChatHistoryMessage(
                id=str(item.id),
                role=item.role.value,
                messageType=item.message_type.value,
                content=item.content,
                metadata=item.message_metadata,
                createdAt=item.created_at,
            )
            for item in session.messages
        ],
    )


async def delete_chat_session(
    *,
    thread_id: str,
    db: AsyncSession,
    access: StoreAccessContext | None = None,
    guest_id: str | None = None,
) -> None:
    user_id, _, owner_guest_id = _owner(access, guest_id)
    deleted = await soft_delete_session(
        thread_id=thread_id, user_id=user_id, guest_id=owner_guest_id, db=db
    )
    if not deleted:
        raise ChatSessionNotFoundError("对话不存在或已删除")
