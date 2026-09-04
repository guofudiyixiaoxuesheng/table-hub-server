"""用户模块的数据传输结构。"""

from app.modules.user.schemas.create_user import (
    CreateUserRequest,
    UpdateStorePlayerRequest,
    UpsertStorePlayerRequest,
)
from app.modules.user.schemas.user import (
    PlayerBehaviorSummaryResponse,
    PlayerSessionBehaviorItem,
    StorePlayerListResponse,
    StorePlayerAnalyticsResponse,
    StorePlayerResponse,
    UserResponse,
)

__all__ = [
    "CreateUserRequest",
    "UpdateStorePlayerRequest",
    "UpsertStorePlayerRequest",
    "PlayerBehaviorSummaryResponse",
    "PlayerSessionBehaviorItem",
    "StorePlayerAnalyticsResponse",
    "StorePlayerListResponse",
    "StorePlayerResponse",
    "UserResponse",
]
