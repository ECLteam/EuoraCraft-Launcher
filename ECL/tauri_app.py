import sys

from .adapters.tauri import run_tauri_app
from .launcher import EuoraCraftLauncher


def main() -> int:
    launcher = EuoraCraftLauncher()
    if not launcher.init_launcher():
        return 1
    return run_tauri_app(launcher)


if __name__ == "__main__":
    sys.exit(main())
