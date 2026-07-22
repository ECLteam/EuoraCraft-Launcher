# ------------------------------
# EuoraCraft Launcher
# ECLTeam © 2026 GPL-3.0 License
# https://github.com/ECLTeam/EuoraCraft-Launcher
# ------------------------------

import sys

from ECL.lunacher import EuoraCraftLauncher

def run_launcher() -> bool:
    launcher = EuoraCraftLauncher()
    return launcher.main_run()

if __name__ == "__main__":
    if not run_launcher():
        sys.exit(1)
