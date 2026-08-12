import sys
import tomllib
from pathlib import Path
from typing import TypedDict


class RuntimeInfo(TypedDict):
    """
    运行环境信息。
    """

    is_frozen: bool
    app_path: Path
    resource_path: Path


def get_runtime_info() -> RuntimeInfo:
    """
    获取运行环境信息。

    """
    is_frozen = bool(getattr(sys, "frozen", False))
    if is_frozen:
        app_path = Path(sys.executable).resolve().parent
        resource_path = Path(getattr(sys, "_MEIPASS", app_path)).resolve()
    else:
        app_path = Path(__file__).resolve().parent.parent.parent
        resource_path = app_path
    return {
        "is_frozen": is_frozen,
        "app_path": app_path,
        "resource_path": resource_path,
    }


def get_pyproject_data(app_path: Path) -> dict | None:
    """
    读取 pyproject.toml。

    :param app_path: 启动器运行目录
    """
    open_path = Path(app_path / "pyproject.toml")
    try:
        with open_path.open(encoding="utf-8") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None
