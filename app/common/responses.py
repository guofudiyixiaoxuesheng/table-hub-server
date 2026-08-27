"""统一 API 成功和失败响应结构。"""

from pydantic import BaseModel


class ApiResponse[DataT](BaseModel):
    """成功响应统一外层结构。"""

    code: str = "ok"
    message: str = "success"
    data: DataT
