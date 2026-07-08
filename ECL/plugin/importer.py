import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

from ..common.logger import get_logger

logger = get_logger("plugin.importer")


class PluginImporter:
    def __init__(self, cache_root: str | Path):
        self._cache_root = Path(cache_root)
        self._plugin_libs: dict[str, dict[str, Path]] = {}
        self._importers: dict[str, dict[str, Any]] = {}

    def _isolated_key(self, plugin_name: str, package_name: str) -> str:
        return f"_plugin_{plugin_name}_{package_name}"

    def register_plugin(self, plugin_name: str, libs: dict[str, Path]) -> None:
        self._plugin_libs[plugin_name] = libs
        _importer = _PluginMetaPathFinder(plugin_name, libs)
        self._importers[plugin_name] = {"finder": _importer, "libs": libs}
        sys.meta_path.append(_importer)

    def unregister_plugin(self, plugin_name: str) -> None:
        importer_info = self._importers.pop(plugin_name, None)
        if importer_info:
            finder = importer_info["finder"]
            if finder in sys.meta_path:
                sys.meta_path.remove(finder)
            # 清理该插件在 sys.modules 中注册的隔离模块
            prefix = self._isolated_key(plugin_name, "")
            for key in list(sys.modules.keys()):
                if key.startswith(prefix):
                    sys.modules.pop(key, None)
        self._plugin_libs.pop(plugin_name, None)

    def import_package(self, package_name: str, plugin_name: str):
        libs = self._plugin_libs.get(plugin_name, {})
        if package_name not in libs:
            return importlib.import_module(package_name)

        isolated = self._isolated_key(plugin_name, package_name)
        if isolated in sys.modules:
            return sys.modules[isolated]

        # 检查原始包名是否已被占用
        if package_name in sys.modules:
            logger.warning(f"包名冲突: {package_name} 已被其他模块占用，插件 {plugin_name} 使用隔离命名空间")

        pkg_path = libs[package_name]
        spec = importlib.util.spec_from_file_location(isolated, str(pkg_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"无法为插件 {plugin_name} 加载包 {package_name}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[isolated] = module
        spec.loader.exec_module(module)
        return module


class _PluginMetaPathFinder(importlib.abc.MetaPathFinder):
    def __init__(self, plugin_name: str, libs: dict[str, Path]):
        self.plugin_name = plugin_name
        self.libs = libs

    def find_spec(self, fullname, path, target=None):
        pkg_name = fullname.split(".")[0]
        if pkg_name in self.libs:
            lib_path = self.libs[pkg_name]
            if lib_path.is_file():
                return importlib.util.spec_from_file_location(fullname, str(lib_path))
            elif lib_path.is_dir():
                init_file = lib_path / "__init__.py"
                if init_file.exists():
                    return importlib.util.spec_from_file_location(
                        fullname, str(init_file), submodule_search_locations=[str(lib_path)]
                    )
        return None
