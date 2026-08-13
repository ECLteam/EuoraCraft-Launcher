import json
import shutil
from pathlib import Path
from time import perf_counter
from typing import Any

from ECL.plugins.dependencies import parse_dependency, parse_version

from .base import _PluginState
from .contracts import PluginAction, PluginActionResult


class PluginLifecycle(_PluginState):
    def _enable_all(self) -> None:
        """
        按依赖拓扑顺序启用已加载插件；被禁用的插件不参与启用。
        """
        started = perf_counter()
        enabled_count = 0
        for name in self._dependency_resolution.load_order:
            if name in self._disabled_plugins:
                continue
            if name in self._plugins:
                enabled, _reason = self._enable(name)
                enabled_count += int(enabled)
        self.logger.debug("插件批量启用完成: enabled=%d, duration=%.2fs", enabled_count, perf_counter() - started)

    def enable(self, name: str) -> PluginActionResult:
        """
        启用插件。

        :param name: 目标对象名称
        """
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
        self.events.emit("plugin:enabled", plugin)
        self.logger.info("插件已启用: %s", name)
        # 若前端已就绪，单独通知该插件注入 UI 资源，避免重复通知所有插件
        if self._frontend_ready:
            self._call_plugin_hook(plugin, "on_frontend_ready")
        return True, ""

    def disable(self, name: str, _persist_state: bool = True) -> PluginActionResult:
        """
        禁用插件。

        :param name: 目标对象名称
        :param _persist_state: 是否将状态变化写入持久化文件
        """
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
        self.events.remove_handlers_by_owner(name)
        # 持久化禁用状态，下次启动时跳过该插件；关闭流程中不写入，避免把所有插件标为禁用
        if _persist_state:
            self._disabled_plugins.add(name)
            self._save_plugin_state()
            self.events.emit("plugin:disabled", plugin)
        self.logger.info("插件已禁用: %s", name)
        return PluginActionResult(name, PluginAction.DISABLE, "disabled")

    def unload(self, name: str, _persist_state: bool = True) -> PluginActionResult:
        """
        卸载插件。

        :param name: 目标对象名称
        :param _persist_state: 是否将状态变化写入持久化文件
        """
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
        self.events.remove_handlers_by_owner(name)
        self._plugins.pop(name, None)
        self._status.pop(name, None)
        self.events.emit("plugin:unloaded", name)
        self.logger.info("插件已卸载: %s", name)
        return PluginActionResult(name, PluginAction.UNLOAD, "unloaded")

    def reload(self, name: str) -> PluginActionResult:
        """
        重新加载插件。

        :param name: 目标对象名称
        """
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
        """
        安装插件。

        :param source_path: 待安装插件的源目录
        """
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
        self.events.emit("plugin:installed", target_name)
        return PluginActionResult(target_name, PluginAction.INSTALL, "installed")

    def _are_dependencies_satisfied(self, metadata: dict[str, Any]) -> bool:
        """
        检查插件元数据中的依赖是否已被当前加载的插件满足。

        :param metadata: 插件清单元数据
        """
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
        """
        通知所有已启用插件前端已就绪；重复调用无效。
        """
        if self._frontend_ready:
            self.logger.debug("忽略重复的插件前端就绪通知")
            return
        started = perf_counter()
        notified = 0
        self.logger.info("正在通知已启用插件前端已就绪")
        self._frontend_ready = True
        for name, plugin in self._plugins.items():
            if self._status.get(name) != "enabled":
                continue
            self._call_plugin_hook(plugin, "on_frontend_ready")
            notified += 1
        if self._sidebar_collapsed is not None:
            self.events.emit("frontend:sidebar_changed", {"collapsed": self._sidebar_collapsed})
        self.logger.info(
            "插件前端就绪通知完成: notified=%d, duration=%.2fs",
            notified,
            perf_counter() - started,
        )

    def set_sidebar_state(self, collapsed: bool) -> None:
        """
        记录侧栏状态，并在前端就绪后通知插件。

        :param collapsed: 侧栏是否处于折叠状态
        """
        if collapsed == self._sidebar_collapsed:
            return
        self._sidebar_collapsed = collapsed
        if self._frontend_ready:
            self.events.emit("frontend:sidebar_changed", {"collapsed": collapsed})

    def close(self) -> None:
        """
        按依赖拓扑的逆序卸载已加载插件并解除框架事件订阅。
        """
        loaded_plugins = set(self._plugins)
        plugin_names = [name for name in reversed(self._dependency_resolution.load_order) if name in loaded_plugins]
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
            self.events.unsubscribe("plugin:html_injected", self._on_html_injected)
            self.events.unsubscribe("plugin:vue_slot_registered", self._on_vue_slot_registered)
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
