import sys

from ECL.tauri_app import main as tauri_main


def main() -> int:
    return tauri_main()


if __name__ == "__main__":
    sys.exit(main())
