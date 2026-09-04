"""场次模块数据结构。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.game_session.models import (
    GameSessionImageSource,
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


class SessionImageAssetResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    label: str
    preview_url: str = Field(alias="previewUrl")
    relative_path: str | None = Field(default=None, alias="relativePath")
    page_number: int | None = Field(default=None, alias="pageNumber")


class RoomBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)
    capacity: int = Field(default=6, ge=1, le=50)
    location: str | None = Field(default=None, max_length=120)
    status: str = Field(default="active", pattern=r"^(active|disabled)$")
    notes: str | None = Field(default=None, max_length=1000)


class CreateRoomRequest(RoomBase):
    pass


class UpdateRoomRequest(RoomBase):
    pass


class RoomResponse(RoomBase):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    store_id: uuid.UUID = Field(alias="storeId")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class GameSessionBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    script_document_id: uuid.UUID | None = Field(default=None, alias="scriptDocumentId")
    dm_user_id: uuid.UUID | None = Field(default=None, alias="dmUserId")
    room_id: uuid.UUID | None = Field(default=None, alias="roomId")
    title: str = Field(min_length=1, max_length=160)
    script_name: str = Field(alias="scriptName", min_length=1, max_length=200)
    start_time: datetime = Field(alias="startTime")
    duration_minutes: int = Field(default=240, alias="durationMinutes", ge=30, le=1440)
    min_players: int = Field(default=1, alias="minPlayers", ge=1, le=50)
    capacity: int = Field(default=6, ge=1, le=50)
    price_cents: int = Field(default=0, alias="priceCents", ge=0)
    description: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    cover_image_source: GameSessionImageSource | None = Field(default=None, alias="coverImageSource")
    cover_image_asset_id: uuid.UUID | None = Field(default=None, alias="coverImageAssetId")
    cover_image_url: str | None = Field(default=None, alias="coverImageUrl", max_length=2048)
    detail_image_source: GameSessionImageSource | None = Field(default=None, alias="detailImageSource")
    detail_image_asset_ids: list[uuid.UUID] = Field(default_factory=list, alias="detailImageAssetIds", max_length=20)
    detail_image_urls: list[str] = Field(default_factory=list, alias="detailImageUrls", max_length=20)

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
    room_id: uuid.UUID | None = Field(default=None, alias="roomId")
    room_name: str | None = Field(default=None, alias="roomName")
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
    my_reservation_id: uuid.UUID | None = Field(default=None, alias="myReservationId")
    my_reservation_status: SessionPlayerStatus | None = Field(default=None, alias="myReservationStatus")
    my_reservation_code: str | None = Field(default=None, alias="myReservationCode")
    cover_image_source: GameSessionImageSource | None = Field(default=None, alias="coverImageSource")
    cover_image_asset_id: uuid.UUID | None = Field(default=None, alias="coverImageAssetId")
    cover_image_url: str | None = Field(default=None, alias="coverImageUrl")
    detail_image_source: GameSessionImageSource | None = Field(default=None, alias="detailImageSource")
    detail_image_asset_ids: list[uuid.UUID] = Field(default_factory=list, alias="detailImageAssetIds")
    detail_image_urls: list[str] = Field(default_factory=list, alias="detailImageUrls")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class GameSessionDetailResponse(GameSessionResponse):
    players: list[SessionPlayerResponse]
