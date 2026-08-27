"""定义与 Web 框架无关的统一业务异常。"""


class ApplicationError(Exception):
    """所有可预期业务异常的基类。"""

    status_code = 400
    code = "application_error"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ConflictError(ApplicationError):
    """资源状态或唯一性冲突。"""

    status_code = 409
    code = "conflict"
