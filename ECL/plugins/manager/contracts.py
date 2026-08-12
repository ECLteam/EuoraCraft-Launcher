from dataclasses import dataclass
from enum import StrEnum


class PluginCommandError(Exception):
    """
    Plugin command execution failed.
    """


class PluginAction(StrEnum):
    ENABLE = "enable"
    DISABLE = "disable"
    UNLOAD = "unload"
    RELOAD = "reload"
    INSTALL = "install"
    UPDATE_SETTING = "update_setting"


@dataclass(frozen=True, slots=True)
class PluginActionResult:
    plugin_name: str
    action: PluginAction
    status: str
    message: str = ""

    @property
    def success(self) -> bool:
        return self.status in {"enabled", "disabled", "unloaded", "installed", "updated"}
