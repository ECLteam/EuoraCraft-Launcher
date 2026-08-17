from .base import GameServiceError, VersionScanError
from .catalog import CatalogCoordinator
from .install import InstallCoordinator
from .launch import LaunchCoordinator
from .mods import ModCoordinator
from .profiles import ProfileCoordinator
from .resources import ResourceCoordinator
from .scan import ScanCoordinator
from .screenshots import ScreenshotCoordinator
from .servers import ServerCoordinator
from .workspace import WorkspaceCoordinator
from .worlds import WorldCoordinator


class GameService(
    ProfileCoordinator,
    WorkspaceCoordinator,
    WorldCoordinator,
    ScreenshotCoordinator,
    ServerCoordinator,
    ResourceCoordinator,
    ModCoordinator,
    LaunchCoordinator,
    InstallCoordinator,
    ScanCoordinator,
    CatalogCoordinator,
):
    """
    面向 IPC 边界公开的统一游戏服务门面。

    通过多重继承聚合各领域协调器，将实例、安装、启动、扫描与资源管理的
    能力合并为单一的 ``GameService`` 入口，内部共享基类 ``_GameState``
    提供的运行状态与依赖。
    """


__all__ = ["GameService", "GameServiceError", "VersionScanError"]
