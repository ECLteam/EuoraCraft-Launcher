"""内置主题标识。前端根据 ui.theme.theme_id 应用皮肤，无需后端服务。"""

BUILTIN_THEME_IDS = ("classic", "folia")


def normalize_theme_id(value: object) -> str:
    return value if value in BUILTIN_THEME_IDS else "classic"


__all__ = ["BUILTIN_THEME_IDS", "normalize_theme_id"]
