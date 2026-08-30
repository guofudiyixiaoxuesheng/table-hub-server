"""对话线程、消息和引用记录 ORM 模型。"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ChatSessionStatus(str, enum.Enum):
    ACTIVE = "active"
    DELETED = "deleted"


class ChatMessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ChatMessageType(str, enum.Enum):
    """消息展示类型；用于后续图片、文件、预约卡片和工具结果扩展。"""

    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    ACTION_CARD = "action_card"
    SYSTEM_EVENT = "system_event"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


class ChatSession(Base):
    """AI 对话业务会话，用于左侧历史列表。"""

    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index("uq_chat_sessions_thread_id", "thread_id", unique=True),
        Index("ix_chat_sessions_user_updated", "user_id", "updated_at"),
        Index("ix_chat_sessions_guest_updated", "guest_id", "updated_at"),
        Index("ix_chat_sessions_store_updated", "store_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[str] = mapped_column(String(120), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    store_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=True
    )
    guest_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    scene: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[ChatSessionStatus] = mapped_column(
        Enum(
            ChatSessionStatus,
            name="chat_session_status",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=ChatSessionStatus.ACTIVE,
        server_default=ChatSessionStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    """AI 对话消息记录。"""

    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_session_created", "session_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[ChatMessageRole] = mapped_column(
        Enum(
            ChatMessageRole,
            name="chat_message_role",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
    )
    message_type: Mapped[ChatMessageType] = mapped_column(
        Enum(
            ChatMessageType,
            name="chat_message_type",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=ChatMessageType.TEXT,
        server_default=ChatMessageType.TEXT.value,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped[ChatSession] = relationship(back_populates="messages")
