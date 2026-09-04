"""用户响应结构。"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.modules.user.models import UserRole, UserStatus


class UserResponse(BaseModel):
    """对外返回的安全用户字段，不包含密码哈希。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone: str | None
    nickname: str | None
    avatar_url: str | None
    role: UserRole
    status: UserStatus
    phone_verified_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StorePlayerResponse(BaseModel):
    """门店玩家客户池响应。"""

    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    user_id: uuid.UUID
    phone: str | None
    nickname: str | None
    avatar_url: str | None
    preference: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class StorePlayerListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[StorePlayerResponse]
    total: int
    page: int
    page_size: int


class PlayerSessionBehaviorItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: uuid.UUID
    title: str
    script_name: str
    script_genre: str | None = None
    start_time: datetime
    duration_minutes: int
    capacity: int
    joined_seats: int
    price_cents: int
    cover_image_url: str | None = None
    join_status: str
    reservation_code: str
    source: str
    seat_count: int
    joined_at: datetime
    updated_at: datetime


class PlayerBehaviorSummaryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    store_player: StorePlayerResponse
    reservation_count: int
    completed_count: int
    cancelled_count: int
    active_reservation_count: int
    cancellation_rate: float
    estimated_spend_cents: int
    favorite_genres: list[str]
    recent_sessions: list[PlayerSessionBehaviorItem]
    ai_summary: str


class StorePlayerAnalyticsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    total_players: int
    reservation_count: int
    completed_count: int
    cancelled_count: int
    active_reservation_count: int
    cancellation_rate: float
    estimated_revenue_cents: int
    top_genres: list[dict[str, object]]
    active_players: list[dict[str, object]]
    risk_players: list[dict[str, object]]
    ai_summary: str
