"""场次模块数据结构。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.game_session.models import (
    GameSessionStatus,
    SessionJoinSource,
    SessionPlayerStatus,
)


class ScriptOptionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    name: str
    script_genre: str | None = Field(default=None, alias="scriptGenre")
    description: str | None = None


class DmOptionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    nickname: str | None
    phone: str | None


class GameSessionBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    script_document_id: uuid.UUID | None = Field(default=None, alias="scriptDocumentId")
    dm_user_id: uuid.UUID | None = Field(default=None, alias="dmUserId")
    title: str = Field(min_length=1, max_length=160)
    script_name: str = Field(alias="scriptName", min_length=1, max_length=200)
    start_time: datetime = Field(alias="startTime")
    duration_minutes: int = Field(default=240, alias="durationMinutes", ge=30, le=1440)
    min_players: int = Field(default=1, alias="minPlayers", ge=1, le=50)
    capacity: int = Field(default=6, ge=1, le=50)
    price_cents: int = Field(default=0, alias="priceCents", ge=0)
    description: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_capacity(self):
        if self.min_players > self.capacity:
            raise ValueError("最低成团人数不能大于最大人数")
        return self


class CreateGameSessionRequest(GameSessionBase):
    pass


class UpdateGameSessionRequest(GameSessionBase):
    status: GameSessionStatus = GameSessionStatus.RECRUITING


class SessionPlayerRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    user_id: uuid.UUID | None = Field(default=None, alias="userId")
    player_name: str = Field(alias="playerName", min_length=1, max_length=80)
    phone: str | None = Field(default=None, max_length=20)
    seat_count: int = Field(default=1, alias="seatCount", ge=1, le=10)
    source: SessionJoinSource = SessionJoinSource.MANUAL
    status: SessionPlayerStatus = SessionPlayerStatus.PENDING
    notes: str | None = Field(default=None, max_length=1000)


class UpdateSessionPlayerRequest(SessionPlayerRequest):
    pass


class SessionPlayerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    session_id: uuid.UUID = Field(alias="sessionId")
    user_id: uuid.UUID | None = Field(alias="userId")
    player_name: str = Field(alias="playerName")
    phone: str | None
    seat_count: int = Field(alias="seatCount")
    reservation_code: str = Field(alias="reservationCode")
    source: SessionJoinSource
    status: SessionPlayerStatus
    notes: str | None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class GameSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    store_id: uuid.UUID = Field(alias="storeId")
    script_document_id: uuid.UUID | None = Field(alias="scriptDocumentId")
    dm_user_id: uuid.UUID | None = Field(alias="dmUserId")
    title: str
    script_name: str = Field(alias="scriptName")
    start_time: datetime = Field(alias="startTime")
    duration_minutes: int = Field(alias="durationMinutes")
    min_players: int = Field(alias="minPlayers")
    capacity: int
    price_cents: int = Field(alias="priceCents")
    status: GameSessionStatus
    description: str | None
    notes: str | None
    joined_seats: int = Field(alias="joinedSeats")
    player_count: int = Field(alias="playerCount")
    dm_name: str | None = Field(default=None, alias="dmName")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class GameSessionDetailResponse(GameSessionResponse):
    players: list[SessionPlayerResponse]
