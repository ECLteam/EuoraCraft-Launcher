# ============================================================
# EuoraCraft Launcher
# ECLTeam © 2026 GPL-3.0 License
# https://github.com/ECLTeam/EuoraCraft-Launcher
#
# 文件作用：构建期注入的常量：Microsoft Client ID 与 CurseForge API Key。
#
# 公开接口：
#   - MICROSOFT_CLIENT_ID（str）
#   - CURSEFORGE_API_KEY（str）
# ============================================================

MICROSOFT_CLIENT_ID = ""  # Microsoft OAuth 客户端 ID，构建时注入
CURSEFORGE_API_KEY = ""  # CurseForge API Key，构建时注入
