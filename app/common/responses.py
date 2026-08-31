"""统一 API 成功响应函数。"""

from typing import Any


def success_response(
    data: Any = None,
    message: str = "success",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """生成项目统一成功响应。"""

    response = {"code": "ok", "message": message, "data": data}
    if meta is not None:
        response["meta"] = meta
    return response
