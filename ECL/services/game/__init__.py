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
    Thin public fa?ade composed from focused game coordinators.
    """


__all__ = ["GameService", "GameServiceError", "VersionScanError"]
