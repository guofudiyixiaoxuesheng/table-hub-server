"""AI 对话入口和历史会话管理。"""

from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import (
    AuthenticationError,
    StoreAccessContext,
    require_authenticated_user,
)
from app.modules.chat.schemas import ChatRequest
from app.modules.chat.service import (
    chat_with_parent_graph,
    delete_chat_session,
    get_chat_messages,
    list_chat_sessions,
    stream_chat_with_parent_graph,
)

router = APIRouter(prefix="/chat", tags=["chat"])
_optional_bearer = HTTPBearer(auto_error=False)
OptionalBearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None, Depends(_optional_bearer)
]
Database = Annotated[AsyncSession, Depends(get_database)]
GuestIdQuery = Annotated[str | None, Query(alias="guestId", max_length=120)]
StoreIdQuery = Annotated[uuid.UUID | None, Query(alias="storeId")]


def optional_access(credentials: OptionalBearerCredentials) -> StoreAccessContext | None:
    if credentials is None:
        return None
    try:
        return require_authenticated_user(credentials.credentials)
    except AuthenticationError:
        return None


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("")
async def chat(
    request: Request,
    payload: ChatRequest,
    db: Database,
    access: Annotated[StoreAccessContext | None, Depends(optional_access)],
) -> dict[str, object]:
    data = await chat_with_parent_graph(
        graph=request.app.state.parent_graph,
        payload=payload,
        db=db,
        access=access,
    )
    return success_response(data=data.model_dump(mode="json", by_alias=True))


@router.post("/stream")
async def chat_stream(
    request: Request,
    payload: ChatRequest,
    db: Database,
    access: Annotated[StoreAccessContext | None, Depends(optional_access)],
) -> StreamingResponse:
    async def event_stream():
        try:
            async for event, data in stream_chat_with_parent_graph(
                graph=request.app.state.parent_graph,
                payload=payload,
                db=db,
                access=access,
            ):
                yield _sse(event, data)
        except Exception as exc:
            await db.rollback()
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions")
async def sessions(
    db: Database,
    access: Annotated[StoreAccessContext | None, Depends(optional_access)],
    guest_id: GuestIdQuery = None,
    store_id: StoreIdQuery = None,
) -> dict[str, object]:
    data = await list_chat_sessions(db=db, access=access, guest_id=guest_id, store_id=store_id)
    return success_response(data=[item.model_dump(mode="json", by_alias=True) for item in data])


@router.get("/sessions/{thread_id}/messages")
async def session_messages(
    thread_id: str,
    db: Database,
    access: Annotated[StoreAccessContext | None, Depends(optional_access)],
    guest_id: GuestIdQuery = None,
    store_id: StoreIdQuery = None,
) -> dict[str, object]:
    data = await get_chat_messages(
        thread_id=thread_id, db=db, access=access, guest_id=guest_id, store_id=store_id
    )
    return success_response(data=data.model_dump(mode="json", by_alias=True))


@router.delete("/sessions/{thread_id}")
async def delete_session(
    thread_id: str,
    db: Database,
    access: Annotated[StoreAccessContext | None, Depends(optional_access)],
    guest_id: GuestIdQuery = None,
    store_id: StoreIdQuery = None,
) -> dict[str, object]:
    await delete_chat_session(
        thread_id=thread_id, db=db, access=access, guest_id=guest_id, store_id=store_id
    )
    return success_response(message="对话已删除")
