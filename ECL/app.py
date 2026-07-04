import sys

from .adapters.adapter import run_app
from .launcher import EuoraCraftLauncher


def main() -> int:
    launcher = EuoraCraftLauncher()
    if not launcher.init_launcher():
        return 1
    return run_app(launcher)


if __name__ == "__main__":
    sys.exit(main())
