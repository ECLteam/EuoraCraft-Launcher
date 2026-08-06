# ------------------------------
# EuoraCraft Launcher
# ECLTeam © 2026 GPL-3.0 License
# https://github.com/ECLTeam/EuoraCraft-Launcher
# ------------------------------

import sys

from ECL.launcher import EuoraCraftLauncher


def run_launcher() -> int:
    return int(EuoraCraftLauncher().run())

if __name__ == "__main__":
    sys.exit(run_launcher())
