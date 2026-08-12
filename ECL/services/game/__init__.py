from .base import GameServiceError, VersionScanError
from .catalog import CatalogCoordinator
from .install import InstallCoordinator
from .launch import LaunchCoordinator
from .mods import ModCoordinator
from .scan import ScanCoordinator


class GameService(ModCoordinator, LaunchCoordinator, InstallCoordinator, ScanCoordinator, CatalogCoordinator):
    """
    Thin public fa?ade composed from focused game coordinators.
    """


__all__ = ["GameService", "GameServiceError", "VersionScanError"]
