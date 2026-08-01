import sys
import tomllib
from pathlib import Path


def get_runtime_info() -> dict:
    """
    获取当前运行环境信息
    :return: 环境信息字典
        - is_frozen: bool，是否为打包环境；True=打包，False=开发源码运行
        - app_path: Path，可执行程序所在目录；开发环境下为项目根目录
        - resource_path: Path，打包资源解压目录；开发环境下与 app_path 相同
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
    读取 pyproject.toml 配置数据
    :param app_path: 程序根目录路径
    :return: pyproject.toml 解析后的字典，读取失败时返回 None
    此方法不推荐使用
    """
    open_path = Path(app_path / "pyproject.toml")
    try:
        with open_path.open(encoding="utf-8") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None
