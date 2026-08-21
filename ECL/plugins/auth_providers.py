"""自定义账户/登录扩展点：插件注册第三方认证提供方并参与凭据解析。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ECL.utils import get_logger


@dataclass(frozen=True)
class AuthField:
    """
    动态登录表单的单个输入项。
    """

    key: str  # 提交给认证回调的字段键。
    label: str  # 面向用户的字段标签。
    type: str = "text"  # 前端输入控件类型。
    required: bool = True  # 是否必须填写。
    placeholder: str = ""  # 输入提示文本。


@dataclass
class AuthProvider:
    """
    插件注册的认证提供方。

    ``authenticate`` 接收前端提交的字段值字典，返回账户原始信息：
    ``{"id", "alias", "uuid"}`` 必填，``data`` 可保存令牌等不透明负载，
    ``skinUrl`` 可选。``resolve_credentials`` 在启动时接收公开账户字典并返回
    ``{"player_name", "uuid", "user_type", "access_token", "auth_server"?}``，
    其中 ``user_type`` 必须为 ``msa`` / ``yggdrasil`` / ``legacy`` 之一。
    """

    id: str  # 提供方稳定标识。
    title: str  # 前端显示名称。
    fields: list[AuthField]  # 动态登录表单字段。
    authenticate: Callable[[Mapping[str, Any]], dict[str, Any]]  # 认证回调。
    resolve_credentials: Callable[[dict[str, Any]], dict[str, str]]  # 启动凭据解析回调。
    owner: str = ""  # 注册此提供方的插件名。
    description: str = ""  # 可选的用户说明。

    def to_dict(self) -> dict[str, Any]:
        """
        返回前端可安全消费的提供方定义。

        :return: 不包含认证回调的表单元数据
        """
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "fields": [
                {
                    "key": item.key,
                    "label": item.label,
                    "type": item.type,
                    "required": item.required,
                    "placeholder": item.placeholder,
                }
                for item in self.fields
            ],
        }


class AuthProviderRegistry:
    """
    维护插件认证提供方，供账户服务聚合展示与凭据解析。
    """

    def __init__(self) -> None:
        self._providers: dict[str, AuthProvider] = {}  # 按标识索引的提供方。
        self._logger = get_logger("AuthProviderRegistry")  # 扩展点日志器。

    def register(
        self,
        owner: str,
        provider_id: str,
        title: str,
        fields: list[AuthField],
        authenticate: Callable[[Mapping[str, Any]], dict[str, Any]],
        resolve_credentials: Callable[[dict[str, Any]], dict[str, str]],
        description: str = "",
    ) -> None:
        """
        注册或原位更新一个认证提供方。

        :param owner: 插件名
        :param provider_id: 稳定标识，最终账户 ID 为 ``plugin:<provider_id>:<account_id>``
        :param title: 面向用户的显示名称
        :param fields: 动态登录表单字段
        :param authenticate: 认证回调
        :param resolve_credentials: 启动凭据解析回调
        :param description: 可选描述
        """
        self._providers[provider_id] = AuthProvider(
            id=provider_id,
            title=title,
            fields=list(fields),
            authenticate=authenticate,
            resolve_credentials=resolve_credentials,
            owner=owner,
            description=description,
        )

    def unregister_owner(self, owner: str) -> None:
        """
        撤销指定插件注册的全部提供方。
        """
        for provider_id in [pid for pid, provider in self._providers.items() if provider.owner == owner]:
            self._providers.pop(provider_id, None)

    def get(self, provider_id: str) -> AuthProvider | None:
        """
        按稳定标识获取认证提供方。

        :param provider_id: 提供方标识
        :return: 已注册的提供方；不存在时为 None
        """
        return self._providers.get(provider_id)

    def list_providers(self) -> list[AuthProvider]:
        """
        按注册顺序返回全部提供方。
        """
        return list(self._providers.values())
