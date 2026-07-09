# ------------------------------
# EuoraCraft Launcher 主程序
# ECLTeam © 2026 GNU General Public License v3.0
# https://github.com/ECLTeam/EuoraCraft-Launcher
# ------------------------------

import sys

from ECL.app import main


def run_launch() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(run_launch())
