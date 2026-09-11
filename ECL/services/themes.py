# ============================================================
# EuoraCraft Launcher
# ECLTeam © 2026 GPL-3.0 License
# https://github.com/ECLTeam/EuoraCraft-Launcher
#
# 文件作用：内置主题标识。前端根据 ui.theme.theme_id 应用皮肤，无需后端服务。
#
# 公开接口：
#   - BUILTIN_THEME_IDS（tuple）
#   - normalize_theme_id(value) -> str
# ============================================================

"""内置主题标识。前端根据 ui.theme.theme_id 应用皮肤，无需后端服务。"""

BUILTIN_THEME_IDS = ("classic", "folia")


def normalize_theme_id(value: object) -> str:
    return value if value in BUILTIN_THEME_IDS else "classic"


__all__ = ["BUILTIN_THEME_IDS", "normalize_theme_id"]
