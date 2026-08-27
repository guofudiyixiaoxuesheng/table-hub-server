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
