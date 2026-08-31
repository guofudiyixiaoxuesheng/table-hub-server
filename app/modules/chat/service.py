"""编排会话持久化、限流和 AI 回答。"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.graph import run_parent_graph, stream_parent_graph
from app.ai.state import AiMessage
from app.core.security import StoreAccessContext
from app.modules.chat.exceptions import ChatSessionNotFoundError
from app.modules.chat.repository import (
    ensure_visible_session,
    get_session_with_messages,
    list_recent_messages,
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


async def _build_graph_state(
    *,
    payload: ChatRequest,
    db: AsyncSession,
    access: StoreAccessContext | None,
) -> tuple[str, uuid.UUID | None, uuid.UUID | None, str | None, dict[str, Any]]:
    thread_id = _normalize_thread_id(payload.thread_id)
    user_id, store_id, guest_id = _owner(access, payload.guest_id)
    session = await ensure_visible_session(
        thread_id=thread_id,
        user_id=user_id,
        store_id=store_id,
        guest_id=guest_id,
        first_message=payload.message,
        db=db,
    )
    history = await list_recent_messages(session_id=session.id, db=db)
    messages: list[AiMessage] = [
        {"role": item.role.value, "content": item.content}
        for item in history
        if item.role.value in {"user", "assistant", "system", "tool"}
    ]
    messages.append({"role": "user", "content": payload.message})
    return thread_id, user_id, store_id, guest_id, {
        "user_id": str(user_id) if user_id else None,
        "store_id": str(store_id) if store_id else None,
        "role": access.role if access else None,
        "message": payload.message,
        "messages": messages,
    }


def _response_from_state(thread_id: str, state: dict[str, Any]) -> ChatResponse:
    return ChatResponse(
        threadId=thread_id,
        scene=state.get("scene", "fallback"),
        intent=state.get("intent", ""),
        intentConfidence=state.get("intent_confidence", 0),
        intentReason=state.get("intent_reason", ""),
        rawScene=state.get("raw_scene", ""),
        rawIntent=state.get("raw_intent", ""),
        answer=state.get("answer", "暂时无法回答，请稍后再试。"),
        nextAction=state.get("next_action", ""),
        citations=state.get("citations", []),
    )


def _public_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "scene": state.get("scene"),
        "intent": state.get("intent"),
        "intentConfidence": state.get("intent_confidence"),
        "intentReason": state.get("intent_reason"),
        "rawScene": state.get("raw_scene"),
        "rawIntent": state.get("raw_intent"),
        "scenePayload": state.get("scene_payload", {}),
        "rewrittenQuery": state.get("rewritten_query"),
        "answer": state.get("answer"),
        "nextAction": state.get("next_action"),
        "citations": state.get("citations", []),
    }


def _merge_update_event(state: dict[str, Any], event: Any) -> dict[str, Any]:
    if not isinstance(event, dict):
        return state
    for value in event.values():
        if isinstance(value, dict):
            state.update(value)
    return state


async def chat_with_parent_graph(
    *,
    graph: Any,
    payload: ChatRequest,
    db: AsyncSession,
    access: StoreAccessContext | None = None,
) -> ChatResponse:
    thread_id, user_id, store_id, guest_id, state = await _build_graph_state(
        payload=payload, db=db, access=access
    )

    result = await run_parent_graph(
        graph,
        state,
        thread_id,
    )
    response = _response_from_state(thread_id, result)
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


async def stream_chat_with_parent_graph(
    *,
    graph: Any,
    payload: ChatRequest,
    db: AsyncSession,
    access: StoreAccessContext | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    thread_id, user_id, store_id, guest_id, state = await _build_graph_state(
        payload=payload, db=db, access=access
    )
    final_state = dict(state)
    yield "session", {"threadId": thread_id, "streamMode": payload.stream_mode}

    async for event in stream_parent_graph(
        graph,
        state,
        thread_id,
        stream_mode=payload.stream_mode,
    ):
        if payload.stream_mode == "values" and isinstance(event, dict):
            final_state = dict(event)
            yield "state", _public_state(final_state)
            continue

        final_state = _merge_update_event(final_state, event)
        yield "update", {"raw": event, "state": _public_state(final_state)}

    response = _response_from_state(thread_id, final_state)
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
    yield "answer", response.model_dump(mode="json", by_alias=True)
    yield "done", {"threadId": thread_id}


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
