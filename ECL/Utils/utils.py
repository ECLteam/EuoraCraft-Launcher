import sys
import tomllib
from pathlib import Path


def get_runtime_info() -> dict:
    """
    获取当前运行环境信息
    :return: 环境信息字典
        - is_frozen: bool，是否为打包环境；True=打包，False=开发源码运行
        - app_path: Path，程序根目录路径对象
    """
    is_frozen = bool(getattr(sys, "frozen", False))
    app_path = Path(sys.argv[0]).resolve().parent if is_frozen else Path(__file__).resolve().parent.parent.parent
    return {
        "is_frozen": is_frozen,
        "app_path": app_path,
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
