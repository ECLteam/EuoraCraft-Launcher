import copy
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .env import EnvLoader, convert_env_value, get_env_loader
from .logger import get_logger
from .version import __version__, __version_type__

logger = get_logger("config")


class ConfigManager:
    DEFAULT_CONFIG = [
        {
            "launcher": {"version": __version__, "version_type": __version_type__, "debug": False},
            "ui": {
                "width": 900,
                "height": 600,
                "title": "EuoraCraft Launcher",
                "locale": "zh-CN",
                "background": {"type": "default", "path": "", "opacity": 0.2, "blur": 0},
                "theme": {"mode": "system", "primary_color": "#4A7FD9", "blur_amount": 6, "sidebar_collapsed": True, "titlebar_hidden": True},
                "mouse_effect": {"enabled": False, "color": "45,175,255", "scale": 1.5, "opacity": 1.0, "speed": 1.0},
            },
            "game": {
                "minecraft_paths": ["./.minecraft"],
                "java_auto": True,
                "java_path": "",
                "memory_auto": True,
                "memory_size": 4096,
            },
            "download": {"mirror_source": "official", "download_threads": 4},
        }
    ]

    def __init__(self, config_path: str = "setting.json"):
        self._config_path = Path(config_path).resolve()
        self.config: list[dict[str, Any]] = []
        self._instances: list[dict[str, Any]] = []
        self._env_loader = get_env_loader()
        self.load()
        logger.info("配置管理器初始化完成")

    @property
    def config_path(self) -> Path:
        return self._config_path

    @property
    def ui(self) -> dict[str, Any]:
        return self.config[0].get("ui", {}) if self.config else {}

    def _apply_env_overrides(self, config: list[dict[str, Any]]) -> None:
        env = self._env_loader.env
        if not env or not config:
            return

        for env_key, env_val in env.items():
            if not env_key.startswith("ECL_"):
                continue

            parts = env_key.split("_")
            if len(parts) < 3:
                continue

            section = parts[1].lower()
            key = "_".join(parts[2:]).lower()

            if section not in config[0] or key not in config[0][section]:
                continue

            original_val = config[0][section][key]
            config[0][section][key] = convert_env_value(env_val, original_val)
            logger.info(f"环境变量覆盖配置: [{section}][{key}]")

    def _get_default_config(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self.DEFAULT_CONFIG)

    def _auto_complete_missing_config(self) -> None:
        if not self.config or not isinstance(self.config, list) or len(self.config) == 0:
            logger.warning("配置为空，使用默认配置")
            self.config = self._get_default_config()
            return

        default_config = self.DEFAULT_CONFIG[0]
        current_config = self.config[0]

        config_updated = False

        for section, default_section_config in default_config.items():
            if section not in current_config:
                logger.info(f"补全缺失的配置项: {section}")
                current_config[section] = copy.deepcopy(default_section_config)
                config_updated = True
            else:
                if isinstance(default_section_config, dict) and isinstance(current_config[section], dict):
                    for key, default_value in default_section_config.items():
                        if key not in current_config[section]:
                            logger.info(f"补全缺失的配置项: {section}.{key}")
                            current_config[section][key] = default_value
                            config_updated = True

        # 始终以 version.py 为版本权威来源，每次启动同步到 setting.json
        launcher_cfg = current_config.get("launcher", {})
        if launcher_cfg.get("version") != __version__ or launcher_cfg.get("version_type") != __version_type__:
            launcher_cfg["version"] = __version__
            launcher_cfg["version_type"] = __version_type__
            current_config["launcher"] = launcher_cfg
            config_updated = True
            logger.info(f"版本号已同步至配置文件: v{__version__} ({__version_type__})")

        if config_updated:
            logger.info("检测到配置变更，已自动更新")
            self.save(self.config)

    def _migrate_game_paths(self) -> None:
        # 将旧的相对路径 ./ .minecraft 迁移为绝对路径
        game_config = self.config[0].get("game", {})
        paths = game_config.get("minecraft_paths", [])
        default_abs = self._get_default_minecraft_path()
        needs_save = False
        for p in paths:
            if not isinstance(p, dict):
                continue
            path_str = p.get("path", "")
            if path_str in ("./.minecraft", ".minecraft"):
                p["path"] = default_abs
                needs_save = True
        if needs_save:
            logger.info(f"已将相对路径迁移为绝对路径: {default_abs}")
            self.save(self.config)

    def load(self) -> list[dict[str, Any]]:
        if not self.config_path.exists():
            logger.warning("配置文件不存在，正在生成默认配置...")
            self.config = self._get_default_config()
            self.save(self.config)
            logger.info(f"默认配置文件已生成：{self.config_path}")
        else:
            try:
                with self.config_path.open(encoding="utf-8") as f:
                    self.config = json.load(f)
                logger.info("配置文件读取完成")
                self._auto_complete_missing_config()
                self._migrate_game_paths()
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"读取配置文件失败: {e}")
                raise
        self._apply_env_overrides(self.config)
        return self.config

    def save(self, config: list[dict[str, Any]]) -> None:
        try:
            safe_config = self._make_config_safe_for_json(config)
            with self.config_path.open("w", encoding="utf-8") as f:
                json.dump(safe_config, f, ensure_ascii=False, indent=2)
            logger.debug(f"配置已保存到: {self.config_path}")
        except OSError as e:
            logger.error(f"保存配置文件失败: {e}")
            raise

    def _make_config_safe_for_json(self, obj: Any) -> Any:
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, dict):
            return {k: self._make_config_safe_for_json(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._make_config_safe_for_json(item) for item in obj]
        return obj

    def validate(self) -> str | None:
        if not self.config or not isinstance(self.config, list) or len(self.config) == 0:
            return "配置结构错误：配置应为非空列表"

        launcher_cfg = self.config[0].get("launcher", {})
        version = launcher_cfg.get("version")
        if not version or not re.match(r"^\d+\.\d+\.\d+$", version):
            return f"版本号格式错误: '{version}'，应为数字.数字.数字（如 1.0.0）"

        return None

    def get_launcher_config(self) -> dict[str, Any]:
        return self.config[0].get("launcher", {}) if self.config else {}

    def get_ui_config(self) -> dict[str, Any]:
        return self.ui

    def get_locale_config(self) -> dict[str, str]:
        return {"locale": self.ui.get("locale", "zh-CN")}

    def _ensure_ui_section(self) -> dict[str, Any]:
        if not self.config:
            self.config = self._get_default_config()
        if "ui" not in self.config[0]:
            self.config[0]["ui"] = {}
        return self.config[0]["ui"]

    def update_locale_config(self, locale: str) -> None:
        ui = self._ensure_ui_section()
        ui["locale"] = locale
        self.save(self.config)
        logger.info(f"语言配置已更新: {locale}")

    def get_background_config(self) -> dict[str, Any]:
        return self.ui.get("background", {"type": "default", "path": "", "opacity": 0.2, "blur": 0})

    def update_background_config(self, background_config: dict[str, Any]) -> None:
        ui = self._ensure_ui_section()
        ui["background"] = background_config
        self.save(self.config)
        logger.info(f"背景图配置已更新: {background_config.get('type', 'unknown')}")

    def _resolve_game_path(self, path: str) -> Path:
        path_obj = Path(path)
        if not path_obj.is_absolute():
            path_obj = Path.cwd() / path_obj
        return path_obj.resolve()

    def _init_single_path(self, path: str) -> None:
        path_obj = self._resolve_game_path(path)
        if path_obj.exists():
            return
        try:
            (path_obj / "versions").mkdir(parents=True, exist_ok=True)
            (path_obj / "assets").mkdir(exist_ok=True)
            (path_obj / "libraries").mkdir(exist_ok=True)
            logger.info(f"新游戏目录已创建: {path_obj}")
        except (OSError, PermissionError) as e:
            logger.error(f"创建游戏目录失败 {path}: {e}")

    def init_game_paths(self) -> None:
        game_config = self.config[0].get("game", {})
        paths = game_config.get("minecraft_paths", ["./.minecraft"])
        for path in paths:
            if isinstance(path, dict):
                path = path.get("path", "./.minecraft")
            self._init_single_path(path)

    def check_game_paths_exist(self) -> list[dict[str, Any]]:
        game_config = self.config[0].get("game", {})
        paths = game_config.get("minecraft_paths", ["./.minecraft"])
        results = []
        for p in paths:
            if isinstance(p, dict):
                path_str = p.get("path", "./.minecraft")
                name = p.get("name", "未命名路径")
            else:
                path_str = p
                name = "默认路径"
            resolved_path = self._resolve_game_path(path_str)
            results.append(
                {"name": name, "path": str(resolved_path), "raw_path": path_str, "exists": resolved_path.exists()}
            )
        return results

    def get_game_config(self, auto_init: bool = False) -> dict[str, Any]:
        game_config = self.config[0].get("game", {"minecraft_paths": ["./.minecraft"]})
        if "minecraft_path" in game_config and "minecraft_paths" not in game_config:
            game_config["minecraft_paths"] = [game_config.pop("minecraft_path")]
        elif "minecraft_paths" not in game_config:
            game_config["minecraft_paths"] = ["./.minecraft"]
        if auto_init:
            self.init_game_paths()
        return game_config

    def _get_default_minecraft_path(self) -> str:
        return str((Path.cwd() / ".minecraft").resolve())

    def _ensure_default_minecraft_path(self, paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
        default_path = self._get_default_minecraft_path()
        for p in paths:
            path_str = p.get("path", "") if isinstance(p, dict) else p
            if path_str not in ("./.minecraft", ".minecraft", default_path):
                continue
            if isinstance(p, dict):
                p["protected"] = True
                p["name"] = "默认路径"
                p["path"] = default_path
            return paths
        paths.insert(0, {"name": "默认路径", "path": default_path, "protected": True})
        return paths

    def update_game_config(self, game_config: dict[str, Any]) -> None:
        if not self.config:
            self.config = self._get_default_config()
        current_game_config = self.config[0].get("game", {})
        updated_config = {**current_game_config, **game_config}
        if "minecraft_path" in updated_config and isinstance(updated_config["minecraft_path"], str):
            updated_config["minecraft_paths"] = [
                {"name": "默认路径", "path": updated_config.pop("minecraft_path"), "protected": True}
            ]
        elif "minecraft_paths" not in updated_config:
            updated_config["minecraft_paths"] = [{"name": "默认路径", "path": "./.minecraft", "protected": True}]
        updated_config["minecraft_paths"] = self._ensure_default_minecraft_path(updated_config["minecraft_paths"])
        old_paths = {
            p.get("path", "") if isinstance(p, dict) else p for p in current_game_config.get("minecraft_paths", [])
        }
        new_paths = [
            p.get("path", "") if isinstance(p, dict) else p
            for p in updated_config["minecraft_paths"]
            if (p.get("path", "") if isinstance(p, dict) else p)
            and (p.get("path", "") if isinstance(p, dict) else p) not in old_paths
        ]
        self.config[0]["game"] = updated_config
        self.save(self.config)
        logger.info("游戏配置已更新")
        for path in new_paths:
            self._init_single_path(path)

    def get_theme_config(self) -> dict[str, Any]:
        return self.ui.get("theme", {"mode": "system", "primary_color": "#4A7FD9", "blur_amount": 6})

    def update_theme_config(self, theme_config: dict[str, Any]) -> None:
        ui = self._ensure_ui_section()
        ui["theme"] = {
            "mode": theme_config.get("mode", "system"),
            "primary_color": theme_config.get("primary_color", "#4A7FD9"),
            "blur_amount": theme_config.get("blur_amount", 6),
            "sidebar_collapsed": theme_config.get("sidebar_collapsed", True),
            "titlebar_hidden": theme_config.get("titlebar_hidden", True),
        }
        self.save(self.config)
        logger.info("主题配置已更新")

    def get_download_config(self) -> dict[str, Any]:
        return self.config[0].get("download", {"mirror_source": "official", "download_threads": 4})

    def update_download_config(self, download_config: dict[str, Any]) -> None:
        if not self.config:
            self.config = self._get_default_config()
        self.config[0]["download"] = download_config
        self.save(self.config)
        logger.info("下载配置已更新")

    def get_mouse_effect_config(self) -> dict[str, Any]:
        return self.ui.get(
            "mouse_effect", {"enabled": False, "color": "45,175,255", "scale": 1.5, "opacity": 1.0, "speed": 1.0}
        )

    def update_mouse_effect_config(self, mouse_effect_config: dict[str, Any]) -> None:
        ui = self._ensure_ui_section()
        ui["mouse_effect"] = {
            "enabled": mouse_effect_config.get("enabled", False),
            "color": mouse_effect_config.get("color", "45,175,255"),
            "scale": mouse_effect_config.get("scale", 1.5),
            "opacity": mouse_effect_config.get("opacity", 1.0),
            "speed": mouse_effect_config.get("speed", 1.0),
        }
        self.save(self.config)
        logger.info("鼠标点击效果配置已更新")

    def get_instances_config(self) -> list[dict[str, Any]]:
        return self._instances

    def add_instance(self, instance: dict[str, Any]) -> str:
        instance_id = str(uuid.uuid4())
        instance["id"] = instance_id
        instance["created_at"] = datetime.now().isoformat()
        self._instances.append(instance)
        logger.info(f"实例已创建: {instance_id}")
        try:
            from ..api.events import emit_plugin_event
            emit_plugin_event("instance:created", {"instance_id": instance_id, "name": instance.get("name", ""), "version": instance.get("version", "")})
        except ImportError:
            pass
        return instance_id

    def update_instance(self, instance_id: str, updates: dict[str, Any]) -> bool:
        for i, inst in enumerate(self._instances):
            if inst.get("id") == instance_id:
                self._instances[i].update(updates)
                logger.info(f"实例已更新: {instance_id}")
                return True
        return False

    def delete_instance(self, instance_id: str) -> bool:
        for i, inst in enumerate(self._instances):
            if inst.get("id") == instance_id:
                name = inst.get("name", "")
                self._instances.pop(i)
                logger.info(f"实例已删除: {instance_id}")
                try:
                    from ..api.events import emit_plugin_event
                    emit_plugin_event("instance:deleted", {"instance_id": instance_id, "name": name})
                except ImportError:
                    pass
                return True
        return False

    def get_instance(self, instance_id: str) -> dict[str, Any] | None:
        for inst in self._instances:
            if inst.get("id") == instance_id:
                return inst
        return None

    def __repr__(self) -> str:
        return f"ConfigManager(config_path='{self.config_path!s}')"
