"""将业务异常转换为统一的 FastAPI HTTP 响应。"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import ApplicationError


async def application_error_handler(
    _: Request, error: Exception
) -> JSONResponse:
    """把业务异常转换为稳定的 JSON 错误响应。"""

    if not isinstance(error, ApplicationError):
        raise error

    return JSONResponse(
        status_code=error.status_code,
        content={"code": error.code, "message": error.message, "data": None},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """注册项目级异常处理器。"""

    app.add_exception_handler(ApplicationError, application_error_handler)
