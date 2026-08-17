from dataclasses import dataclass
from enum import StrEnum

from ECL.utils import PluginCommandError  # noqa: F401  # re-export


class PluginAction(StrEnum):
    """插件管理操作类型。"""

    ENABLE = "enable"
    DISABLE = "disable"
    UNLOAD = "unload"
    RELOAD = "reload"
    INSTALL = "install"
    UPDATE_SETTING = "update_setting"


@dataclass(frozen=True, slots=True)
class PluginActionResult:
    """插件操作的执行结果。"""

    plugin_name: str  # 目标插件名
    action: PluginAction  # 执行的操作类型
    status: str  # 操作结果状态
    message: str = ""  # 结果说明

    @property
    def success(self) -> bool:
        """判断操作是否成功。"""
        return self.status in {"enabled", "disabled", "unloaded", "installed", "updated"}
