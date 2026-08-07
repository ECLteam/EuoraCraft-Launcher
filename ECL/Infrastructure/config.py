from __future__ import annotations

import json
from contextlib import suppress
from copy import deepcopy
from pathlib import Path
from typing import Any

from ECL.Events import EventBus
from ECL.Infrastructure.logging import get_logger

default_config: dict[str, Any] = {
    "launcher": {"debug": False},
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
    "version_settings": {},
}


class ConfigError(RuntimeError):
    """配置错误。"""


class ConfigValidationError(ConfigError, ValueError):
    """配置参数错误。"""


class ConfigManager:
    """全局配置管理器"""

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, data_path: Path | None = None) -> None:
        if self._initialized:
            return
        if data_path is None:
            raise ValueError("首次创建 ConfigManager 时必须提供 data_path")
        self.logger = get_logger("config")
        self.data_path = Path(data_path)
        self.config_path = self.data_path / "setting.json"
        self.config_data: dict[str, Any] | None = None
        self._initialized = True

    @property
    def default_minecraft_path(self) -> Path:
        """
        获取默认 Minecraft 目录
        :return: 默认 Minecraft 目录
        """
        return (self.data_path.parent / ".minecraft").resolve()

    def _create_default_config(self) -> dict[str, Any]:
        config_data = deepcopy(default_config)
        self._ensure_default_minecraft_path(config_data)
        return config_data

    def _ensure_default_minecraft_path(self, config_data: dict[str, Any]) -> bool:
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
        self.data_path.mkdir(parents=True, exist_ok=True)
        if self.config_path.exists():
            return
        self.logger.info("配置文件不存在，正在创建: %s", self.config_path)
        self._write_config(self._create_default_config())

    def _write_config(self, config_data: dict[str, Any]) -> None:
        temporary_path = self.config_path.with_suffix(".json.tmp")
        try:
            serialized_config = json.dumps(config_data, ensure_ascii=False, indent=4)
            self.data_path.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(serialized_config, encoding="utf-8")
            temporary_path.replace(self.config_path)
        except (OSError, TypeError, ValueError) as exc:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)
            raise ConfigError(f"写入配置文件失败: {self.config_path}") from exc
        self.config_data = deepcopy(config_data)

    def _load_config(self) -> dict[str, Any]:
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
        # self.logger.info(f"配置分区已保存: {section}")
        # 通知其他组件配置已变更
        EventBus().emit("config:updated", normalized_section, deepcopy(data))
