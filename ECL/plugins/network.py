"""受控网络能力：插件经权限门禁后使用共享 HTTP 客户端发起请求。"""

from __future__ import annotations

from dataclasses import dataclass, field

_MAX_HTTP_BODY_BYTES = 8 * 1024 * 1024


class PluginHttpError(RuntimeError):
    """
    插件网络请求失败或超出权限时抛出。
    """


@dataclass
class PluginHttpResponse:
    """
    插件可安全读取的 HTTP 响应视图，不暴露底层客户端对象。
    """

    status_code: int  # HTTP 状态码。
    url: str  # 最终响应 URL。
    headers: dict[str, str] = field(default_factory=dict)  # 响应头快照。
    text: str = ""  # UTF-8 文本内容。
    content_b64: str = ""  # Base64 编码的二进制内容。
    truncated: bool = False  # 内容是否因大小限制被截断。


def _action_for_method(method: str) -> str:
    # 只读方法走 read 权限，其余方法走 write 权限。
    return "read" if method.upper() in {"GET", "HEAD", "OPTIONS"} else "write"
