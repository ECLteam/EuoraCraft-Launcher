from __future__ import annotations

import json
from contextlib import suppress
from copy import deepcopy
from pathlib import Path
from typing import Any

from ECL.events import EventBus
from ECL.utils.errors import ConfigError, ConfigValidationError
from ECL.utils.files import atomic_write_text
from ECL.utils.logging import get_logger

default_config: dict[str, Any] = {
    "launcher": {"debug": False, "disable_ssl_verify": False},
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
        "last_manage_path": "",
    },
    "download": {"mirror_source": "official"},
    "ui": {
        "locale": "zh-CN",
        "theme": {
            "mode": "system",
            "primary_color": "#6f8cff",
            "blur_amount": 18,
            "sidebar_collapsed": True,
            "navigation_mode": "sidebar",
            "titlebar_hidden": False,
            "transparent_bg": False,
            "background_opacity": 1.0,
        },
        "background": {"type": "default", "path": "", "opacity": 1.0, "blur": 18},
    },
}


class ConfigStore:
    """
    以 JSON 文件为载体的启动器配置存储，归应用上下文所有。

    负责配置的读写、默认值填充与校验，并以事件总线向其他组件广播配置变更。
    """

    def __init__(self, data_path: Path, event_bus: EventBus | None = None) -> None:
        self.logger = get_logger("config")
        self.data_path = Path(data_path)
        self.config_path = self.data_path / "setting.json"
        self.config_data: dict[str, Any] | None = None
        self.events = event_bus or EventBus()

    @property
    def default_minecraft_path(self) -> Path:
        """
        获取默认 Minecraft 目录。
        :return: 默认 Minecraft 目录
        """
        return (self.data_path.parent / ".minecraft").resolve()

    def _create_default_config(self) -> dict[str, Any]:
        """深拷贝默认配置并填充 Minecraft 路径。"""
        config_data = deepcopy(default_config)
        self._ensure_default_minecraft_path(config_data)
        return config_data

    def _ensure_default_minecraft_path(self, config_data: dict[str, Any]) -> bool:
        """未配置 Minecraft 路径时创建默认目录并回填相关字段，返回是否产生变更。"""
        game_config = config_data.get("game")
        if not isinstance(game_config, dict):
            return False
        minecraft_paths = game_config.get("minecraft_paths")
        if isinstance(minecraft_paths, list) and minecraft_paths:
            return False
        minecraft_path = self.default_minecraft_path
        minecraft_path.mkdir(parents=True, exist_ok=True)
        game_config["minecraft_paths"] = [{"name": "默认路径", "path": str(minecraft_path)}]
        if not game_config.get("last_install_path"):
            game_config["last_install_path"] = str(minecraft_path)
        if not game_config.get("last_manage_path"):
            game_config["last_manage_path"] = str(minecraft_path)
        return True

    def _initialize_file(self) -> None:
        """创建数据目录，并用默认配置初始化缺失的配置文件。"""
        self.data_path.mkdir(parents=True, exist_ok=True)
        if self.config_path.exists():
            return
        self.logger.info("配置文件不存在，正在创建: %s", self.config_path)
        self._write_config(self._create_default_config())

    def _write_config(self, config_data: dict[str, Any]) -> None:
        """以原子替换方式写入配置，失败时抛 ConfigError。"""
        try:
            serialized_config = json.dumps(config_data, ensure_ascii=False, indent=4)
            atomic_write_text(self.config_path, serialized_config)
        except (OSError, TypeError, ValueError) as exc:
            raise ConfigError(f"写入配置文件失败: {self.config_path}") from exc
        self.config_data = deepcopy(config_data)

    def _load_config(self) -> dict[str, Any]:
        """从磁盘加载配置，必要时回写默认路径或恢复损坏的配置。"""
        try:
            self._initialize_file()
            loaded = json.loads(self.config_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("配置文件根节点必须是对象")
            if self._ensure_default_minecraft_path(loaded):
                self._write_config(loaded)
            return loaded
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            return self._restore_default_config(exc)

    def _restore_default_config(self, cause: Exception) -> dict[str, Any]:
        """备份损坏配置并恢复为默认配置。"""
        backup_path = self.config_path.with_suffix(".json.bak")
        self.logger.warning("配置文件无效，将恢复默认配置: %s", cause)
        with suppress(OSError):
            self.config_path.replace(backup_path)
        restored = self._create_default_config()
        self._write_config(restored)
        self.logger.info("已恢复默认配置，原配置备份路径: %s", backup_path)
        return restored

    def get_config(self, section: str | None = None) -> Any:
        """
        获取配置数据
        :param section: 配置分区，为 None 时返回全部配置
        :return: 配置数据
        """
        if self.config_data is None:
            self.config_data = self._load_config()
        if section is None:
            return deepcopy(self.config_data)
        return deepcopy(self.config_data.get(section))

    def list_sections(self) -> list[str]:
        """
        获取全部配置分区名称
        :return: 配置分区名称列表
        """
        return list(self.get_config())

    def get_many(self, sections: list[str]) -> dict[str, Any]:
        """
        批量获取配置分区
        :param sections: 配置分区名称列表
        :return: 配置分区及其数据
        """
        config_data = self.get_config()
        return {section: config_data.get(section) for section in dict.fromkeys(sections)}

    def save_config(self, section: str, data: Any) -> None:
        """
        保存配置分区
        :param section: 配置分区名称
        :param data: 配置数据
        """
        if not isinstance(section, str) or not section.strip():
            raise ConfigValidationError("配置分区名称不能为空")
        normalized_section = section.strip()
        config_data = self.get_config()
        config_data[normalized_section] = deepcopy(data)
        self._write_config(config_data)
        # 广播配置变更事件，通知订阅组件。
        self.events.emit("config:updated", normalized_section, deepcopy(data))


# 为迁移期调用方保留的兼容名称。
ConfigManager = ConfigStore
