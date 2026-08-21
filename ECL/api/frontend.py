from ECL.api.accounts import AccountHandlers
from ECL.api.bridge import (
    _Emitter,
    _FrontendState,
    _guess_image_extension,
    _mime_to_ext,
    _normalize_image_url,
)
from ECL.api.connector import ConnectorHandlers
from ECL.api.files import FileHandlers
from ECL.api.game import GameHandlers
from ECL.api.mods import ModHandlers
from ECL.api.plugins import PluginHandlers
from ECL.api.settings import SettingsHandlers
from ECL.api.system import SystemHandlers
from ECL.api.themes import ThemeHandlers
from ECL.api.windows import WindowHandlers
from ECL.api.workspace import WorkspaceHandlers


class FrontendApi(
    ConnectorHandlers,
    WorkspaceHandlers,
    PluginHandlers,
    ModHandlers,
    FileHandlers,
    AccountHandlers,
    GameHandlers,
    SettingsHandlers,
    SystemHandlers,
    ThemeHandlers,
    WindowHandlers,
):
    """
    聚合正式 IPC 域处理器，并共享唯一的前端事件桥接状态。

    该门面只供 PyTauri 适配器注册命令；业务逻辑仍由应用上下文中的服务负责。
    """


__all__ = [
    "FrontendApi",
    "_Emitter",
    "_FrontendState",
    "_guess_image_extension",
    "_mime_to_ext",
    "_normalize_image_url",
]
