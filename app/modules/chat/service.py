"""编排会话持久化、限流和 AI 回答。"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.graph import run_parent_graph, stream_parent_graph
from app.ai.state import AiMessage
from app.core.security import StoreAccessContext
from app.core.store_context import resolve_request_store_id
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
from app.modules.analytics.service import maybe_create_rag_evaluation_from_state
from app.observability.langfuse import langfuse_callbacks
from app.observability.tracing import trace_chat


def _normalize_thread_id(value: str | None) -> str:
    return value.strip() if value and value.strip() else f"chat-{uuid.uuid4()}"


async def _owner(
    *,
    db: AsyncSession,
    access: StoreAccessContext | None,
    guest_id: str | None,
    requested_store_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID | None, uuid.UUID | None, str | None]:
    if access:
        return access.user_id, access.store_id, None
    store_id = await resolve_request_store_id(
        db=db,
        access=access,
        requested_store_id=requested_store_id,
    )
    return None, store_id, guest_id


async def _build_graph_state(
    *,
    payload: ChatRequest,
    db: AsyncSession,
    access: StoreAccessContext | None,
) -> tuple[str, uuid.UUID | None, uuid.UUID | None, str | None, dict[str, Any]]:
    thread_id = _normalize_thread_id(payload.thread_id)
    user_id, store_id, guest_id = await _owner(
        db=db,
        access=access,
        guest_id=payload.guest_id,
        requested_store_id=payload.store_id,
    )
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


def _split_stream_event(event: Any) -> tuple[str | None, Any]:
    """兼容 LangGraph 单 stream_mode 和多 stream_mode 的事件形态。

    stream_mode=["updates", "custom"] 时，LangGraph 会返回：
    ("updates", {...}) 或 ("custom", {...})。

    subgraphs=True 后，子图事件可能带 namespace：
    (("script_rag_handler:xxx",), "custom", {...})
    或 (("script_rag_handler:xxx",), ("custom", {...}))。
    """

    if (
        isinstance(event, tuple)
        and len(event) == 3
        and event[1] in {"updates", "custom", "values"}
    ):
        return event[1], event[2]
    if (
        isinstance(event, tuple)
        and len(event) == 2
        and isinstance(event[1], tuple)
        and len(event[1]) == 2
        and event[1][0] in {"updates", "custom", "values"}
    ):
        return event[1][0], event[1][1]
    if (
        isinstance(event, tuple)
        and len(event) == 2
        and event[0] in {"updates", "custom", "values"}
    ):
        return event[0], event[1]
    return None, event


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

    metadata = {
        "store_id": str(store_id) if store_id else None,
        "user_id": str(user_id) if user_id else None,
        "guest_id": guest_id,
        "stream": False,
    }
    with trace_chat(
        trace_name="tablehub-ai-chat",
        user_id=str(user_id) if user_id else None,
        session_id=thread_id,
        store_id=str(store_id) if store_id else None,
        guest_id=guest_id,
        metadata=metadata,
    ):
        result = await run_parent_graph(
            graph,
            state,
            thread_id,
            callbacks=langfuse_callbacks(),
            metadata=metadata,
            db_session=db,
        )
    response = _response_from_state(thread_id, result)
    chat_session = await upsert_session_message_pair(
        thread_id=thread_id,
        user_id=user_id,
        store_id=store_id,
        guest_id=guest_id,
        user_message=payload.message,
        assistant_message=response.answer,
        scene=response.scene,
        db=db,
    )
    await maybe_create_rag_evaluation_from_state(
        thread_id=thread_id,
        store_id=store_id,
        user_id=user_id,
        guest_id=guest_id,
        chat_session=chat_session,
        question=payload.message,
        state=result,
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

    metadata = {
        "store_id": str(store_id) if store_id else None,
        "user_id": str(user_id) if user_id else None,
        "guest_id": guest_id,
        "stream": True,
        "stream_mode": payload.stream_mode,
    }
    with trace_chat(
        trace_name="tablehub-ai-chat-stream",
        user_id=str(user_id) if user_id else None,
        session_id=thread_id,
        store_id=str(store_id) if store_id else None,
        guest_id=guest_id,
        metadata=metadata,
    ):
        async for event in stream_parent_graph(
            graph,
            state,
            thread_id,
            stream_mode=payload.stream_mode,
            callbacks=langfuse_callbacks(),
            metadata=metadata,
            db_session=db,
        ):
            event_mode, event_payload = _split_stream_event(event)
            if event_mode == "custom":
                if isinstance(event_payload, dict) and event_payload.get("type") == "answer_delta":
                    yield "delta", {"delta": event_payload.get("delta", "")}
                else:
                    yield "custom", {"raw": event_payload}
                continue
            event = event_payload

            if payload.stream_mode == "values" and isinstance(event, dict):
                final_state = dict(event)
                yield "state", _public_state(final_state)
                continue

            final_state = _merge_update_event(final_state, event)
            yield "update", {"raw": event, "state": _public_state(final_state)}

    response = _response_from_state(thread_id, final_state)
    chat_session = await upsert_session_message_pair(
        thread_id=thread_id,
        user_id=user_id,
        store_id=store_id,
        guest_id=guest_id,
        user_message=payload.message,
        assistant_message=response.answer,
        scene=response.scene,
        db=db,
    )
    await maybe_create_rag_evaluation_from_state(
        thread_id=thread_id,
        store_id=store_id,
        user_id=user_id,
        guest_id=guest_id,
        chat_session=chat_session,
        question=payload.message,
        state=final_state,
        db=db,
    )
    yield "answer", response.model_dump(mode="json", by_alias=True)
    yield "done", {"threadId": thread_id}


async def list_chat_sessions(
    *,
    db: AsyncSession,
    access: StoreAccessContext | None = None,
    guest_id: str | None = None,
    store_id: uuid.UUID | None = None,
) -> list[ChatSessionSummary]:
    user_id, owner_store_id, owner_guest_id = await _owner(
        db=db,
        access=access,
        guest_id=guest_id,
        requested_store_id=store_id,
    )
    sessions = await list_sessions(user_id=user_id, store_id=owner_store_id, guest_id=owner_guest_id, db=db)
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
    store_id: uuid.UUID | None = None,
) -> ChatSessionMessages:
    user_id, owner_store_id, owner_guest_id = await _owner(
        db=db,
        access=access,
        guest_id=guest_id,
        requested_store_id=store_id,
    )
    session = await get_session_with_messages(
        thread_id=thread_id, user_id=user_id, store_id=owner_store_id, guest_id=owner_guest_id, db=db
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
    store_id: uuid.UUID | None = None,
) -> None:
    user_id, owner_store_id, owner_guest_id = await _owner(
        db=db,
        access=access,
        guest_id=guest_id,
        requested_store_id=store_id,
    )
    deleted = await soft_delete_session(
        thread_id=thread_id, user_id=user_id, store_id=owner_store_id, guest_id=owner_guest_id, db=db
    )
    if not deleted:
        raise ChatSessionNotFoundError("对话不存在或已删除")
