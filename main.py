# ============================================================
# EuoraCraft Launcher
# ECLTeam © 2026 GPL-3.0 License
# https://github.com/ECLTeam/EuoraCraft-Launcher
#
# 文件作用：进程入口：初始化运行环境并启动 EuoraCraft 启动器。
#
# 公开接口：
#   - run_launcher() -> int
# ============================================================

import sys

from ECL.launcher import EuoraCraftLauncher


def run_launcher() -> int:
    return int(EuoraCraftLauncher().run())

if __name__ == "__main__":
    sys.exit(run_launcher())
