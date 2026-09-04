"""场次、时间、容量、DM 和拼车玩家 ORM 模型。"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class GameSessionStatus(str, enum.Enum):
    RECRUITING = "recruiting"
    FULL = "full"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class SessionPlayerStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class SessionJoinSource(str, enum.Enum):
    H5 = "h5"
    MANUAL = "manual"
    WECHAT_CHAT = "wechat_chat"


class GameSessionImageSource(str, enum.Enum):
    MANUAL = "manual"
    KNOWLEDGE_ASSET = "knowledge_asset"
    AI_GENERATED = "ai_generated"


class Room(Base):
    """门店房间/包间资源，用于场次排期占用。"""

    __tablename__ = "rooms"
    __table_args__ = (
        Index("ix_rooms_store_status", "store_id", "status"),
        Index("ix_rooms_store_name", "store_id", "name", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sessions: Mapped[list[GameSession]] = relationship(back_populates="room")


class GameSession(Base):
    """商家发布的一场可报名剧本活动。"""

    __tablename__ = "game_sessions"
    __table_args__ = (
        Index("ix_game_sessions_store_start_time", "store_id", "start_time"),
        Index("ix_game_sessions_store_status", "store_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    script_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    dm_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    script_name: Mapped[str] = mapped_column(String(200), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=240)
    min_players: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[GameSessionStatus] = mapped_column(
        Enum(
            GameSessionStatus,
            name="game_session_status",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=GameSessionStatus.RECRUITING,
        server_default=GameSessionStatus.RECRUITING.value,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_image_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cover_image_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_parsed_assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cover_image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    detail_image_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    detail_image_asset_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    detail_image_urls: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    players: Mapped[list[SessionPlayer]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    room: Mapped[Room | None] = relationship(back_populates="sessions")


class SessionPlayer(Base):
    """某个场次下的一条约车/报名记录。"""

    __tablename__ = "session_players"
    __table_args__ = (
        Index("ix_session_players_session_status", "session_id", "status"),
        Index("ix_session_players_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    player_name: Mapped[str] = mapped_column(String(80), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    seat_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reservation_code: Mapped[str] = mapped_column(String(12), nullable=False, unique=True)
    source: Mapped[SessionJoinSource] = mapped_column(
        Enum(
            SessionJoinSource,
            name="session_join_source",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=SessionJoinSource.MANUAL,
        server_default=SessionJoinSource.MANUAL.value,
    )
    status: Mapped[SessionPlayerStatus] = mapped_column(
        Enum(
            SessionPlayerStatus,
            name="session_player_status",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=SessionPlayerStatus.PENDING,
        server_default=SessionPlayerStatus.PENDING.value,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    session: Mapped[GameSession] = relationship(back_populates="players")
