# ECL.Game.Core - 游戏核心模块

from .C_Downloader import Downloader
from .C_FilesChecker import FilesChecker
from .C_GetGames import GetGames
from .C_Libs import (
    ApiUrl,
    find_version,
    is_uuid3,
    name_to_path,
    name_to_uuid,
    replace_last,
    unzip,
)
from .C_Skin import download_skin, get_avatar_data_url, get_skin_address, get_skin_sex
from .ECLauncherCore import ECLauncherCore
from .InstancesManager import InstancesManager

__all__ = [
    "ApiUrl",
    "Downloader",
    "ECLauncherCore",
    "FilesChecker",
    "GetGames",
    "InstancesManager",
    "download_skin",
    "find_version",
    "get_avatar_data_url",
    "get_skin_address",
    "get_skin_sex",
    "is_uuid3",
    "name_to_path",
    "name_to_uuid",
    "replace_last",
    "unzip",
]
