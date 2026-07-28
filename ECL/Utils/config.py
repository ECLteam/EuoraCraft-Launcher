import json
from contextlib import suppress
from copy import deepcopy
from pathlib import Path
from typing import Any

from ECL.Utils.logger import get_logger

default_config = {
    "launcher": {
        "debug": False,
    },
    "game": {
        "minecraft_paths": [],
        "java_auto": True,
        "java_path": "",
        "memory_auto": True,
        "memory_size": 4096,
        "game_width": 854,
        "game_height": 480,
        "jvm_args": [],
        "fullscreen": False,
        "last_install_path": "",
    },
    "download": {
        "mirror_source": "official",
        "download_threads": 16,
    },
    "ui": {
        "locale": "zh-CN",
        "theme": {
            "mode": "system",
            "primary_color": "#6f8cff",
            "blur_amount": 18,
            "sidebar_collapsed": False,
            "navigation_mode": "sidebar",
            "titlebar_hidden": False,
            "transparent_bg": False,
            "background_opacity": 0.16,
        },
        "background": {
            "type": "default",
            "path": "",
            "opacity": 0.16,
            "blur": 18,
        },
    },
    "version_settings": {},
}


class ConfigManager:
    """JSON 配置文件管理器，支持读写、分区操作和写入"""

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, data_path: Path | None = None):
        if self._initialized:
            return
        self.logger = get_logger("config")
        self.data_path: Path = Path(data_path)
        self.config_path: Path = self.data_path / "setting.json"
        self._initialized: bool = True
        self.config_data: dict[str, Any] | None = None

    def _config_init(self) -> bool:
        """
        初始化配置文件目录和默认配置文件
        :return: 初始化是否成功
        """
        try:
            self.data_path.mkdir(parents=True, exist_ok=True)
            if not self.config_path.exists():
                self.logger.info(f"配置文件不存在，正在创建: {self.config_path}")
                self.config_path.write_text(
                    json.dumps(default_config, ensure_ascii=False, indent=4),
                    encoding="utf-8",
                )
                self.logger.info("已创建默认配置文件")
            return True
        except OSError as exc:
            self.logger.error(f"初始化配置文件失败: {exc}")
            return False

    def _write_config(self, config_data: dict[str, Any]) -> bool:
        """
        原子写入配置到文件
        :param config_data: 待写入的配置数据
        :return: 写入是否成功
        """
        temporary_path = self.config_path.with_suffix(".json.tmp")
        try:
            serialized_config = json.dumps(config_data, ensure_ascii=False, indent=4)
            self.data_path.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(serialized_config, encoding="utf-8")
            temporary_path.replace(self.config_path)
            self.config_data = deepcopy(config_data)
            return True
        except (OSError, TypeError, ValueError) as exc:
            self.logger.error(f"写入配置文件失败: {exc}")
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)
            return False

    def get_config(self, section: str | None = None) -> Any:
        """
        获取配置数据
        :param section: 可选，指定配置分区名称；为 None 时返回全部配置
        :return: 配置数据或指定分区的配置数据
        """
        if self.config_data is None:
            if self._config_init():
                try:
                    loaded_config = json.loads(self.config_path.read_text(encoding="utf-8"))
                    if not isinstance(loaded_config, dict):
                        raise ValueError("配置文件根节点必须是对象")
                    self.config_data = loaded_config
                except (OSError, json.JSONDecodeError, ValueError) as exc:
                    backup_path = self.config_path.with_suffix(".json.bak")
                    self.logger.warning(f"配置文件无效，将恢复默认配置: {exc}")
                    with suppress(OSError):
                        self.config_path.replace(backup_path)
                    self.config_data = deepcopy(default_config)
                    if self._write_config(self.config_data):
                        self.logger.info(f"已恢复默认配置，原配置备份路径: {backup_path}")
            else:
                self.config_data = deepcopy(default_config)
        if section is None:
            return deepcopy(self.config_data)
        return deepcopy(self.config_data.get(section))

    def list_sections(self) -> list[str]:
        """
        获取全部配置分区名称
        :return: 配置分区名称列表
        """
        return list(self.get_config().keys())

    def get_many(self, sections: list[str]) -> dict[str, Any]:
        """
        批量获取指定配置分区
        :param sections: 配置分区名称列表
        :return: 分区名到配置数据的映射
        """
        config_data = self.get_config()
        return {section: config_data.get(section) for section in dict.fromkeys(sections)}

    def save_config(self, section: str, data: Any) -> bool:
        """
        保存指定配置分区
        :param section: 配置分区名称
        :param data: 待保存的配置数据
        :return: 保存是否成功
        """
        if not isinstance(section, str) or not section.strip():
            self.logger.error("配置分区名称不能为空")
            return False
        config_data = self.get_config()
        config_data[section] = data
        if self._write_config(config_data):
            self.logger.info(f"配置分区已保存: {section}")
            return True
        return False