import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from ECL.Events import EventBus
from ECL.Infrastructure import get_logger
from ECL.Plugin.dependencies import (
    DependencyResolution,
    PluginDependencyInfo,
    parse_dependency,
    parse_version,
    resolve_dependencies,
)
from ECL.Plugin.permissions import PermissionManager
from ECL.Plugin.plugin import Plugin


class PluginCommandError(Exception):
    """插件命令执行失败"""


class PluginAction(StrEnum):
    """可由插件管理 API 执行的状态操作。"""

    ENABLE = "enable"
    DISABLE = "disable"
    UNLOAD = "unload"
    RELOAD = "reload"
    INSTALL = "install"
    UPDATE_SETTING = "update_setting"


@dataclass(frozen=True, slots=True)
class PluginActionResult:
    """插件操作结果。"""

    plugin_name: str
    action: PluginAction
    status: str
    message: str = ""

    @property
    def success(self) -> bool:
        """操作是否成功。"""
        return self.status in {"enabled", "disabled", "unloaded", "installed", "updated"}


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
        self._command_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="plugin_cmd")
        self._plugins: dict[str, Plugin] = {}  # name → Plugin 实例
        self._status: dict[str, str] = {}  # name → unloaded | loaded | enabled | disabled
        self._routes: list[dict[str, str]] = []  # 所有插件注册的路由
        # 插件配置值，key 为 "插件名.设置键"
        self._config_values: dict[str, Any] = {}
        # 插件配置文件的路径映射
        self._config_paths: dict[str, Path] = {}
        # 同一插件可以向一个插槽追加多个条目；带 key 的 HTML 和同名 Vue 组件会原位更新
        self._slots: dict[str, list[dict[str, str]]] = {}
        self._vue_slots: dict[str, list[dict[str, str]]] = {}
        # Vue 组件路由：与 _routes 平行的独立列表
        self._vue_routes: list[dict[str, Any]] = []
        # 已注册的 Vue 组件（去重），component_name → {plugin, template, script, style}
        self._vue_components: dict[str, dict[str, Any]] = {}
        self._event_handlers_registered = False
        self._dependency_resolution: DependencyResolution = DependencyResolution()
        self._permission_manager = PermissionManager()
        # 被禁用的插件名集合，持久化到 plugin_state.json
        self._disabled_plugins: set[str] = set()
        self._plugin_state_path: Path | None = None
        # 候选插件映射，用于在启用被禁用的插件时按需加载
        self._candidate_map: dict[str, dict[str, Any]] = {}
        # 插件实例化/启用失败的详细错误信息，供前端展示
        self._plugin_errors: dict[str, str] = {}
        # 前端是否已就绪；就绪后新启用的插件需要单独补调 on_frontend_ready
        self._frontend_ready = False
        self._sidebar_collapsed: bool | None = None

    def initialize(self, data_path: Path, resource_path: Path | None = None) -> None:
        """从用户和系统目录发现插件，按依赖顺序加载并启用可用插件。"""
        self._data_path = Path(data_path)
        self._resource_path = Path(resource_path) if resource_path is not None else self._data_path
        self._plugin_dir = self._data_path / "plugins"
        self._plugin_dir.mkdir(parents=True, exist_ok=True)
        self._plugin_config_dir = self._data_path / "plugin_config"
        self._plugin_config_dir.mkdir(parents=True, exist_ok=True)
        self._plugin_state_path = self._data_path / "plugin_state.json"
        self._load_plugin_state()
        # 订阅 HTML 注入事件，收集插槽内容
        if not self._event_handlers_registered:
            EventBus().subscribe("plugin:html_injected", self._on_html_injected)
            # 订阅 Vue 组件注册事件，收集 Vue 插槽和路由
            EventBus().subscribe("plugin:vue_slot_registered", self._on_vue_slot_registered)
            self._event_handlers_registered = True

        candidates = self._collect_candidates(self._plugin_dir, is_system=False)
        candidates.extend(
            self._collect_candidates(self._resource_path / "resources" / "system_plugins", is_system=True)
        )
        self._candidate_map = {c["name"]: c for c in candidates}
        self._dependency_resolution = self._resolve_candidate_dependencies(candidates)
        self._load_plugins_in_order(candidates, self._dependency_resolution.load_order)
        self._enable_all()
        self.logger.info(
            "插件框架初始化完成，已加载 %d 个插件，已禁用 %d 个插件",
            len(self._plugins),
            len(self._disabled_plugins),
        )

    def _collect_candidates(self, base_dir: Path, is_system: bool) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        if not base_dir.is_dir():
            return candidates
        for plugin_dir in sorted(base_dir.iterdir()):
            if not plugin_dir.is_dir():
                continue
            metadata_path = plugin_dir / "plugin.json"
            if not metadata_path.is_file():
                continue
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.logger.warning("插件元数据解析失败: %s", metadata_path)
                continue
            name = metadata.get("name")
            if not name:
                continue
            candidates.append(
                {
                    "name": name,
                    "plugin_dir": plugin_dir,
                    "metadata_path": metadata_path,
                    "metadata": metadata,
                    "is_system": is_system,
                }
            )
        return candidates

    def _resolve_candidate_dependencies(self, candidates: list[dict[str, Any]]) -> DependencyResolution:
        """根据候选插件元数据解析依赖关系与加载顺序。"""
        seen: set[str] = set()
        infos: list[PluginDependencyInfo] = []
        for candidate in candidates:
            name = candidate["name"]
            if name in seen:
                self.logger.warning("插件 %s 重复，跳过", name)
                continue
            seen.add(name)
            metadata = candidate["metadata"]
            deps_meta = metadata.get("dependencies", {})
            deps: list[Any] = []
            for dep_name, dep_value in deps_meta.items():
                req = parse_dependency(dep_name, dep_value)
                if req is None:
                    self.logger.warning("插件 %s 的依赖 %s 格式无效", name, dep_name)
                    continue
                deps.append(req)
            infos.append(
                PluginDependencyInfo(
                    name=name,
                    version=metadata.get("version", "0.0.0"),
                    dependencies=deps,
                    is_system=candidate["is_system"],
                )
            )
        return resolve_dependencies(infos)

    def _load_plugins_in_order(self, candidates: list[dict[str, Any]], load_order: list[str]) -> None:
        """按依赖拓扑顺序实例化并加载插件；被禁用的插件直接跳过。"""
        candidate_map = {c["name"]: c for c in candidates}
        for name in self._disabled_plugins:
            candidate = candidate_map.get(name)
            if candidate is None:
                continue
            self._permission_manager.register_plugin_permissions(name, candidate["metadata"].get("permissions", []))
            self._status[name] = "disabled"
        for name in load_order:
            if name in self._disabled_plugins:
                self.logger.info("插件 %s 已被禁用，跳过加载", name)
                continue
            candidate = candidate_map.get(name)
            if candidate is None:
                continue
            self._load_plugin(candidate["plugin_dir"], candidate["metadata_path"], candidate["is_system"])

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
        # 在实例化之前注册权限声明，使 __init__ 中的装饰器注册能立即生效
        permissions_meta = metadata.get("permissions", [])
        self._permission_manager.register_plugin_permissions(name, permissions_meta)
        self._load_plugin_config(name, metadata)

        self._status[name] = "loading"
        try:
            plugin = self._create_instance(name, plugin_dir, metadata, entry_point, is_system)
        except PermissionError as exc:
            detail = str(exc)
            self.logger.error("插件 %s 权限声明不足，无法实例化: %s", name, detail)
            self._status[name] = "permission_denied"
            self._plugin_errors[name] = detail
            return
        except Exception as exc:
            self.logger.exception("插件 %s 实例化失败", name)
            self._status[name] = "error"
            self._plugin_errors[name] = str(exc)
            return
        self._plugins[name] = plugin
        self._status[name] = "loaded"
        self._call_plugin_hook(plugin, "on_load")
        self.logger.info("插件已加载: %s v%s", name, plugin.version)

    def _create_instance(
        self, name: str, plugin_dir: Path, metadata: dict[str, Any], entry_point: str, is_system: bool
    ) -> Plugin:
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
        return plugin_class(self, plugin_dir, metadata, is_system)

    def _call_plugin_hook(self, plugin: Plugin, method_name: str, *, fail_status: str | None = None) -> bool:
        """安全调用插件生命周期钩子；失败时记录日志并可选择恢复状态。"""
        try:
            getattr(plugin, method_name)()
            return True
        except PermissionError as exc:
            detail = str(exc)
            self.logger.error("插件 %s %s 权限不足: %s", plugin.name, method_name, detail)
            self._status[plugin.name] = "permission_denied"
            self._plugin_errors[plugin.name] = detail
            return False
        except Exception as exc:
            self.logger.exception("插件 %s %s 失败", plugin.name, method_name)
            self._plugin_errors[plugin.name] = str(exc)
            if fail_status is not None:
                self._status[plugin.name] = fail_status
            return False

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
        data = {k[len(prefix) :]: v for k, v in self._config_values.items() if k.startswith(prefix)}
        config_path = self._config_paths.get(name)
        if config_path is None:
            return
        config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_plugin_state(self) -> None:
        """从 plugin_state.json 读取已禁用的插件列表。"""
        if self._plugin_state_path is None or not self._plugin_state_path.is_file():
            self._disabled_plugins = set()
            return
        try:
            state = json.loads(self._plugin_state_path.read_text(encoding="utf-8"))
            disabled = state.get("disabled", [])
            self._disabled_plugins = set(disabled) if isinstance(disabled, list) else set()
        except (json.JSONDecodeError, OSError):
            self.logger.warning("插件状态文件解析失败: %s", self._plugin_state_path)
            self._disabled_plugins = set()

    def _save_plugin_state(self) -> None:
        """将已禁用的插件列表写入 plugin_state.json。"""
        if self._plugin_state_path is None:
            return
        state = {"disabled": sorted(self._disabled_plugins)}
        self._plugin_state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _enable_all(self) -> None:
        """按依赖拓扑顺序启用已加载插件；被禁用的插件不参与启用。"""
        for name in self._dependency_resolution.load_order:
            if name in self._disabled_plugins:
                continue
            if name in self._plugins:
                self._enable(name)

    def enable(self, name: str) -> PluginActionResult:
        """启用插件。"""
        enabled, reason = self._enable(name)
        return PluginActionResult(
            plugin_name=name,
            action=PluginAction.ENABLE,
            status="enabled" if enabled else self._status.get(name, "failed"),
            message=reason,
        )

    def _enable(self, name: str) -> tuple[bool, str]:
        plugin = self._plugins.get(name)
        # 若插件因被禁用而未加载，先按候选信息加载
        if plugin is None and name in self._disabled_plugins and name in self._candidate_map:
            candidate = self._candidate_map[name]
            self._load_plugin(candidate["plugin_dir"], candidate["metadata_path"], candidate["is_system"])
            plugin = self._plugins.get(name)
        if plugin is None:
            reason = self._plugin_errors.get(name) or self._dependency_resolution.errors.get(name)
            return False, reason or f"插件不存在或未加载: {name}"
        current = self._status.get(name)
        if current not in ("loaded", "disabled"):
            reason = self._plugin_errors.get(name) or self._dependency_resolution.errors.get(name)
            return False, reason or f"插件当前状态为 {current}，无法启用"
        # 加载后若依赖仍不满足，则不应启用
        if not self._are_dependencies_satisfied(plugin.metadata):
            reason = f"插件 {name} 依赖未满足"
            self.logger.warning(reason)
            self._plugin_errors[name] = reason
            return False, reason
        self._status[name] = "enabling"
        if not self._call_plugin_hook(plugin, "on_enable", fail_status="loaded"):
            reason = self._plugin_errors.get(name, f"插件 {name} on_enable 钩子执行失败")
            return False, reason
        self._status[name] = "enabled"
        # 从禁用列表移除并持久化，确保下次启动会加载该插件
        self._disabled_plugins.discard(name)
        self._save_plugin_state()
        self._plugin_errors.pop(name, None)
        EventBus().emit("plugin:enabled", plugin)
        self.logger.info("插件已启用: %s", name)
        # 若前端已就绪，单独通知该插件注入 UI 资源，避免重复通知所有插件
        if self._frontend_ready:
            self._call_plugin_hook(plugin, "on_frontend_ready")
        return True, ""

    def disable(self, name: str, _persist_state: bool = True) -> PluginActionResult:
        """禁用插件。"""
        plugin = self._plugins.get(name)
        if plugin is None or self._status.get(name) != "enabled":
            reason = self._plugin_errors.get(name) or self._dependency_resolution.errors.get(name)
            return PluginActionResult(
                name,
                PluginAction.DISABLE,
                self._status.get(name, "not_found"),
                reason or "插件未启用",
            )
        self._status[name] = "disabling"
        self._call_plugin_hook(plugin, "on_disable")
        self._status[name] = "disabled"
        # 清理禁用插件注册的前端内容和事件处理器，重新启用时由插件重新注册
        self._routes = [r for r in self._routes if r["plugin"] != name]
        self._vue_routes = [r for r in self._vue_routes if r["plugin"] != name]
        for slot_id, entries in self._slots.items():
            self._slots[slot_id] = [entry for entry in entries if entry["plugin"] != name]
        for slot_id, entries in self._vue_slots.items():
            self._vue_slots[slot_id] = [entry for entry in entries if entry["plugin"] != name]
        self._vue_components = {
            component_name: component
            for component_name, component in self._vue_components.items()
            if component["plugin"] != name
        }
        EventBus().remove_handlers_by_owner(name)
        # 持久化禁用状态，下次启动时跳过该插件；关闭流程中不写入，避免把所有插件标为禁用
        if _persist_state:
            self._disabled_plugins.add(name)
            self._save_plugin_state()
            EventBus().emit("plugin:disabled", plugin)
        self.logger.info("插件已禁用: %s", name)
        return PluginActionResult(name, PluginAction.DISABLE, "disabled")

    def unload(self, name: str, _persist_state: bool = True) -> PluginActionResult:
        """卸载插件。"""
        plugin = self._plugins.get(name)
        if plugin is None:
            reason = self._plugin_errors.get(name) or self._dependency_resolution.errors.get(name)
            return PluginActionResult(
                name,
                PluginAction.UNLOAD,
                self._status.get(name, "not_found"),
                reason or "插件不存在或未加载",
            )
        current = self._status.get(name)
        if current == "enabled":
            self.disable(name, _persist_state=_persist_state)
        self._status[name] = "unloading"
        self._call_plugin_hook(plugin, "on_unload")
        # 清理注册的路由和状态
        self._routes = [r for r in self._routes if r["plugin"] != name]
        self._vue_routes = [r for r in self._vue_routes if r["plugin"] != name]
        # 清理插槽注入
        for slot_id, entries in self._slots.items():
            self._slots[slot_id] = [entry for entry in entries if entry["plugin"] != name]
        for slot_id, entries in self._vue_slots.items():
            self._vue_slots[slot_id] = [entry for entry in entries if entry["plugin"] != name]
        # 清理已注册的 Vue 组件
        self._vue_components = {k: v for k, v in self._vue_components.items() if v["plugin"] != name}
        # 清理事件处理器
        EventBus().remove_handlers_by_owner(name)
        self._plugins.pop(name, None)
        self._status.pop(name, None)
        EventBus().emit("plugin:unloaded", name)
        self.logger.info("插件已卸载: %s", name)
        return PluginActionResult(name, PluginAction.UNLOAD, "unloaded")

    def reload(self, name: str) -> PluginActionResult:
        """重新加载插件。"""
        plugin = self._plugins.get(name)
        if plugin is None:
            reason = self._plugin_errors.get(name) or self._dependency_resolution.errors.get(name)
            return PluginActionResult(
                name,
                PluginAction.RELOAD,
                self._status.get(name, "not_found"),
                reason or "插件不存在或未加载",
            )
        plugin_dir = plugin.plugin_dir
        is_system = getattr(plugin, "is_system", False)
        # 重载是临时卸载，不应把插件写入禁用状态文件
        self.unload(name, _persist_state=False)
        metadata_path = plugin_dir / "plugin.json"
        if not metadata_path.is_file():
            return PluginActionResult(name, PluginAction.RELOAD, "invalid", "插件清单不存在")
        self._load_plugin(plugin_dir, metadata_path, is_system)
        enabled, reason = self._enable(name)
        return PluginActionResult(name, PluginAction.RELOAD, "enabled" if enabled else "failed", reason)

    def install(self, source_path: str) -> PluginActionResult:
        """安装插件。"""
        source = Path(source_path)
        if not source.is_dir():
            return PluginActionResult("", PluginAction.INSTALL, "invalid", "插件源目录不存在")
        metadata_path = source / "plugin.json"
        if not metadata_path.is_file():
            return PluginActionResult("", PluginAction.INSTALL, "invalid", "插件清单不存在")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        target_name = metadata.get("name")
        if not target_name:
            return PluginActionResult("", PluginAction.INSTALL, "invalid", "插件清单缺少 name")
        target_dir = self._plugin_dir / target_name
        # 用 shutil.copytree 复制整个插件目录，覆盖已存在的
        import shutil

        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(source, target_dir)
        self._load_plugin(target_dir, target_dir / "plugin.json", is_system=False)
        if target_name not in self._plugins:
            reason = self._plugin_errors.get(target_name)
            return PluginActionResult(target_name, PluginAction.INSTALL, "failed", reason or "插件加载失败")
        if not self._are_dependencies_satisfied(metadata):
            self.logger.warning("插件 %s 依赖未满足，仅加载不启用", target_name)
            self.unload(target_name)
            return PluginActionResult(target_name, PluginAction.INSTALL, "failed", "插件依赖未满足")
        enabled, reason = self._enable(target_name)
        if not enabled:
            return PluginActionResult(target_name, PluginAction.INSTALL, "failed", reason)
        EventBus().emit("plugin:installed", target_name)
        return PluginActionResult(target_name, PluginAction.INSTALL, "installed")

    def _are_dependencies_satisfied(self, metadata: dict[str, Any]) -> bool:
        """检查插件元数据中的依赖是否已被当前加载的插件满足。"""
        deps = metadata.get("dependencies", {})
        for dep_name, dep_value in deps.items():
            req = parse_dependency(dep_name, dep_value)
            if req is None:
                continue
            dep_plugin = self._plugins.get(req.name)
            if dep_plugin is None:
                if not req.optional:
                    return False
                continue
            dep_version = parse_version(dep_plugin.version)
            if dep_version is None or not req.specifier.contains(dep_version, prereleases=True):
                return False
        return True

    def on_frontend_ready(self) -> None:
        """通知所有已启用插件前端已就绪；重复调用无效。"""
        if self._frontend_ready:
            return
        self._frontend_ready = True
        for name, plugin in self._plugins.items():
            if self._status.get(name) != "enabled":
                continue
            self._call_plugin_hook(plugin, "on_frontend_ready")
        if self._sidebar_collapsed is not None:
            EventBus().emit("frontend:sidebar_changed", {"collapsed": self._sidebar_collapsed})

    def set_sidebar_state(self, collapsed: bool) -> None:
        """记录侧栏状态，并在前端就绪后通知插件。"""
        if collapsed == self._sidebar_collapsed:
            return
        self._sidebar_collapsed = collapsed
        if self._frontend_ready:
            EventBus().emit("frontend:sidebar_changed", {"collapsed": collapsed})

    def close(self) -> None:
        """按依赖拓扑的逆序卸载已加载插件并解除框架事件订阅。"""
        loaded_plugins = set(self._plugins)
        plugin_names = [
            name for name in reversed(self._dependency_resolution.load_order) if name in loaded_plugins
        ]
        plugin_names.extend([name for name in reversed(list(self._plugins.keys())) if name not in plugin_names])
        self.logger.info("正在退出插件框架，共 %d 个已加载插件", len(plugin_names))
        for name in plugin_names:
            try:
                # 关闭流程中不持久化禁用状态，避免把所有插件写入 plugin_state.json
                if not self.unload(name, _persist_state=False).success:
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
        self._permission_manager.clear()
        self._disabled_plugins.clear()
        self._sidebar_collapsed = None
        self._command_executor.shutdown(wait=False)
        self.logger.info("插件框架已退出")

    def _register_route(self, plugin: Plugin, path: str, title: str, icon: str) -> None:
        # 同一插件重复注册相同路径时先移除旧条目，避免路由列表出现重复
        self._routes = [r for r in self._routes if not (r["plugin"] == plugin.name and r["path"] == path)]
        self._routes.append({"plugin": plugin.name, "path": path, "title": title, "icon": icon})
        EventBus().emit("plugin:route_registered", plugin.name, path, title, icon)

    def get_plugin(self, name: str) -> Plugin | None:
        """获取插件。"""
        return self._plugins.get(name)

    def subscribe_event(self, plugin: Plugin, event: str, handler: Any) -> None:
        """
        统一注册插件的事件订阅，自动以插件名作为所有者标识。
        插件自身无需也不能指定所有者，由插件管理器统一注入。
        :param plugin: 插件实例
        :param event: 事件名称
        :param handler: 回调函数
        """
        EventBus().subscribe(event, handler, owner=plugin.name)

    def list_plugins(self) -> list[dict[str, Any]]:
        """获取插件列表。"""
        result = []
        for name, plugin in self._plugins.items():
            result.append(
                {
                    "name": name,
                    "title": plugin.title,
                    "version": plugin.version,
                    "description": plugin.description,
                    "author": plugin.author,
                    "icon": "",
                    "status": self._status.get(name, "unloaded"),
                    "error": self._plugin_errors.get(name) or self._dependency_resolution.errors.get(name),
                    "dependencies": plugin.metadata.get("dependencies", {}),
                    "permissions": [p.to_dict() for p in self._permission_manager.get_plugin_permissions(name)],
                    "services": list(plugin._commands.keys()),
                    "settings": list(plugin._settings.keys()),
                    "is_system": getattr(plugin, "is_system", False),
                }
            )
        # 补充因依赖错误未被加载的插件条目，便于前端展示
        loaded_names = set(self._plugins.keys())
        for name in sorted(self._dependency_resolution.skipped - loaded_names - self._disabled_plugins):
            result.append(
                {
                    "name": name,
                    "title": name,
                    "version": "",
                    "description": "",
                    "author": "",
                    "icon": "",
                    "status": "unloaded",
                    "error": self._dependency_resolution.errors.get(name),
                    "dependencies": {},
                    "permissions": [],
                    "services": [],
                    "settings": [],
                    "is_system": False,
                }
            )
        # 补充被禁用且未实例化的插件条目，仍从 plugin.json 读取元数据供前端展示
        for name in sorted(self._disabled_plugins - loaded_names):
            candidate = self._candidate_map.get(name, {})
            metadata = candidate.get("metadata", {})
            result.append(
                {
                    "name": name,
                    "title": metadata.get("title", name),
                    "version": metadata.get("version", ""),
                    "description": metadata.get("description", ""),
                    "author": metadata.get("author", ""),
                    "icon": "",
                    "status": "disabled",
                    "error": None,
                    "dependencies": metadata.get("dependencies", {}),
                    "permissions": [p.to_dict() for p in self._permission_manager.get_plugin_permissions(name)],
                    "services": [],
                    "settings": [],
                    "is_system": candidate.get("is_system", False),
                }
            )
        # 补充实例化失败的插件条目
        for name in sorted(set(self._plugin_errors.keys()) - loaded_names):
            candidate = self._candidate_map.get(name, {})
            metadata = candidate.get("metadata", {})
            result.append(
                {
                    "name": name,
                    "title": metadata.get("title", name),
                    "version": metadata.get("version", ""),
                    "description": metadata.get("description", ""),
                    "author": metadata.get("author", ""),
                    "icon": "",
                    "status": self._status.get(name, "error"),
                    "error": self._plugin_errors.get(name),
                    "dependencies": metadata.get("dependencies", {}),
                    "permissions": [p.to_dict() for p in self._permission_manager.get_plugin_permissions(name)],
                    "services": [],
                    "settings": [],
                    "is_system": candidate.get("is_system", False),
                }
            )
        return result

    def get_routes(self) -> list[dict[str, Any]]:
        """获取插件路由。"""
        return list(self._routes)

    def get_slots(self) -> dict[str, list[dict[str, str]]]:
        """返回按插槽分组的插件 HTML 注入内容。"""
        return {slot_id: [dict(entry) for entry in entries] for slot_id, entries in self._slots.items()}

    def get_vue_slots(self) -> dict[str, list[dict[str, Any]]]:
        """返回按插槽分组的插件 Vue 组件定义。"""
        return {slot_id: [dict(entry) for entry in entries] for slot_id, entries in self._vue_slots.items()}

    def get_vue_components(self) -> dict[str, dict[str, Any]]:
        """返回所有已注册 Vue 组件定义的浅拷贝。"""
        return dict(self._vue_components)

    def get_vue_routes(self) -> list[dict[str, Any]]:
        """获取 Vue 路由。"""
        return list(self._vue_routes)

    def _on_html_injected(self, plugin_name: str, slot_id: str, html: str, key: str | None) -> None:
        entries = self._slots.setdefault(slot_id, [])
        entry = {"plugin": plugin_name, "html": html}
        if key is None:
            entries.append(entry)
            return
        entry["key"] = key
        for index, current in enumerate(entries):
            if current["plugin"] == plugin_name and current.get("key") == key:
                entries[index] = entry
                return
        entries.append(entry)

    def _on_vue_slot_registered(
        self, plugin_name: str, slot_id: str, component_name: str, template: str, script: str, style: str
    ) -> None:
        entries = self._vue_slots.setdefault(slot_id, [])
        entry = {
            "plugin": plugin_name,
            "component_name": component_name,
            "template": template,
            "script": script,
            "style": style,
        }
        for index, current in enumerate(entries):
            if current["plugin"] == plugin_name and current["component_name"] == component_name:
                entries[index] = entry
                break
        else:
            entries.append(entry)
        # 全局组件表用于路由引用 / 去重
        self._vue_components[component_name] = {
            "plugin": plugin_name,
            "template": template,
            "script": script,
            "style": style,
        }

    def _register_vue_route(
        self,
        plugin: Plugin,
        path: str,
        title: str,
        icon: str,
        component_name: str,
        template: str,
        script: str,
        style: str,
    ) -> None:
        """注册 Vue 组件路由，同时记录到 _routes 和 _vue_routes"""
        # 同一插件重复注册相同路径时先移除旧条目，避免路由列表出现重复
        self._routes = [r for r in self._routes if not (r["plugin"] == plugin.name and r["path"] == path)]
        self._vue_routes = [r for r in self._vue_routes if not (r["plugin"] == plugin.name and r["path"] == path)]
        self._routes.append(
            {
                "plugin": plugin.name,
                "path": path,
                "title": title,
                "icon": icon,
                "component": component_name,
                "type": "vue",
            }
        )
        self._vue_routes.append(
            {
                "plugin": plugin.name,
                "path": path,
                "title": title,
                "icon": icon,
                "component_name": component_name,
                "template": template,
                "script": script,
                "style": style,
            }
        )
        self._vue_components[component_name] = {
            "plugin": plugin.name,
            "template": template,
            "script": script,
            "style": style,
        }
        EventBus().emit("plugin:route_registered", plugin.name, path, title, icon)
        EventBus().emit(
            "plugin:vue_route_registered", plugin.name, path, title, component_name, template, script, style, icon
        )

    def get_settings(self, name: str) -> dict[str, Any]:
        """返回插件设置结构及当前持久化值。"""
        plugin = self._plugins.get(name)
        if plugin is None:
            return {"schema": None, "values": {}}
        schema = list(plugin._settings.values())
        values = {}
        for key in plugin._settings:
            full_key = f"{name}.{key}"
            values[key] = self._config_values.get(full_key, plugin._settings[key]["default"])
        return {"schema": schema, "values": values}

    def update_setting(self, name: str, key: str, value: Any) -> PluginActionResult:
        """更新一个已声明的插件设置，并返回保存结果。"""
        plugin = self._plugins.get(name)
        if plugin is None or key not in plugin._settings:
            return PluginActionResult(name, PluginAction.UPDATE_SETTING, "not_found", "插件或设置项不存在")
        full_key = f"{name}.{key}"
        old_value = self._config_values.get(full_key)
        self._config_values[full_key] = value
        self._save_plugin_config(name)
        EventBus().emit("plugin:settings_changed", name, key, old_value, value)
        return PluginActionResult(name, PluginAction.UPDATE_SETTING, "updated")

    def call_command(self, command: str, params: dict[str, Any] | None = None, timeout: float = 30.0) -> Any:
        """在线程池中调用 ``插件名:命令名``，失败或超时时抛出 ``PluginCommandError``。"""
        if ":" not in command:
            raise PluginCommandError(f"命令格式错误: {command}")
        plugin_name, cmd_name = command.split(":", 1)
        plugin = self._plugins.get(plugin_name)
        if plugin is None or self._status.get(plugin_name) != "enabled":
            raise PluginCommandError(f"插件 {plugin_name} 未启用或不存在")
        handler = plugin._commands.get(cmd_name)
        if handler is None:
            raise PluginCommandError(f"插件 {plugin_name} 不存在命令 {cmd_name}")
        try:
            future = self._command_executor.submit(handler, **(params or {}))
            return future.result(timeout=timeout)
        except FutureTimeoutError:
            self.logger.error("插件 %s 命令 %s 执行超时", plugin_name, cmd_name)
            raise PluginCommandError(f"插件 {plugin_name} 命令 {cmd_name} 执行超时") from None
        except PluginCommandError:
            raise
        except Exception as exc:
            self.logger.exception("插件 %s 命令 %s 执行失败", plugin_name, cmd_name)
            raise PluginCommandError(f"插件 {plugin_name} 命令 {cmd_name} 执行失败: {exc}") from exc
