import json
from pathlib import Path

from ECL.Utils.logger import get_logger

default_config = {
    "launcher": {
        "debug": False,
    }
}

class ConfigManager:
    _instance = None
    _initialized = False

    def __new__(cls, data_path=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, data_path=None):
        if self._initialized:
            return

        self.logger = get_logger("config")
        self.data_path: Path = Path(data_path)
        self.config_path: Path = self.data_path / "setting.json"
        self._initialized: bool = True
        self.config_data: dict = None

    def _config_init(self) -> bool:
        self.data_path.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            self.logger.info(f"配置文件不存在，正在创建: {self.config_path}")
            self.config_path.write_text(json.dumps(default_config, indent=4), encoding="utf-8")
            self.logger.info("已创建默认配置文件")
            return True
        return True

    def get_config(self) -> dict:
        """获取配置"""
        if self.config_data is None: # 判断是否已经获取过配置
            if self._config_init():
                try:
                    self.config_data = json.loads(self.config_path.read_text(encoding="utf-8"))
                    return self.config_data
                except json.JSONDecodeError:
                    try:
                        self.config_path.replace(self.config_path / "setting.json.bak")
                        self.logger.warning("配置文件无效，已自动重新生成，旧配置文件已备份")
                    except Exception:
                        self.logger.info("重命名失败，请手动移除配置文件")
                        return default_config
                    return default_config
            return default_config
        return self.config_data
