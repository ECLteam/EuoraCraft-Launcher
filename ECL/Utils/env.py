import os
from pathlib import Path

from dotenv import dotenv_values

from ECL.Utils.logger import get_logger


class EnvManager:
    _instance = None
    _initialized = False

    def __new__(cls, data_path=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, app_path=None):
        if self._initialized:
            return

        self.logger = get_logger("EnvManager")
        self.env_path: Path = Path(app_path / ".env")
        self.env_data: dict = None
        self._initialized: bool = True
        self.app_path: Path = Path(app_path)

    def get_env(self) -> dict | None:
        """
        读取环境变量文件的内容
        :return: dict | None
        """
        system_env = {k: v for k, v in os.environ.items() if k.startswith("ECL_")}
        if not self.env_path.exists():
            return None
        if self.env_data is not None:
            return self.env_data
        self.env_data = dotenv_values(self.env_path)
        self.env_data.update(system_env)
        return self.env_data

    def _convert_env_value(self, value: str):
        # 布尔值
        lower = value.lower()
        if lower == "true":
            return True
        if lower == "false":
            return False
        # 整数
        if value.lstrip("-").isdigit():
            return int(value)
        # 浮点数
        try:
            return float(value)
        except ValueError:
            return value

    def config_replace(self, config: dict | None = None) -> dict:
        """
        将环境变量中的配置项替换进config字典中
        环境变量格式: ECL_CONFIG_SECTION_KEY = value
        :param config: 原始配置字典
        :return: 替换后的配置字典
        """
        if config is None:
            return None
        env_data = self.get_env()
        if env_data is None:
            return config
        prefix = "ECL_CONFIG_"
        for env_key, env_value in env_data.items():
            if not env_key.startswith(prefix):
                continue
            cfg_key_path = env_key[len(prefix):]
            key_segments = cfg_key_path.split("_")
            key_segments = [seg.lower() for seg in key_segments]
            current = config
            for i, segment in enumerate(key_segments):
                if i == len(key_segments) - 1:
                    current[segment] = self._convert_env_value(env_value)
                else:
                    if segment not in current or not isinstance(current[segment], dict):
                        current[segment] = {}
                    current = current[segment]
        return config
