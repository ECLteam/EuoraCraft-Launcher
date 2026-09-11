# ============================================================
# EuoraCraft Launcher
# ECLTeam © 2026 GPL-3.0 License
# https://github.com/ECLTeam/EuoraCraft-Launcher
#
# 文件作用：插件运行框架：读取 plugin.json、装配权限与管理器并托管生命周期。
# ============================================================

from ECL.plugins.manager import PluginAction, PluginActionResult, PluginCommandError, PluginManager

__all__ = ["PluginAction", "PluginActionResult", "PluginCommandError", "PluginManager"]
