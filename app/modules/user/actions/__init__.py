"""用户业务用例，每个文件对应一个可独立测试的动作函数。"""

from app.modules.user.actions.create_user import create_user_action

__all__ = ["create_user_action"]
