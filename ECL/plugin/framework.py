import asyncio
import contextlib
import importlib
import importlib.util
import json
import sys
import threading
from pathlib import Path
from typing import Any

from ..common.logger import get_logger
from .importer import PluginImporter
from .plugin import Plugin, PluginStatus
from .registry import EventRegistry, ServiceRegistry

logger = get_logger("plugin.framework")


def _get_event_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


class PluginFramework:
    def __init__(
        self,
        plugins_dir: str | Path,
        cache_root: str | Path | None = None,
        deps_meta_path: str | Path | None = None,
        config_root: str | Path | None = None,
        system_plugins_dir: str | Path | None = None,
    ):
        self._plugins_dir = Path(plugins_dir)
        self._cache_root = Path(cache_root) if cache_root else self._plugins_dir.parent / "dep_cache"
        self._deps_meta_path = Path(deps_meta_path) if deps_meta_path else self._plugins_dir.parent / "deps_meta.json"
        self._config_root = Path(config_root) if config_root else self._plugins_dir.parent / "plugin_config"
        self._system_plugins_dir = Path(system_plugins_dir) if system_plugins_dir else None

        self._plugins: dict[str, Plugin] = {}
        self._plugin_dirs: dict[str, Path] = {}
        self._system_plugins: set[str] = set()
        self._service_registry = ServiceRegistry()
        self._event_registry = EventRegistry()
        self._importer = PluginImporter(self._cache_root)

        self._deps_meta: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._shutting_down = False
        self._frontend_ready_fired = False
        self._plugin_settings: dict[str, dict[str, Any]] = {}
        self._plugin_routes: dict[str, dict[str, Any]] = {}
        self._plugin_commands: dict[str, dict[str, Any]] = {}
        self._html_slots: dict[str, list[tuple[str, str]]] = {}

        self._plugins_dir.mkdir(parents=True, exist_ok=True)
        self._cache_root.mkdir(parents=True, exist_ok=True)
        self._config_root.mkdir(parents=True, exist_ok=True)
        if self._deps_meta_path.exists():
            try:
                self._deps_meta = json.loads(self._deps_meta_path.read_text("utf-8"))
            except (ValueError, OSError) as e:
                logger.warning(f"读取依赖元数据失败: {e}")
                self._deps_meta = {}


    def scan_plugins(self) -> list[dict[str, Any]]:
        result = []
        if not self._plugins_dir.is_dir():
            return result

        for d in sorted(self._plugins_dir.iterdir()):
            if not d.is_dir():
                continue
            manifest = d / "plugin.json"
            if not manifest.exists():
                continue
            try:
                data = json.loads(manifest.read_text("utf-8"))
                info = {
                    "name": data.get("name", d.name),
                    "title": data.get("title", d.name),
                    "version": data.get("version", "0.0.0"),
                    "description": data.get("description", ""),
                    "author": data.get("author", ""),
                    "icon": data.get("icon", ""),
                    "status": "unloaded",
                    "error": None,
                    "is_system": False,
                }
                plugin = self._plugins.get(info["name"])
                if plugin:
                    info["status"] = plugin.status.value
                    info["error"] = plugin._error
                result.append(info)
            except (json.JSONDecodeError, OSError, KeyError) as e:
                logger.warning(f"解析插件 {d.name} 的 manifest 失败: {e}")
                result.append(
                    {
                        "name": d.name,
                        "title": d.name,
                        "version": "0.0.0",
                        "status": "error",
                        "error": str(e),
                        "is_system": False,
                    }
                )

        # 纳入系统插件
        for name in sorted(self._system_plugins):
            # 避免重复：如果同名普通插件已存在，跳过
            if any(p["name"] == name for p in result):
                continue
            self._load_plugin_config(name)
            info = {
                "name": name,
                "title": name,
                "version": "0.0.0",
                "description": "",
                "author": "",
                "icon": "",
                "status": "unloaded",
                "error": None,
                "is_system": True,
            }
            plugin = self._plugins.get(name)
            if plugin:
                info["title"] = plugin._meta.get("title", name)
                info["version"] = plugin._version
                info["description"] = plugin._meta.get("description", "")
                info["author"] = plugin._meta.get("author", "")
                info["icon"] = plugin._meta.get("icon", "")
                info["status"] = plugin.status.value
                info["error"] = plugin._error
            result.append(info)

        return result

    def load_plugin(self, plugin_name: str) -> dict[str, Any]:
        with self._lock:
            return self._load_plugin_internal(plugin_name)

    def enable_plugin(self, plugin_name: str) -> dict[str, Any]:
        with self._lock:
            return self._enable_plugin_internal(plugin_name, set())

    def disable_plugin(self, plugin_name: str, force: bool = False) -> dict[str, Any]:
        with self._lock:
            return self._disable_plugin_internal(plugin_name, force)

    def unload_plugin(self, plugin_name: str) -> dict[str, Any]:
        with self._lock:
            return self._unload_plugin_internal(plugin_name)

    def reload_plugin(self, plugin_name: str, cascade: bool = False) -> dict[str, Any]:
        with self._lock:
            logger.info(f"[framework] 重载请求: {plugin_name}, cascade={cascade}")

            dependents = self._get_dependents(plugin_name)
            if not cascade and dependents:
                logger.warning(f"[framework] 重载被拒绝: {plugin_name} 有依赖者 {dependents}")
                return {"success": False, "message": f"插件 {plugin_name} 被依赖: {dependents}，请使用 cascade=True"}

            # 拓扑排序：依赖者在前，被依赖者在后
            order = []
            visited = set()

            def visit(name: str) -> None:
                if name in visited:
                    return
                visited.add(name)
                for dep in self._get_dependents(name):
                    if dep not in visited:
                        visit(dep)
                order.append(name)

            visit(plugin_name)
            logger.info(f"[framework] 重载拓扑顺序: {order}")

            # 两阶段：预重载通知（任意插件拒绝则取消）
            for name in order:
                results = self._event_registry.emit("plugin:pre_reload", {"plugin": name})
                if any(r is False for r in results):
                    logger.warning(f"[framework] 重载被拒绝: 插件 {name} 的 pre_reload 返回 False")
                    return {"success": False, "message": f"插件 {name} 的重载请求被拒绝"}

            # 执行重载：先卸载再加载
            for name in order:
                logger.info(f"[framework] 重载单插件: {name} (开始)")
                logger.debug(f"[framework] 重载: {name} -> 卸载中...")
                self._emit_frontend("plugin:cleanup", {"name": name})
                self._unload_plugin_internal(name)
                logger.debug(f"[framework] 重载: {name} -> 加载中...")
                result = self._load_plugin_internal(name)
                if result["success"]:
                    logger.info(f"重载插件 {name} 完成")
                else:
                    logger.error(f"重载插件 {name} 加载失败: {result.get('message', '')}")
                logger.info(f"[framework] 重载单插件: {name} (完成)")

            # 两阶段：重载完成通知
            for name in order:
                self._event_registry.emit("plugin:reloaded", {"plugin": name})

            logger.info(f"[framework] 重载全部完成: {plugin_name}")
            return {"success": True, "message": f"插件 {plugin_name} 重载完成"}

    def get_plugin(self, plugin_name: str) -> Plugin | None:
        return self._plugins.get(plugin_name)

    def fire_frontend_ready(self) -> None:
        if self._frontend_ready_fired:
            return
        self._frontend_ready_fired = True
        for name, plugin in list(self._plugins.items()):
            if plugin._status == PluginStatus.ENABLED:
                try:
                    plugin.on_frontend_ready()
                except (RuntimeError, OSError, ValueError, TypeError) as e:
                    logger.warning(f"插件 {name} 的 on_frontend_ready 异常: {e}")
        logger.info("前端就绪事件已触发")

    def get_plugin_info_dict(self, plugin: Plugin) -> dict[str, Any]:
        # 获取插件信息字典，供 API 层使用
        return {
            "name": plugin._name,
            "version": plugin._version,
            "title": plugin._meta.get("title", plugin._name),
            "description": plugin._meta.get("description", ""),
            "author": plugin._meta.get("author", ""),
            "icon": plugin._meta.get("icon", ""),
            "status": plugin._status.value,
            "error": plugin._error,
            "dependencies": plugin._meta.get("dependencies", {}),
            "events": plugin._meta.get("events", {}),
            "services": list(plugin._services.keys()),
            "is_system": plugin._name in self._system_plugins,
        }

    def get_html_slots(self) -> dict[str, list[dict[str, str]]]:
        result: dict[str, list[dict[str, str]]] = {}
        for slot, entries in self._html_slots.items():
            result[slot] = [{"plugin": p, "html": h} for p, h in entries]
        return result

    def clear_plugin_slots(self, plugin_name: str) -> None:
        for slot in list(self._html_slots.keys()):
            self._html_slots[slot] = [(p, h) for p, h in self._html_slots[slot] if p != plugin_name]
            if not self._html_slots[slot]:
                del self._html_slots[slot]
        self._emit_frontend("plugin:slots_cleared", {"plugin": plugin_name})

    def get_routes(self) -> list[dict[str, str]]:
        return list(self._plugin_routes.values())

    def call_command(self, command_name: str, *args: Any, **kwargs: Any) -> Any:
        cmd = self._plugin_commands.get(command_name)
        if cmd is None:
            return {"success": False, "message": f"命令不存在: {command_name}"}
        if not callable(cmd["handler"]):
            return {"success": False, "message": "命令处理器不可调用"}
        try:
            result = cmd["handler"](*args, **kwargs)
            return {"success": True, "data": result}
        except (RuntimeError, OSError, ValueError, TypeError) as e:
            return {"success": False, "message": str(e)}

    def get_commands(self) -> list[dict[str, str]]:
        return [
            {"plugin": c["plugin"], "name": c["name"], "description": c["description"]}
            for c in self._plugin_commands.values()
        ]

    def shutdown(self) -> None:
        self._shutting_down = True
        logger.info("开始关闭插件框架...")

        enabled = [n for n, p in self._plugins.items() if p._status == PluginStatus.ENABLED]
        loaded = [n for n, p in self._plugins.items() if p._status in (PluginStatus.LOADED, PluginStatus.DISABLED)]
        all_plugins = enabled + loaded

        if not enabled and not loaded:
            self._shutdown_cleanup()
            return

        # 拓扑排序
        visited = set()
        order = []

        def visit(name: str) -> None:
            if name in visited:
                return
            visited.add(name)
            for dep_name in self._get_dependents(name):
                if dep_name in all_plugins and dep_name not in visited:
                    visit(dep_name)
            order.append(name)

        for name in all_plugins:
            visit(name)

        logger.info(f"关闭顺序: {order}")

        # 1. 按拓扑顺序 disable（依赖者先 disable）
        for name in order:
            plugin = self._plugins.get(name)
            if plugin and plugin._status == PluginStatus.ENABLED:
                plugin._status = PluginStatus.DISABLING
                try:
                    plugin.on_disable()
                    plugin._status = PluginStatus.DISABLED
                except (RuntimeError, OSError, ValueError, TypeError) as e:
                    logger.warning(f"禁用插件 {name} 失败: {e}")

        # 2. 按拓扑顺序 unload
        for name in order:
            plugin = self._plugins.get(name)
            if plugin:
                plugin._status = PluginStatus.UNLOADING
                try:
                    plugin.on_unload()
                except (RuntimeError, OSError, ValueError, TypeError) as e:
                    logger.warning(f"卸载插件 {name} 失败: {e}")
                # 清理隔离模块
                isolated = getattr(plugin, "_isolated_module", None)
                if isolated:
                    sys.modules.pop(isolated, None)
                    prefix = isolated + "."
                    for key in list(sys.modules.keys()):
                        if key.startswith(prefix):
                            sys.modules.pop(key, None)

        # 3. 卸载系统插件（绕过 _unload_plugin_internal 的保护）
        for name in list(self._system_plugins):
            plugin = self._plugins.get(name)
            if not plugin:
                continue
            if plugin._status == PluginStatus.ENABLED:
                plugin._status = PluginStatus.DISABLING
                try:
                    plugin.on_disable()
                except (RuntimeError, OSError, ValueError, TypeError) as e:
                    logger.warning(f"关闭系统插件 {name} 禁用失败: {e}")
            plugin._status = PluginStatus.UNLOADING
            try:
                plugin.on_unload()
            except (RuntimeError, OSError, ValueError, TypeError) as e:
                logger.warning(f"关闭系统插件 {name} 卸载失败: {e}")
            isolated = getattr(plugin, "_isolated_module", None)
            if isolated:
                sys.modules.pop(isolated, None)
                prefix = isolated + "."
                for key in list(sys.modules.keys()):
                    if key.startswith(prefix):
                        sys.modules.pop(key, None)

        self._shutdown_cleanup()
        logger.info("插件框架已关闭")


    def _load_system_plugins(self) -> None:
        if self._system_plugins_dir is None or not self._system_plugins_dir.is_dir():
            return
        for d in sorted(self._system_plugins_dir.iterdir()):
            if not d.is_dir():
                continue
            manifest = d / "plugin.json"
            if not manifest.exists():
                continue
            try:
                data = json.loads(manifest.read_text("utf-8"))
                name = data.get("name", d.name)
            except (json.JSONDecodeError, OSError):
                logger.warning(f"解析系统插件 {d.name} 的 manifest 失败")
                continue
            # 检查是否被禁用
            config = self._load_plugin_config(name)
            if config.get("_system_disabled"):
                logger.info(f"系统插件已禁用，跳过: {name}")
                continue
            self._system_plugins.add(name)
            logger.info(f"发现系统插件: {name}")

    def _load_plugin_config(self, plugin_name: str) -> dict[str, Any]:
        path = self._config_root / f"{plugin_name}.json"
        if path.exists():
            try:
                return json.loads(path.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_plugin_config(self, plugin_name: str, values: dict[str, Any]) -> None:
        config_path = self._config_root / f"{plugin_name}.json"
        try:
            config_path.write_text(json.dumps(values, ensure_ascii=False, indent=2), "utf-8")
        except OSError as e:
            logger.error(f"保存插件配置 [{plugin_name}] 失败: {e}")

    def _resolve_entry(self, entry_point: str, plugin_dir: Path, plugin_name: str) -> type:
        if ":" not in entry_point:
            raise ImportError(f"entry_point 格式错误 [{entry_point}]，应为 module:class")

        module_path, class_name = entry_point.split(":", 1)
        module_file = plugin_dir / (module_path.replace(".", "/") + ".py")
        if not module_file.exists():
            raise ImportError(f"插件入口文件不存在: {module_file}")

        # 隔离命名空间，避免不同插件间的模块名冲突
        isolated_name = f"_plugin_{plugin_name}"

        # 重载时清除旧模块缓存，确保拿到最新代码
        if isolated_name in sys.modules:
            sys.modules.pop(isolated_name)
            prefix = isolated_name + "."
            for key in list(sys.modules.keys()):
                if key.startswith(prefix):
                    sys.modules.pop(key, None)

        try:
            spec = importlib.util.spec_from_file_location(isolated_name, str(module_file))
            if spec is None or spec.loader is None:
                raise ImportError(f"无法加载模块: {module_path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[isolated_name] = module
            spec.loader.exec_module(module)
            cls = getattr(module, class_name)
            if not (isinstance(cls, type) and issubclass(cls, Plugin)):
                raise TypeError(f"入口类 {class_name} 不是 Plugin 的子类")
            return cls
        except (ImportError, AttributeError, TypeError, OSError, ValueError) as e:
            sys.modules.pop(isolated_name, None)
            raise ImportError(f"加载插件入口失败 [{entry_point}]: {e}") from e

    def _resolve_dependencies(self, plugin_name: str, loading_set: set | None = None) -> list[str]:
        if loading_set is None:
            loading_set = set()
        if plugin_name in loading_set:
            raise RuntimeError(f"检测到循环依赖: {plugin_name}")

        plugin = self._plugins.get(plugin_name)
        if not plugin:
            return []

        loading_set.add(plugin_name)
        deps = plugin.meta.get("dependencies", {}).get("plugins", {})
        order = []
        for dep_name in deps:
            dep_order = self._resolve_dependencies(dep_name, loading_set)
            order.extend(d for d in dep_order if d not in order)
            if dep_name not in order:
                order.append(dep_name)

        loading_set.discard(plugin_name)
        return order

    def _get_dependents(self, plugin_name: str) -> list[str]:
        dependents = []
        for name, plugin in self._plugins.items():
            plugin_deps = plugin.meta.get("dependencies", {}).get("plugins", {})
            if plugin_name in plugin_deps:
                dependents.append(name)
        return dependents

    def _resolve_plugin_libs(self, plugin_name: str) -> dict[str, Path]:
        plugin = self._plugins.get(plugin_name)
        if not plugin:
            return {}
        third_party = plugin.meta.get("dependencies", {}).get("third_party", {})
        libs = {}
        changed = False
        for pkg_name, _version_constraint in third_party.items():
            cached = self._deps_meta.get("cached", {}).get(pkg_name)
            pkg_dir = self._cache_root / pkg_name
            if not cached and pkg_dir.exists():
                # 自动发现缓存目录中的包并补充记录
                self._deps_meta.setdefault("cached", {})[pkg_name] = {"path": str(pkg_dir)}
                changed = True
                cached = True
            if cached and pkg_dir.exists():
                init_file = pkg_dir / "__init__.py"
                if init_file.exists():
                    libs[pkg_name] = init_file
                else:
                    libs[pkg_name] = pkg_dir
        if changed:
            try:
                self._deps_meta_path.write_text(json.dumps(self._deps_meta, ensure_ascii=False, indent=2), "utf-8")
            except OSError as e:
                logger.error(f"保存依赖元数据失败: {e}")
        return libs

    def _load_plugin_internal(self, plugin_name: str) -> dict[str, Any]:
        if plugin_name in self._plugins and self._plugins[plugin_name].status != PluginStatus.UNLOADED:
            return {"success": False, "message": f"插件 {plugin_name} 已加载"}

        # 系统插件：从 system_plugins_dir 查找 manifest
        if plugin_name in self._system_plugins:
            manifest_path = self._system_plugins_dir / plugin_name / "plugin.json" if self._system_plugins_dir else None
            if manifest_path is None or not manifest_path.exists():
                return {"success": False, "message": f"未找到系统插件: {plugin_name}"}
        else:
            manifest_path = None
            for d in self._plugins_dir.iterdir():
                if d.is_dir():
                    m = d / "plugin.json"
                    if m.exists():
                        try:
                            data = json.loads(m.read_text("utf-8"))
                            if data.get("name") == plugin_name:
                                manifest_path = m
                                break
                        except (json.JSONDecodeError, OSError):
                            continue

        if manifest_path is None:
            return {"success": False, "message": f"未找到插件: {plugin_name}"}

        try:
            manifest_data = json.loads(manifest_path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            return {"success": False, "message": f"解析 manifest 失败: {e}"}

        try:
            entry_point = manifest_data.get("entry_point")
            if not entry_point:
                return {"success": False, "message": "manifest 中缺少 entry_point"}

            plugin_dir = manifest_path.parent
            cls = self._resolve_entry(entry_point, plugin_dir, plugin_name)

            plugin = cls(self)
            plugin._name = manifest_data.get("name", plugin_name)
            plugin._version = manifest_data.get("version", "0.0.0")
            plugin._meta = manifest_data
            plugin._status = PluginStatus.LOADING
            plugin._isolated_module = f"_plugin_{plugin_name}"
            self._plugins[plugin_name] = plugin
            self._plugin_dirs[plugin_name] = plugin_dir

            plugin.on_load()

            # 异步 on_load：fire-and-forget，不阻塞主流程
            async def _run_async_method(plugin: Plugin, method_name: str) -> None:
                method = getattr(plugin, method_name, None)
                if method is not None and callable(method):
                    try:
                        await method()
                    except (RuntimeError, OSError, ValueError, TypeError) as e:
                        logger.error(f"插件 {plugin._name} 的 {method_name} 异常: {e}")

            loop = _get_event_loop()
            if loop is not None:
                _ = loop.create_task(_run_async_method(plugin, "async_on_load"))

            plugin._status = PluginStatus.LOADED

            libs = self._resolve_plugin_libs(plugin_name)
            if libs:
                self._importer.register_plugin(plugin_name, libs)

            try:
                self._enable_plugin_internal(plugin_name)
            except (RuntimeError, OSError, ValueError, TypeError) as e:
                logger.warning(f"插件 {plugin_name} 加载成功但启用失败: {e}")

            logger.info(f"插件已加载: {plugin._name} v{plugin._version}")
            return {"success": True, "message": f"插件 {plugin_name} 已加载", "data": self.get_plugin_info_dict(plugin)}

        except (ImportError, TypeError, AttributeError, OSError, RuntimeError) as e:
            if plugin_name in self._plugins:
                self._plugins[plugin_name]._status = PluginStatus.ERROR
                self._plugins[plugin_name]._error = str(e)
            logger.error(f"加载插件 {plugin_name} 失败: {e}")
            return {"success": False, "message": str(e)}

    def _enable_plugin_internal(self, plugin_name: str, _enabling: set[str] | None = None) -> dict[str, Any]:
        if _enabling is None:
            _enabling = set()
        plugin = self._plugins.get(plugin_name)
        if not plugin:
            return {"success": False, "message": f"插件 {plugin_name} 未加载"}

        if plugin._status == PluginStatus.ENABLED:
            return {"success": True, "message": f"插件 {plugin_name} 已处于启用状态"}

        deps = plugin.meta.get("dependencies", {}).get("plugins", {})
        for dep_name, _constraint in deps.items():
            dep = self._plugins.get(dep_name)
            if not dep or dep.status != PluginStatus.ENABLED:
                if dep_name in _enabling:
                    return {"success": False, "message": f"检测到循环依赖: {dep_name}"}
                _enabling.add(dep_name)
                result = self._enable_plugin_internal(dep_name, _enabling)
                if not result["success"]:
                    return {"success": False, "message": f"依赖插件 {dep_name} 启用失败: {result.get('message', '')}"}

        plugin._status = PluginStatus.ENABLING
        try:
            plugin._bind_pending_handlers()
            plugin.on_enable()
            plugin._status = PluginStatus.ENABLED
            # 系统插件启用后清除禁用标记
            if plugin_name in self._system_plugins:
                config = self._load_plugin_config(plugin_name)
                if "_system_disabled" in config:
                    del config["_system_disabled"]
                    self._save_plugin_config(plugin_name, config)
            self._event_registry.emit("plugin:enabled", {"name": plugin_name, "version": plugin._version})
            logger.info(f"插件已启用: {plugin_name}")
            return {"success": True, "message": f"插件 {plugin_name} 已启用", "data": self.get_plugin_info_dict(plugin)}
        except (RuntimeError, OSError, ValueError, TypeError) as e:
            plugin._status = PluginStatus.ERROR
            plugin._error = str(e)
            self._event_registry.emit("plugin:error", {"name": plugin_name, "error": str(e)})
            logger.error(f"启用插件 {plugin_name} 失败: {e}")
            return {"success": False, "message": str(e)}

    def _disable_plugin_internal(self, plugin_name: str, force: bool = False, notify: bool = True) -> dict[str, Any]:
        plugin = self._plugins.get(plugin_name)
        if not plugin:
            return {"success": False, "message": f"插件 {plugin_name} 未加载"}

        if plugin._status not in (PluginStatus.ENABLED, PluginStatus.ERROR):
            return {"success": True, "message": f"插件 {plugin_name} 当前状态无需禁用"}

        dependents = self._get_dependents(plugin_name)
        enabled_deps = [
            d for d in dependents if self._plugins.get(d) and self._plugins[d].status == PluginStatus.ENABLED
        ]

        # 两阶段：预禁用通知
        if notify and enabled_deps:
            for dep_name in enabled_deps:
                results = self._event_registry.emit("plugin:pre_disable", {"plugin": plugin_name})
                if any(r is False for r in results):
                    logger.info(f"插件 {dep_name} 拒绝了 {plugin_name} 的禁用请求")
                    return {"success": False, "message": f"插件 {dep_name} 拒绝了禁用操作"}

        plugin._status = PluginStatus.DISABLING
        try:
            plugin.on_disable()
            plugin._status = PluginStatus.DISABLED
            # 系统插件禁用后持久化标记
            if plugin_name in self._system_plugins:
                config = self._load_plugin_config(plugin_name)
                config["_system_disabled"] = True
                self._save_plugin_config(plugin_name, config)
            logger.info(f"插件已禁用: {plugin_name}")
            # 两阶段：禁用完成通知
            if notify and enabled_deps:
                for _dep_name in enabled_deps:
                    self._event_registry.emit("plugin:disabled", {"plugin": plugin_name})
            return {"success": True, "message": f"插件 {plugin_name} 已禁用", "data": self.get_plugin_info_dict(plugin)}
        except (RuntimeError, OSError, ValueError, TypeError) as e:
            plugin._status = PluginStatus.ERROR
            plugin._error = str(e)
            logger.error(f"禁用插件 {plugin_name} 失败: {e}")
            return {"success": False, "message": str(e)}

    def _unload_plugin_internal(self, plugin_name: str) -> dict[str, Any]:
        # 系统插件不可卸载
        if plugin_name in self._system_plugins:
            return {"success": False, "message": "系统插件不可卸载"}

        plugin = self._plugins.get(plugin_name)
        if not plugin:
            return {"success": False, "message": f"插件 {plugin_name} 未加载"}

        logger.debug(f"[unload] {plugin_name} 当前状态: {plugin._status.value}")
        if plugin._status == PluginStatus.ENABLED:
            logger.debug(f"[unload] {plugin_name} 调用 _disable_plugin_internal...")
            self._disable_plugin_internal(plugin_name, force=True, notify=False)
            logger.debug(f"[unload] {plugin_name} _disable_plugin_internal 返回, 状态: {plugin._status.value}")

        logger.debug(f"[unload] {plugin_name} 检查状态: {plugin._status.value}")
        if plugin._status in (PluginStatus.LOADED, PluginStatus.DISABLED, PluginStatus.ERROR):
            logger.debug(f"[unload] {plugin_name} 发送 plugin:pre_unload 事件...")
            self._event_registry.emit("plugin:pre_unload", {"name": plugin_name})
            logger.debug(f"[unload] {plugin_name} plugin:pre_unload 事件完成")
            plugin._status = PluginStatus.UNLOADING
            logger.debug(f"[unload] {plugin_name} 调用 on_unload...")
            try:
                plugin.on_unload()
            except (RuntimeError, OSError, ValueError, TypeError) as e:
                logger.warning(f"卸载插件 {plugin_name} 的 on_unload 异常: {e}")
            logger.debug(f"[unload] {plugin_name} on_unload 完成")

            logger.debug(f"[unload] {plugin_name} 清理服务注册...")
            self._service_registry.unregister_by_provider(plugin_name)
            logger.debug(f"[unload] {plugin_name} 清理事件注册...")
            self._event_registry.unregister_by_plugin(plugin_name)
            logger.debug(f"[unload] {plugin_name} 清理导入器...")
            self._importer.unregister_plugin(plugin_name)

            # 清理插件入口模块（隔离命名空间）
            isolated = getattr(plugin, "_isolated_module", None)
            if isolated:
                logger.debug(f"[unload] {plugin_name} 清理隔离模块: {isolated}")
                sys.modules.pop(isolated, None)
                prefix = isolated + "."
                for key in list(sys.modules.keys()):
                    if key.startswith(prefix):
                        sys.modules.pop(key, None)

            # 清理路由、命令、插槽、设置
            logger.debug(f"[unload] {plugin_name} 清理资源...")
            # 路由
            keys_to_remove = [k for k in self._plugin_routes if k.startswith(f"{plugin_name}:")]
            removed_routes = []
            for key in keys_to_remove:
                removed = self._plugin_routes.pop(key, None)
                if removed:
                    removed_routes.append(removed)
            if removed_routes:
                for route in removed_routes:
                    self._emit_frontend("plugin:route_unregistered", {"plugin": plugin_name, "path": route["path"]})

            # 命令
            cmd_keys = [k for k in self._plugin_commands if k.startswith(f"{plugin_name}:")]
            for key in cmd_keys:
                self._plugin_commands.pop(key, None)

            # 插槽 HTML
            self.clear_plugin_slots(plugin_name)

            # 设置
            self._plugin_settings.pop(plugin_name, None)
            logger.debug(f"[unload] {plugin_name} 资源清理完成")

            self._plugins.pop(plugin_name, None)
            self._plugin_dirs.pop(plugin_name, None)
            logger.info(f"插件已卸载: {plugin_name}")
            return {"success": True, "message": f"插件 {plugin_name} 已卸载"}

        logger.debug(f"[unload] {plugin_name} 状态不匹配，直接移除")
        self._plugins.pop(plugin_name, None)
        self._plugin_dirs.pop(plugin_name, None)
        return {"success": True, "message": f"插件 {plugin_name} 已移除"}

    def _emit_frontend(self, event: str, payload: dict[str, Any]) -> None:
        # 安全地向前端推送事件，忽略关闭状态和导入错误
        if self._shutting_down:
            return
        with contextlib.suppress(ImportError, RuntimeError, OSError):
            from ..api.events import emit
            emit(event, payload)

    def _register_plugin_settings(self, plugin_name: str, schema: dict[str, Any]) -> None:
        if plugin_name not in self._plugin_settings:
            self._plugin_settings[plugin_name] = {"schema": {}, "values": {}}
        self._plugin_settings[plugin_name]["schema"] = schema
        # 从磁盘加载已保存的配置值
        saved = self._load_plugin_config(plugin_name)
        if saved:
            self._plugin_settings[plugin_name]["values"] = saved
        self._event_registry.emit("plugin:settings_registered", {"plugin": plugin_name, "schema": schema})

    def _get_plugin_setting(self, plugin_name: str, key: str, default: Any = None) -> Any:
        return self._plugin_settings.get(plugin_name, {}).get("values", {}).get(key, default)

    def _update_plugin_setting(self, plugin_name: str, key: str, value: Any) -> None:
        if plugin_name not in self._plugin_settings:
            self._plugin_settings[plugin_name] = {"schema": {}, "values": {}}
        old = self._plugin_settings[plugin_name]["values"].get(key)
        self._plugin_settings[plugin_name]["values"][key] = value
        # 持久化到磁盘
        self._save_plugin_config(plugin_name, self._plugin_settings[plugin_name]["values"])
        self._event_registry.emit(
            "plugin:settings_changed", {"plugin": plugin_name, "key": key, "old_value": old, "new_value": value}
        )
        self._emit_frontend(
            "plugin:settings_changed", {"plugin": plugin_name, "key": key, "old_value": old, "new_value": value}
        )

    def _inject_html(self, plugin_name: str, slot: str, html: str) -> None:
        self._html_slots.setdefault(slot, []).append((plugin_name, html))
        self._emit_frontend("plugin:html_injected", {"plugin": plugin_name, "slot": slot, "html": html})

    def _register_route(self, plugin_name: str, path: str, title: str, icon: str) -> None:
        key = f"{plugin_name}:{path}"
        self._plugin_routes[key] = {"plugin": plugin_name, "path": path, "title": title, "icon": icon}
        self._emit_frontend(
            "plugin:route_registered", {"plugin": plugin_name, "path": path, "title": title, "icon": icon}
        )

    def _unregister_route(self, plugin_name: str, path: str) -> None:
        key = f"{plugin_name}:{path}"
        removed = self._plugin_routes.pop(key, None)
        if removed:
            self._emit_frontend("plugin:route_unregistered", {"plugin": plugin_name, "path": path})

    def _register_command(self, plugin_name: str, name: str, handler: Any, description: str) -> None:
        key = f"{plugin_name}:{name}"
        self._plugin_commands[key] = {
            "plugin": plugin_name,
            "name": name,
            "handler": handler,
            "description": description,
        }

    def _shutdown_cleanup(self) -> None:
        # 清理所有注册资源
        self._plugins.clear()
        self._plugin_dirs.clear()
        self._plugin_routes.clear()
        self._plugin_commands.clear()
        self._html_slots.clear()
        self._plugin_settings.clear()
        self._service_registry._services.clear()
        self._event_registry._events.clear()
        self._event_registry._subscribers.clear()

        # 清理 importer
        if hasattr(self._importer, "_importers"):
            for info in list(self._importer._importers.values()):
                finder = info.get("finder")
                if finder and finder in sys.meta_path:
                    sys.meta_path.remove(finder)
        self._importer = PluginImporter(self._cache_root)
