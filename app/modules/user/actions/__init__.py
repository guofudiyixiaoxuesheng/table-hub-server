"""用户业务用例，每个文件对应一个可独立测试的动作函数。"""

from app.modules.user.actions.create_user import create_user_action
from app.modules.user.actions.analyze_store_players import (
    get_current_player_behavior_summary,
    get_player_behavior_summary,
    get_store_player_analytics,
)
from app.modules.user.actions.manage_store_players import (
    create_store_player,
    delete_store_player,
    list_store_players,
    update_store_player,
)

__all__ = [
    "create_user_action",
    "get_current_player_behavior_summary",
    "get_player_behavior_summary",
    "get_store_player_analytics",
    "create_store_player",
    "delete_store_player",
    "list_store_players",
    "update_store_player",
]
