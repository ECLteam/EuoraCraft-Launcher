# ============================================================
# EuoraCraft Launcher
# ECLTeam © 2026 GPL-3.0 License
# https://github.com/ECLTeam/EuoraCraft-Launcher
#
# 文件作用：通用基础包。
# ============================================================

from ECL.common.build_env import CURSEFORGE_API_KEY, MICROSOFT_CLIENT_ID
from ECL.common.runtime import get_pyproject_data, get_runtime_info
from ECL.common.version import __version__, __version_type__

__all__ = [
    "CURSEFORGE_API_KEY",
    "MICROSOFT_CLIENT_ID",
    "__version__",
    "__version_type__",
    "get_pyproject_data",
    "get_runtime_info",
]
