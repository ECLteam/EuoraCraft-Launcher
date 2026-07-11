import os
import sys
from functools import cached_property
from pathlib import Path

from .logger import get_logger

logger = get_logger("env")


def is_frozen():
    return getattr(sys, "frozen", False)


def is_dev():
    return not is_frozen()


def get_app_dir():
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", "."))
    return Path.cwd()


def get_runtime_dir():
    if is_frozen():
        return Path(sys.executable).parent
    return Path.cwd()


class EnvLoader:
    def __init__(self, env_paths=None):
        self.__env_paths = env_paths or [".env.dev", ".env"]

    @cached_property
    def _env_dict(self):
        merged = {}
        search_dirs = [Path.cwd()]
        if is_frozen():
            search_dirs.append(get_runtime_dir())
        for name in self.__env_paths:
            for base in search_dirs:
                path = (base / name).resolve()
                if not path.exists():
                    continue
                logger.debug(f"加载环境文件: {path}")
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
                                merged[key] = value
                except OSError as e:
                    logger.error(f"读取环境文件失败 {path}: {e}")
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
        if value.lstrip("-").isdigit():
            return int(value)
        logger.warning(f"环境变量 {key} 的值 '{value}' 无法解析为整数，使用默认值 {default}")
        return default


def convert_env_value(raw, target):
    if isinstance(target, bool):
        return raw.lower() in ("true", "1", "yes", "on")
    if isinstance(target, int):
        if raw.lstrip("-").isdigit():
            return int(raw)
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
