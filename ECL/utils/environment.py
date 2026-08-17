import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from ECL.utils.logging import get_logger


class Environment:
    """
    面向组合根的环境变量读取器，路径一经创建即固定不变。
    """

    def __init__(self, app_path: Path) -> None:
        """记录应用路径并准备 .env 文件与环境变量缓存。"""
        self.logger = get_logger("EnvManager")
        self.app_path = Path(app_path)
        self.env_path = self.app_path / ".env"
        self.env_data: dict[str, str | None] | None = None

    def get_env(self) -> dict[str, str | None]:
        """
        获取环境变量。
        """
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
        """
        读取环境变量。

        :param default: 字段缺失时采用的默认值
        :param keys: 需要批量读取的配置键
        """
        env_data = self.get_env()
        for key in keys:
            value = env_data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return default

    def _convert_env_value(self, value: str) -> bool | int | float | str:
        """将环境变量字符串转换为布尔、整数、浮点数或原字符串。"""
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
        """
        使用环境变量覆盖配置。

        :param config: 游戏或启动器配置数据
        """
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


EnvManager = Environment
