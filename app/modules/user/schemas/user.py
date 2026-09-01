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
