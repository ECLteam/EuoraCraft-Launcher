import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from ECL.Infrastructure.logging import get_logger


class EnvManager:
    """环境变量管理器"""

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, app_path: Path | None = None) -> None:
        if self._initialized:
            return
        self.logger = get_logger("EnvManager")
        if app_path is None:
            raise ValueError("首次创建 EnvManager 时必须提供 app_path")
        self.app_path = Path(app_path)
        self.env_path = self.app_path / ".env"
        self.env_data: dict[str, str | None] | None = None
        self._initialized: bool = True

    def get_env(self) -> dict[str, str | None]:
        """获取环境变量。"""
        if self.env_data is not None:
            return dict(self.env_data)
        self.env_data = dict(dotenv_values(self.env_path)) if self.env_path.exists() else {}
        self.env_data.update({key: value for key, value in os.environ.items() if key.startswith("ECL_")})
        system_client_id = os.environ.get("MICROSOFT_CLIENT_ID") or os.environ.get("ECL_MICROSOFT_CLIENT_ID")
        if system_client_id:
            self.env_data["MICROSOFT_CLIENT_ID"] = system_client_id
        elif not self.env_data.get("MICROSOFT_CLIENT_ID") and self.env_data.get("ECL_MICROSOFT_CLIENT_ID"):
            self.env_data["MICROSOFT_CLIENT_ID"] = self.env_data["ECL_MICROSOFT_CLIENT_ID"]
        return dict(self.env_data)

    def get_value(self, *keys: str, default: str | None = None) -> str | None:
        """读取环境变量。"""
        env_data = self.get_env()
        for key in keys:
            value = env_data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return default

    def _convert_env_value(self, value: str) -> bool | int | float | str:
        lower = value.lower()
        if lower == "true":
            return True
        if lower == "false":
            return False
        if value.lstrip("-").isdigit():
            return int(value)
        try:
            return float(value)
        except ValueError:
            return value

    def apply_to_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """使用环境变量覆盖配置。"""
        result = deepcopy(config)
        env_data = self.get_env()
        prefix = "ECL_CONFIG_"
        for env_key, env_value in env_data.items():
            if not env_key.startswith(prefix) or env_value is None:
                continue
            cfg_key_path = env_key[len(prefix) :]
            key_segments = cfg_key_path.split("_")
            key_segments = [seg.lower() for seg in key_segments]
            current = result
            for i, segment in enumerate(key_segments):
                if i == len(key_segments) - 1:
                    current[segment] = self._convert_env_value(env_value)
                else:
                    if segment not in current or not isinstance(current[segment], dict):
                        current[segment] = {}
                    current = current[segment]
        return result
