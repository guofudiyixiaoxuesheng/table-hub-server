"""统一 API 成功响应函数。"""

from typing import Any


def success_response(
    data: Any = None,
    message: str = "success",
) -> dict[str, Any]:
    """生成项目统一成功响应。"""

    return {"code": "ok", "message": message, "data": data}
