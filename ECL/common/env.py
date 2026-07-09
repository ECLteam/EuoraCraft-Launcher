import os
import sys
from functools import cached_property
from pathlib import Path

from .logger import get_logger

logger = get_logger("env")


def is_frozen() -> bool:
    # 检测是否为 PyInstaller 打包环境
    return getattr(sys, "frozen", False)


def is_dev() -> bool:
    # 检测是否为开发环境（未打包运行）
    return not is_frozen()


def get_app_dir() -> Path:
    # 获取应用根目录
    # 打包环境：返回 _MEIPASS（PyInstaller 临时解压目录）
    # 开发环境：返回当前工作目录
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", "."))
    return Path.cwd()


def get_runtime_dir() -> Path:
    # 获取运行时目录（可写数据的目录）
    # 打包环境：返回 exe 所在目录（用户安装目录）
    # 开发环境：返回当前工作目录
    if is_frozen():
        return Path(sys.executable).parent
    return Path.cwd()


class EnvLoader:
    def __init__(self, env_paths=None):
        self.__env_paths = env_paths or [".env.dev", ".env"]

    @cached_property
    def _env_dict(self):
        merged = {}
        # 打包模式下额外检查 exe 所在目录（runtime_dir），确保构建时注入的 .env 可被读取
        search_dirs = [Path.cwd()]
        if is_frozen():
            search_dirs.append(get_runtime_dir())
        for name in self.__env_paths:
            for base in search_dirs:
                path = (base / name).resolve()
                if path.exists():
                    logger.debug(f"加载环境文件: {path}")
                    merged.update(_parse_env_file(path))
                    break
        for key, value in os.environ.items():
            merged[key] = value
        return merged

    @property
    def env(self):
        return self._env_dict

    def get(self, key, default=None):
        return self.env.get(key, default)

    def get_bool(self, key, default=False):
        value = self.get(key)
        if value is None:
            return default
        return value.lower() in ("true", "1", "yes", "on")

    def get_int(self, key, default=0):
        value = self.get(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            logger.warning(f"环境变量 {key} 的值 '{value}' 无法解析为整数，使用默认值 {default}")
            return default


def _parse_env_file(path):
    result = {}
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    result[key] = value
    except OSError as e:
        logger.error(f"读取环境文件失败 {path}: {e}")
    return result


def convert_env_value(raw, target):
    # 根据目标值的类型，将字符串环境变量转换为目标类型
    if isinstance(target, bool):
        return raw.lower() in ("true", "1", "yes", "on")
    if isinstance(target, int):
        try:
            return int(raw)
        except ValueError:
            return target
    if isinstance(target, float):
        try:
            return float(raw)
        except ValueError:
            return target
    return raw


def singleton(cls):
    _instances = {}
    _lock = __import__("threading").Lock()

    def wrapper(*args, **kwargs):
        with _lock:
            if cls not in _instances:
                _instances[cls] = cls(*args, **kwargs)
        return _instances[cls]

    return wrapper


@singleton
class GlobalEnv(EnvLoader):
    pass

_default_loader = None


def get_env_loader():
    global _default_loader
    if _default_loader is None:
        _default_loader = GlobalEnv()
    return _default_loader
