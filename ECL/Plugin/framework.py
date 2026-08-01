import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from ECL.Events import EventBus
from ECL.Infrastructure import get_logger
from ECL.Plugin.plugin import Plugin


class PluginFramework:
    """
    插件框架管理器，负责插件发现、加载、生命周期管理。
    插件来源：ECL_data/plugins/（用户插件）、resources/system_plugins/（系统插件）。
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.logger = get_logger("PluginFramework")
        self._initialized = True
        self._plugins: dict[str, Plugin] = {} # name → Plugin 实例
        self._status: dict[str, str] = {} # name → unloaded | loaded | enabled | disabled
        self._routes: list[dict[str, str]] = [] # 所有插件注册的路由
        # 插件配置值，key 为 "插件名.设置键"
        self._config_values: dict[str, Any] = {}
        # 插件配置文件的路径映射
        self._config_paths: dict[str, Path] = {}
        # 插槽注入：slot_id → {plugin_name: html}
        self._slots: dict[str, dict[str, str]] = {}
        # Vue 组件插槽：slot_id → {plugin_name: {component_name, template, script, style}}
        self._vue_slots: dict[str, dict[str, dict[str, str]]] = {}
        # Vue 组件路由：与 _routes 平行的独立列表
        self._vue_routes: list[dict[str, Any]] = []
        # 已注册的 Vue 组件（去重），component_name → {plugin, template, script, style}
        self._vue_components: dict[str, dict[str, Any]] = {}
        self._event_handlers_registered = False

    def initialize(self, data_path: Path, resource_path: Path | None = None) -> None:
        """
        扫描插件目录，加载所有插件
        :param data_path: 启动器可写数据目录
        :param resource_path: 启动器只读资源目录
        """
        self._data_path = Path(data_path)
        self._resource_path = Path(resource_path) if resource_path is not None else self._data_path
        self._plugin_dir = self._data_path / "plugins"
        self._plugin_dir.mkdir(parents=True, exist_ok=True)
        self._plugin_config_dir = self._data_path / "plugin_config"
        self._plugin_config_dir.mkdir(parents=True, exist_ok=True)
        # 订阅 HTML 注入事件，收集插槽内容
        if not self._event_handlers_registered:
            EventBus().subscribe("plugin:html_injected", self._on_html_injected)
            # 订阅 Vue 组件注册事件，收集 Vue 插槽和路由
            EventBus().subscribe("plugin:vue_slot_registered", self._on_vue_slot_registered)
            self._event_handlers_registered = True
        self._discover_and_load(self._plugin_dir, is_system=False)
        self._discover_and_load(self._resource_path / "resources" / "system_plugins", is_system=True)
        self._enable_all()
        self.logger.info("插件框架初始化完成，已加载 %d 个插件", len(self._plugins))

    def _discover_and_load(self, base_dir: Path, is_system: bool) -> None:
        if not base_dir.is_dir():
            return
        for plugin_dir in sorted(base_dir.iterdir()):
            if not plugin_dir.is_dir():
                continue
            metadata_path = plugin_dir / "plugin.json"
            if not metadata_path.is_file():
                continue
            self._load_plugin(plugin_dir, metadata_path, is_system)

    def _load_plugin(self, plugin_dir: Path, metadata_path: Path, is_system: bool) -> None:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self.logger.warning("插件元数据解析失败: %s", metadata_path)
            return
        name = metadata.get("name")
        if not name:
            return
        if name in self._plugins:
            self.logger.warning("插件 %s 重复，跳过", name)
            return
        entry_point = metadata.get("entry_point", "main:Plugin")
        # 加载插件配置值
        self._load_plugin_config(name, metadata)

        self._status[name] = "loading"
        try:
            plugin = self._create_instance(name, plugin_dir, metadata, entry_point)
        except Exception:
            self.logger.exception("插件 %s 实例化失败", name)
            self._status[name] = "unloaded"
            return
        plugin.is_system = is_system
        self._plugins[name] = plugin
        self._status[name] = "loaded"
        try:
            plugin.on_load()
        except Exception:
            self.logger.exception("插件 %s on_load 失败", name)
        self.logger.info("插件已加载: %s v%s", name, plugin.version)

    def _create_instance(self, name: str, plugin_dir: Path, metadata: dict[str, Any], entry_point: str) -> Plugin:
        """从 entry_point 创建插件实例，entry_point 格式为 "文件名:类名" 或纯 "文件名" """
        parts = entry_point.split(":", 1)
        module_name = parts[0]
        class_name = parts[1] if len(parts) > 1 else "Plugin"
        main_py = plugin_dir / f"{module_name}.py"
        if not main_py.is_file():
            raise FileNotFoundError(f"入口文件不存在: {main_py}")
        # 使用隔离的模块名避免命名冲突
        spec = importlib.util.spec_from_file_location(f"plugin_{name}", main_py)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        plugin_class = getattr(module, class_name)
        return plugin_class(self, plugin_dir, metadata)

    def _load_plugin_config(self, name: str, metadata: dict[str, Any]) -> None:
        """从 plugin_config/{name}.json 读取插件配置值"""
        config_path = self._plugin_config_dir / f"{name}.json"
        self._config_paths[name] = config_path
        if not config_path.is_file():
            return
        config_data = json.loads(config_path.read_text(encoding="utf-8"))
        for key, value in config_data.items():
            self._config_values[f"{name}.{key}"] = value

    def _save_plugin_config(self, name: str) -> None:
        """保存插件配置值到 plugin_config/{name}.json"""
        prefix = f"{name}."
        data = {k[len(prefix):]: v for k, v in self._config_values.items() if k.startswith(prefix)}
        config_path = self._config_paths.get(name)
        if config_path is None:
            return
        config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _enable_all(self) -> None:
        for name in list(self._plugins.keys()):
            self._enable(name)

    def _enable(self, name: str) -> bool:
        plugin = self._plugins.get(name)
        if plugin is None:
            return False
        current = self._status.get(name)
        if current not in ("loaded", "disabled"):
            return False
        self._status[name] = "enabling"
        try:
            plugin.on_enable()
        except Exception:
            self.logger.exception("插件 %s on_enable 失败", name)
            self._status[name] = "loaded"
            return False
        self._status[name] = "enabled"
        EventBus().emit("plugin:enabled", plugin)
        self.logger.info("插件已启用: %s", name)
        return True

    def disable(self, name: str) -> bool:
        plugin = self._plugins.get(name)
        if plugin is None or self._status.get(name) != "enabled":
            return False
        self._status[name] = "disabling"
        try:
            plugin.on_disable()
        except Exception:
            self.logger.exception("插件 %s on_disable 失败", name)
        self._status[name] = "disabled"
        # 清理禁用插件注册的路由，重新启用时 on_enable 会重新注册
        self._routes = [r for r in self._routes if r["plugin"] != name]
        self._vue_routes = [r for r in self._vue_routes if r["plugin"] != name]
        EventBus().emit("plugin:disabled", plugin)
        self.logger.info("插件已禁用: %s", name)
        return True

    def unload(self, name: str) -> bool:
        plugin = self._plugins.get(name)
        if plugin is None:
            return False
        current = self._status.get(name)
        if current == "enabled":
            self.disable(name)
        self._status[name] = "unloading"
        try:
            plugin.on_unload()
        except Exception:
            self.logger.exception("插件 %s on_unload 失败", name)
        # 清理注册的路由和状态
        self._routes = [r for r in self._routes if r["plugin"] != name]
        self._vue_routes = [r for r in self._vue_routes if r["plugin"] != name]
        # 清理插槽注入
        for slot_plugins in self._slots.values():
            slot_plugins.pop(name, None)
        for slot_plugins in self._vue_slots.values():
            slot_plugins.pop(name, None)
        # 清理已注册的 Vue 组件
        self._vue_components = {k: v for k, v in self._vue_components.items() if v["plugin"] != name}
        self._plugins.pop(name, None)
        self._status.pop(name, None)
        EventBus().emit("plugin:unloaded", name)
        self.logger.info("插件已卸载: %s", name)
        return True

    def reload(self, name: str) -> bool:
        plugin = self._plugins.get(name)
        if plugin is None:
            return False
        plugin_dir = plugin.plugin_dir
        is_system = getattr(plugin, "is_system", False)
        self.unload(name)
        metadata_path = plugin_dir / "plugin.json"
        if not metadata_path.is_file():
            return False
        self._load_plugin(plugin_dir, metadata_path, is_system)
        return self._enable(name)

    def install(self, source_path: str) -> bool:
        source = Path(source_path)
        if not source.is_dir():
            return False
        metadata_path = source / "plugin.json"
        if not metadata_path.is_file():
            return False
        target_name = json.loads(metadata_path.read_text(encoding="utf-8")).get("name")
        if not target_name:
            return False
        target_dir = self._plugin_dir / target_name
        # 用 shutil.copytree 复制整个插件目录，覆盖已存在的
        import shutil
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(source, target_dir)
        self._load_plugin(target_dir, target_dir / "plugin.json", is_system=False)
        self._enable(target_name)
        EventBus().emit("plugin:installed", target_name)
        return True

    def on_frontend_ready(self) -> None:
        """通知所有已启用插件前端已就绪"""
        for name, plugin in self._plugins.items():
            if self._status.get(name) != "enabled":
                continue
            try:
                plugin.on_frontend_ready()
            except Exception:
                self.logger.exception("插件 %s on_frontend_ready 失败", name)

    def close(self) -> None:
        """按禁用、卸载顺序退出全部插件并解除框架事件订阅。"""
        plugin_names = list(reversed(self._plugins))
        self.logger.info("正在退出插件框架，共 %d 个插件", len(plugin_names))
        for name in plugin_names:
            try:
                if not self.unload(name):
                    self.logger.warning("退出时未能卸载插件: %s", name)
            except Exception:
                self.logger.exception("退出时卸载插件失败: %s", name)

        if self._event_handlers_registered:
            bus = EventBus()
            bus.unsubscribe("plugin:html_injected", self._on_html_injected)
            bus.unsubscribe("plugin:vue_slot_registered", self._on_vue_slot_registered)
            self._event_handlers_registered = False

        self._routes.clear()
        self._vue_routes.clear()
        self._slots.clear()
        self._vue_slots.clear()
        self._vue_components.clear()
        self._config_values.clear()
        self._config_paths.clear()
        self.logger.info("插件框架已退出")

    def _register_route(self, plugin: Plugin, path: str, title: str, icon: str) -> None:
        self._routes.append({"plugin": plugin.name, "path": path, "title": title, "icon": icon})
        EventBus().emit("plugin:route_registered", plugin.name, path, title, icon)

    def get_plugin(self, name: str) -> Plugin | None:
        return self._plugins.get(name)

    def list_plugins(self) -> list[dict[str, Any]]:
        result = []
        for name, plugin in self._plugins.items():
            result.append({
                "name": name,
                "title": plugin.title,
                "version": plugin.version,
                "description": plugin.description,
                "author": plugin.author,
                "icon": "",
                "status": self._status.get(name, "unloaded"),
                "error": None,
                "dependencies": plugin.metadata.get("dependencies", {}),
                "events": plugin.metadata.get("events", {}),
                "services": list(plugin._commands.keys()),
                "settings": list(plugin._settings.keys()),
                "is_system": getattr(plugin, "is_system", False),
            })
        return result

    def get_routes(self) -> list[dict[str, Any]]:
        return self._routes

    def get_slots(self) -> dict[str, list[dict[str, str]]]:
        """
        获取所有插件的插槽注入内容
        :return: slot_id → [{plugin, html}, ...]
        """
        return {slot_id: [{"plugin": name, "html": html} for name, html in plugins.items()]
                for slot_id, plugins in self._slots.items()}

    def get_vue_slots(self) -> dict[str, list[dict[str, Any]]]:
        """
        获取所有插件注册的 Vue 组件插槽
        :return: slot_id → [{plugin, component_name, template, script, style}, ...]
        """
        return {slot_id: [{"plugin": name, **info} for name, info in plugins.items()]
                for slot_id, plugins in self._vue_slots.items()}

    def get_vue_components(self) -> dict[str, dict[str, Any]]:
        """
        获取所有已注册的 Vue 组件定义
        :return: component_name → {plugin, template, script, style}
        """
        return dict(self._vue_components)

    def get_vue_routes(self) -> list[dict[str, Any]]:
        return self._vue_routes

    def _on_html_injected(self, plugin_name: str, slot_id: str, html: str) -> None:
        """收集插件注入的 HTML 到对应插槽"""
        if slot_id not in self._slots:
            self._slots[slot_id] = {}
        self._slots[slot_id][plugin_name] = html

    def _on_vue_slot_registered(self, plugin_name: str, slot_id: str,
                                component_name: str, template: str, script: str, style: str) -> None:
        """收集插件注册的 Vue 组件到对应插槽和全局组件表"""
        if slot_id not in self._vue_slots:
            self._vue_slots[slot_id] = {}
        self._vue_slots[slot_id][plugin_name] = {
            "component_name": component_name,
            "template": template,
            "script": script,
            "style": style,
        }
        # 全局组件表用于路由引用 / 去重
        self._vue_components[component_name] = {
            "plugin": plugin_name,
            "template": template,
            "script": script,
            "style": style,
        }

    def _register_vue_route(self, plugin: Plugin, path: str, title: str, icon: str,
                            component_name: str, template: str, script: str, style: str) -> None:
        """注册 Vue 组件路由，同时记录到 _routes 和 _vue_routes"""
        self._routes.append({
            "plugin": plugin.name, "path": path, "title": title, "icon": icon,
            "component": component_name, "type": "vue",
        })
        self._vue_routes.append({
            "plugin": plugin.name, "path": path, "title": title, "icon": icon,
            "component_name": component_name, "template": template,
            "script": script, "style": style,
        })
        self._vue_components[component_name] = {
            "plugin": plugin.name, "template": template,
            "script": script, "style": style,
        }
        EventBus().emit("plugin:route_registered", plugin.name, path, title, icon)
        EventBus().emit("plugin:vue_route_registered", plugin.name, path, title,
                        component_name, template, script, style, icon)

    def get_settings(self, name: str) -> dict[str, Any]:
        plugin = self._plugins.get(name)
        if plugin is None:
            return {"schema": None, "values": {}}
        schema = list(plugin._settings.values())
        values = {}
        for key in plugin._settings:
            full_key = f"{name}.{key}"
            values[key] = self._config_values.get(full_key, plugin._settings[key]["default"])
        return {"schema": schema, "values": values}

    def update_setting(self, name: str, key: str, value: Any) -> bool:
        plugin = self._plugins.get(name)
        if plugin is None or key not in plugin._settings:
            return False
        full_key = f"{name}.{key}"
        old_value = self._config_values.get(full_key)
        self._config_values[full_key] = value
        self._save_plugin_config(name)
        EventBus().emit("plugin:settings_changed", name, key, old_value, value)
        return True

    def call_command(self, command: str, params: dict[str, Any] | None = None) -> Any:
        """
        调用插件命令，格式 "插件名:命令名"
        :param command: 命令字符串
        :param params: 命令参数
        :return: 命令返回值
        """
        if ":" not in command:
            return None
        plugin_name, cmd_name = command.split(":", 1)
        plugin = self._plugins.get(plugin_name)
        if plugin is None or self._status.get(plugin_name) != "enabled":
            return None
        handler = plugin._commands.get(cmd_name)
        if handler is None:
            return None
        return handler(**(params or {}))
