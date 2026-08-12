from __future__ import annotations

from typing import Any, Generic, Literal, NotRequired, TypedDict, TypeVar

T = TypeVar("T")


class ApiSuccess(TypedDict, Generic[T]):
    """
    IPC 成功响应。
    """

    success: Literal[True]
    data: NotRequired[T]


class ApiFailure(TypedDict):
    """
    IPC 失败响应。
    """

    success: Literal[False]
    message: str
    errorCode: str


ApiResponse = ApiSuccess[Any] | ApiFailure


def success(data: T | None = None) -> ApiSuccess[T | None]:
    """
    创建成功响应。

    :param data: 需要处理或持久化的数据
    """
    return {"success": True, "data": data}


def failure(message: str, error_code: str) -> ApiFailure:
    """
    创建失败响应。

    :param message: 面向用户的错误说明
    :param error_code: 供前端识别的稳定错误码
    """
    return {"success": False, "message": message, "errorCode": error_code}
