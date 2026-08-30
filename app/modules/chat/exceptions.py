"""聊天模块业务异常。"""

from app.core.exceptions import ApplicationError


class ChatSessionNotFoundError(ApplicationError):
    status_code = 404
    code = "chat_session_not_found"
