"""聊天请求、事件流和历史消息数据结构。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    thread_id: str | None = Field(default=None, alias="threadId", max_length=120)
    guest_id: str | None = Field(default=None, alias="guestId", max_length=120)
    message: str = Field(min_length=1, max_length=4000)
    messages: list[ChatMessage] = Field(default_factory=list, max_length=20)


class ChatResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    thread_id: str = Field(alias="threadId")
    scene: str
    answer: str
    next_action: str = Field(alias="nextAction")
    citations: list[dict[str, object]] = Field(default_factory=list)


class ChatSessionSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    thread_id: str = Field(alias="threadId")
    title: str
    scene: str | None = None
    updated_at: datetime = Field(alias="updatedAt")
    created_at: datetime = Field(alias="createdAt")


class ChatHistoryMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    role: Literal["user", "assistant", "system", "tool"]
    message_type: str = Field(alias="messageType", default="text")
    content: str
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(alias="createdAt")


class ChatSessionMessages(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    thread_id: str = Field(alias="threadId")
    title: str
    messages: list[ChatHistoryMessage]
