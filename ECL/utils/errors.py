"""
集中定义后端各领域共用的自定义异常。

主仓库内的业务异常统一在此声明，供 api / services / plugins / utils 各层通过
本模块或各模块的 re-export 使用；子仓库（ECL/game、ECL/services/florolding）
不在本模块范围内。

异常按命名空间分组，公共字段统一在基类中声明：
- ``error_code``：面向前端和 IPC 的稳定错误码
"""

from copy import deepcopy


class ConfigError(RuntimeError):
    """
    配置读写的通用错误。
    """


class ConfigValidationError(ConfigError, ValueError):
    """
    配置参数不合法。
    """


class PluginCommandError(Exception):
    """
    插件命令执行失败。
    """


class AccountError(Exception):
    """
    表示可安全转换为稳定 IPC 错误码的账户操作失败。

    :param message: 面向用户的错误说明
    :param error_code: 供前端识别的稳定错误码
    """

    def __init__(self, message: str, error_code: str = "ACCOUNT_ERROR"):
        super().__init__(message)
        self.error_code = error_code


class AuthlibError(RuntimeError):
    """
    外置登录（authlib-injector）相关的通用错误。
    """


class AuthlibProfileSelectionRequired(AuthlibError):
    """
    外置登录账户存在多个角色，需要调用方主动指定本次登录使用的角色。

    :param profiles: 可选的在线角色列表
    """

    def __init__(self, profiles: list[dict]) -> None:
        super().__init__("该登录名下有多个角色，请选择本次登录使用的角色")
        self.profiles = deepcopy(profiles)


class ConnectorError(Exception):
    """
    联机服务通用错误。
    """


class ConnectorNotAvailableError(ConnectorError):
    """
    联机服务不可用（依赖缺失）。
    """


class DebugMaintenanceError(ValueError):
    """
    调试维护操作的目标或动作不合法。
    """


class WardrobeError(RuntimeError):
    """
    表示可安全返回给前端的衣柜业务错误。

    :param message: 面向用户的错误说明
    :param error_code: 供 IPC 和前端稳定识别的错误码
    """

    def __init__(self, message: str, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class GameServiceError(Exception):
    """
    表示可安全转换为稳定 IPC 错误码的游戏操作失败。

    :param message: 面向用户的错误说明
    :param error_code: 供前端识别的稳定错误码
    """

    def __init__(self, message: str, error_code: str = "GAME_OPERATION_FAILED"):
        super().__init__(message)
        self.error_code = error_code


class VersionScanError(GameServiceError):
    """
    游戏版本扫描失败。

    :param message: 面向用户的错误说明
    :param error_code: 供前端识别的稳定错误码
    """

    def __init__(self, message: str, error_code: str = "VERSION_SCAN_FAILED"):
        super().__init__(message, error_code)


__all__ = [
    "AccountError",
    "AuthlibError",
    "AuthlibProfileSelectionRequired",
    "ConfigError",
    "ConfigValidationError",
    "ConnectorError",
    "ConnectorNotAvailableError",
    "DebugMaintenanceError",
    "GameServiceError",
    "PluginCommandError",
    "VersionScanError",
    "WardrobeError",
]
