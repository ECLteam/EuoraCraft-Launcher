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
    presentation: NotRequired[Literal["message", "modal"]]
    errorId: NotRequired[str]
    title: NotRequired[str]
    detail: NotRequired[str]


ApiResponse = ApiSuccess[Any] | ApiFailure


def success(data: T | None = None) -> ApiSuccess[T | None]:
    """
    创建成功响应。

    :param data: 需要处理或持久化的数据
    """
    return {"success": True, "data": data}


def failure(
    message: str,
    error_code: str,
    *,
    presentation: Literal["message", "modal"] = "message",
    error_id: str | None = None,
    title: str | None = None,
    detail: str | None = None,
) -> ApiFailure:
    """
    创建失败响应。

    :param message: 面向用户的错误说明
    :param error_code: 供前端识别的稳定错误码
    :param presentation: 建议前端使用顶部消息或全局弹窗呈现
    :param error_id: 严重错误与日志、事件关联的唯一编号
    :param title: 严重错误弹窗标题
    :param detail: 可安全展示给用户的补充信息
    """
    result: ApiFailure = {
        "success": False,
        "message": message,
        "errorCode": error_code,
        "presentation": presentation,
    }
    if error_id:
        result["errorId"] = error_id
    if title:
        result["title"] = title
    if detail:
        result["detail"] = detail
    return result
