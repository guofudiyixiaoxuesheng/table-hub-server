"""用户模块业务异常。"""

from app.core.exceptions import ConflictError


class UserPhoneAlreadyExistsError(ConflictError):
    """手机号已被其他用户占用。"""

    def __init__(self) -> None:
        super().__init__("该手机号已注册")
