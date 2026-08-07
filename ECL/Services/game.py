from __future__ import annotations

import asyncio
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from threading import Event, RLock, Thread
from time import monotonic
from typing import Any
from uuid import uuid4

import httpx
from anyio import to_thread

from ECL.Events import EventBus
from ECL.Game.Core.Downloader import Downloader
from ECL.Game.Core.ECLauncherCore import LaunchConfig, build_minecraft_cmd
from ECL.Game.Core.FilesChecker import FilesChecker
from ECL.Game.Core.GetGames import GetGames
from ECL.Game.Core.InstancesManager import InstancesManager
from ECL.Game.Core.LoaderInstaller import LoaderInstaller
from ECL.Game.Core.NetLibs import ApiUrlConfig, BaseApiClient, BmclApiUrl
from ECL.Game.Utils.JavaScanner import JavaScanner
from ECL.Game.Utils.SearchMinecraft import SearchMinecraft
from ECL.Infrastructure import get_logger
from ECL.Services.accounts import AccountManager
from ECL.Services.authlib import AuthlibError, AuthlibInjector

ApiClientFactory = Callable[[ApiUrlConfig], BaseApiClient]
DownloaderFactory = Callable[..., Downloader]
CommandBuilder = Callable[[LaunchConfig], str]
SearchFactory = Callable[[Path], Any]
JavaScannerFactory = Callable[..., JavaScanner]

_VERSION_TYPE_MAP = {
    "release": "release",
    "snapshot": "snapshot",
    "foolday": "april_fools",
    "beta": "old_beta",
    "alpha": "old_alpha",
}
_LOADER_NAME_MAP = {
    "neoforged": "NeoForge",
    "neoforge": "NeoForge",
    "forge": "Forge",
    "fabric": "Fabric",
    "legacyfabric": "Fabric",
    "babric": "Fabric",
    "quilt": "Quilt",
    "optifine": "OptiFine",
    "liteloader": "LiteLoader",
    "cleanroom": "Cleanroom",
}


class GameServiceError(Exception):
    def __init__(self, message: str, error_code: str = "GAME_OPERATION_FAILED"):
        super().__init__(message)
        self.error_code = error_code


class VersionScanError(GameServiceError):
    def __init__(self, message: str, error_code: str = "VERSION_SCAN_FAILED"):
        super().__init__(message, error_code)


@dataclass
class _CoreContext:
    api_client: BaseApiClient
    files_checker: FilesChecker
    games: GetGames


class GameService:
    """Minecraft 版本查询、安装、校验和启动的统一门面。"""

    def __init__(
        self,
        accounts: AccountManager,
        *,
        search_factory: SearchFactory = SearchMinecraft,
        instances_manager: InstancesManager | None = None,
        api_client_factory: ApiClientFactory = BaseApiClient,
        downloader_factory: DownloaderFactory = Downloader,
        command_builder: CommandBuilder = build_minecraft_cmd,
        java_scanner_factory: JavaScannerFactory = JavaScanner,
        data_path: Path | str | None = None,
        authlib_injector: AuthlibInjector | None = None,
        enable_version_watcher: bool | None = None,
        version_watch_interval: float = 0.75,
        version_watch_debounce: float = 0.75,
    ):
        self.logger = get_logger("GameService")
        self.accounts = accounts
        self._search_factory = search_factory
        self.instances = instances_manager or InstancesManager()
        self._api_client_factory = api_client_factory
        self._downloader_factory = downloader_factory
        self._command_builder = command_builder
        self._java_scanner_factory = java_scanner_factory
        self._java_cache_file = Path(data_path) / "java_cache.json" if data_path else None
        self.authlib_injector = authlib_injector or (AuthlibInjector(data_path) if data_path else None)
        self._java_runtimes: list[Any] = []
        self._contexts: dict[tuple[str, str], _CoreContext] = {}
        self._active_downloads: dict[str, Downloader] = {}
        self._install_tasks: dict[str, asyncio.Task[None]] = {}
        self._instance_versions: dict[str, str] = {}
        self._launch_cancel_event: Event | None = None
        self._version_scan_cache: dict[str, list[dict[str, Any]]] = {}
        self._version_watch_paths: dict[str, Path] = {}
        self._version_watch_snapshots: dict[str, tuple[tuple[str, int, int], ...]] = {}
        self._version_watch_pending: dict[str, float] = {}
        self._version_watcher_enabled = data_path is not None if enable_version_watcher is None else enable_version_watcher
        self._version_watch_interval = max(0.1, float(version_watch_interval))
        self._version_watch_debounce = max(0.0, float(version_watch_debounce))
        self._version_watch_stop = Event()
        self._version_watch_thread: Thread | None = None
        self._lock = RLock()

    @staticmethod
    def _normalize_source(source: Any) -> str:
        normalized = str(source or "official").strip().casefold()
        if normalized not in {"official", "bmclapi"}:
            raise GameServiceError("未知的下载源", "INVALID_DOWNLOAD_SOURCE")
        return normalized

    @staticmethod
    def _normalize_game_path(value: Any) -> Path:
        if not isinstance(value, (str, Path)) or not str(value).strip():
            raise GameServiceError("未设置 Minecraft 游戏目录", "GAME_PATH_REQUIRED")
        path = Path(str(value).strip()).expanduser()
        if path.name.casefold() == "versions":
            path = path.parent
        return path.resolve(strict=False)

    @staticmethod
    def _normalize_version_name(value: Any, field_name: str = "版本名称") -> str:
        if not isinstance(value, str) or not value.strip():
            raise GameServiceError(f"{field_name}不能为空", "INVALID_VERSION_NAME")
        name = value.strip()
        if name in {".", ".."} or Path(name).name != name or any(character in name for character in ("/", "\\", "\0")):
            raise GameServiceError(f"{field_name}格式无效", "INVALID_VERSION_NAME")
        return name

    @staticmethod
    def _normalize_positive_int(value: Any, default: int, minimum: int, maximum: int, field_name: str) -> int:
        if value in (None, ""):
            return default
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise GameServiceError(f"{field_name}必须是整数", "INVALID_GAME_OPTION") from exc
        if not minimum <= normalized <= maximum:
            raise GameServiceError(
                f"{field_name}必须在 {minimum} 到 {maximum} 之间",
                "INVALID_GAME_OPTION",
            )
        return normalized

    @staticmethod
    def _normalize_string_list(value: Any, field_name: str) -> list[str]:
        if value in (None, ""):
            return []
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise GameServiceError(f"{field_name}必须是字符串数组", "INVALID_GAME_OPTION")
        return [item.strip() for item in value if item.strip()]

    @staticmethod
    def _api_config(source: str) -> ApiUrlConfig:
        return BmclApiUrl() if source == "bmclapi" else ApiUrlConfig()

    def _context(self, game_path: Any, source: Any = "official") -> _CoreContext:
        path = self._normalize_game_path(game_path)
        normalized_source = self._normalize_source(source)
        key = (str(path).casefold(), normalized_source)
        with self._lock:
            existing = self._contexts.get(key)
            if existing is not None:
                return existing

            api_client = self._api_client_factory(self._api_config(normalized_source))
            files_checker = FilesChecker(api_client)
            loader_installer = LoaderInstaller(
                files_checker,
                self.instances,
                path,
                log_callback=lambda message: self.logger.info("%s", message),
            )
            context = _CoreContext(
                api_client=api_client,
                files_checker=files_checker,
                games=GetGames(files_checker, loader_installer, path),
            )
            self._contexts[key] = context
            return context

    def _query_context(self, source: Any = "official") -> _CoreContext:
        # GetGames 的查询方法仍要求 game_path；查询阶段使用一个不会写入的占位路径。
        return self._context(Path.cwd() / ".minecraft", source)

    @staticmethod
    def _catalog_item(item: dict[str, Any], version_type: str) -> dict[str, Any]:
        return {
            "id": str(item.get("id") or ""),
            "type": version_type,
            "releaseTime": str(item.get("releaseTime") or ""),
        }

    def minecraft_versions_classified(self, source: Any = "official") -> dict[str, list[dict[str, Any]]]:
        """查询并按正式版、快照和旧版本分类 Minecraft 版本。"""
        raw = self._query_context(source).games.get_minecraft_versions()
        groups = {
            "release": ("Release", "release"),
            "snapshot": ("Snapshot", "snapshot"),
            "april_fools": ("FoolDays", "april_fools"),
            "old_beta": ("Beta", "old_beta"),
            "old_alpha": ("Alpha", "old_alpha"),
        }
        catalog: dict[str, list[dict[str, Any]]] = {"all": []}
        type_by_id: dict[str, str] = {}
        for output_name, (core_name, version_type) in groups.items():
            values = [
                self._catalog_item(item, version_type)
                for item in raw.get(core_name, [])
                if isinstance(item, dict) and item.get("id")
            ]
            catalog[output_name] = values
            type_by_id.update({item["id"]: version_type for item in values})
        catalog["all"] = [
            self._catalog_item(item, type_by_id.get(str(item.get("id") or ""), "release"))
            for item in raw.get("All", [])
            if isinstance(item, dict) and item.get("id")
        ]
        return catalog

    def minecraft_versions(self, filter_type: Any = None, source: Any = "official") -> list[dict[str, Any]]:
        """查询 Minecraft 版本，可按版本类别过滤。"""
        catalog = self.minecraft_versions_classified(source)
        normalized_filter = str(filter_type or "all").strip().casefold().replace("-", "_")
        aliases = {
            "fooldays": "april_fools",
            "beta": "old_beta",
            "alpha": "old_alpha",
        }
        key = aliases.get(normalized_filter, normalized_filter)
        if key not in catalog:
            raise GameServiceError("未知的版本分类", "INVALID_VERSION_FILTER")
        return catalog[key]

    def loader_versions(self, loader_type: Any, game_version: Any, source: Any = "official") -> list[Any]:
        """查询指定游戏版本兼容的加载器版本。"""
        loader = str(loader_type or "").strip().casefold()
        version = self._normalize_version_name(game_version, "Minecraft 版本")
        games = self._query_context(source).games
        if loader == "fabric":
            result = games.get_fabric_versions(version)
        elif loader == "forge":
            result = games.get_forge_versions(version)
        elif loader in {"neoforge", "neoforged"}:
            result = games.get_neoforged_versions(version)
        elif loader == "quilt":
            result = games.get_quilt_versions(version)
        else:
            raise GameServiceError(f"暂不支持加载器: {loader_type}", "UNSUPPORTED_LOADER")
        if result is None:
            return []
        if isinstance(result, dict):
            values = result.get("All", result.get("all", []))
            return values if isinstance(values, list) else []
        return result if isinstance(result, list) else []

    @staticmethod
    def _normalize_scan_paths(value: Any) -> list[Path]:
        if isinstance(value, (str, Path)):
            raw_paths = [value]
        elif isinstance(value, list):
            raw_paths = value
        else:
            raise VersionScanError("游戏路径必须是字符串或字符串数组", "INVALID_GAME_PATH")

        paths: list[Path] = []
        seen: set[str] = set()
        for raw_path in raw_paths:
            if not isinstance(raw_path, (str, Path)):
                raise VersionScanError("游戏路径数组只能包含字符串", "INVALID_GAME_PATH")
            path_value = str(raw_path).strip()
            if not path_value:
                continue
            path = Path(path_value).expanduser()
            if path.name.casefold() == "versions":
                path = path.parent
            path_key = str(path.resolve(strict=False)).casefold()
            if path_key in seen:
                continue
            seen.add(path_key)
            paths.append(path)
        if not paths:
            raise VersionScanError("至少需要一个有效的游戏路径", "INVALID_GAME_PATH")
        return paths

    @staticmethod
    def _normalize_scanned_loader(value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            return "Vanilla"
        loader = value.strip()
        return _LOADER_NAME_MAP.get(loader.casefold(), loader)

    @staticmethod
    def _normalize_scanned_version(
        game_path: Path,
        version_name: str,
        raw_info: Any,
    ) -> dict[str, Any]:
        info = raw_info if isinstance(raw_info, dict) else {}
        version_path_value = info.get("VersionPath")
        version_path = (
            Path(version_path_value)
            if isinstance(version_path_value, str) and version_path_value.strip()
            else game_path / "versions" / version_name
        )
        json_path = version_path / f"{version_name}.json"
        vanilla_version = info.get("VanillaVersion")
        vanilla_name = (
            vanilla_version.strip()
            if isinstance(vanilla_version, str) and vanilla_version.strip() and vanilla_version != "Unknown"
            else version_name
        )
        version_type = _VERSION_TYPE_MAP.get(str(info.get("VanillaType") or "").casefold(), "release")
        primary_loader = GameService._normalize_scanned_loader(info.get("LoaderType"))
        loader_key = primary_loader.casefold()
        has_optifine = loader_key == "optifine"
        loader_version = str(info.get("LoaderVersion") or "").strip()
        if loader_version == "Unknown":
            loader_version = ""
        required_java_value = str(info.get("RequestJava") or "").strip()
        required_java = int(required_java_value) if required_java_value.isdigit() else None
        return {
            "id": version_name,
            "versionId": version_name,
            "versionType": version_type,
            "path": str(game_path),
            "displayName": version_name,
            "primaryLoader": primary_loader,
            "loaderVersion": loader_version,
            "vanillaName": vanilla_name,
            "requiredJava": required_java,
            "hasForge": loader_key == "forge",
            "hasNeoForge": loader_key == "neoforge",
            "hasFabric": loader_key == "fabric",
            "hasQuilt": loader_key == "quilt",
            "hasOptiFine": has_optifine,
            "isBroken": not json_path.is_file(),
            "jsonPath": str(json_path),
            "sourceName": game_path.name or str(game_path),
        }

    @staticmethod
    def _version_path_key(game_path: Path) -> str:
        return str(game_path.resolve(strict=False)).casefold()

    @staticmethod
    def _version_directory_snapshot(game_path: Path) -> tuple[tuple[str, int, int], ...]:
        """生成轻量版本目录快照，只跟踪目录项和直接 JSON 文件。"""
        versions_path = game_path / "versions"
        records: list[tuple[str, int, int]] = []

        def append_stat(relative_path: str, path: Path) -> None:
            try:
                stat = path.stat()
            except OSError:
                return
            records.append((relative_path, stat.st_mtime_ns, stat.st_size))

        if not versions_path.is_dir():
            return ()
        append_stat(".", versions_path)
        try:
            version_directories = [entry for entry in versions_path.iterdir() if entry.is_dir()]
        except OSError:
            return tuple(records)
        for version_directory in version_directories:
            append_stat(f"{version_directory.name}/", version_directory)
            try:
                json_files = version_directory.glob("*.json")
                for json_file in json_files:
                    if json_file.is_file():
                        append_stat(f"{version_directory.name}/{json_file.name}", json_file)
            except OSError:
                continue
        return tuple(sorted(records))

    def _watch_version_path(self, game_path: Path) -> str:
        key = self._version_path_key(game_path)
        snapshot = self._version_directory_snapshot(game_path)
        thread: Thread | None = None
        with self._lock:
            previous_snapshot = self._version_watch_snapshots.get(key)
            self._version_watch_paths[key] = game_path
            self._version_watch_snapshots[key] = snapshot
            if previous_snapshot is not None and previous_snapshot != snapshot:
                self._version_scan_cache.pop(key, None)
                self._version_watch_pending[key] = monotonic()
            if self._version_watcher_enabled and (
                self._version_watch_thread is None or not self._version_watch_thread.is_alive()
            ):
                self._version_watch_stop.clear()
                thread = Thread(target=self._version_watch_loop, name="ECL-VersionWatcher", daemon=True)
                self._version_watch_thread = thread
        if thread is not None:
            thread.start()
        return key

    def _poll_version_changes(self, now: float | None = None) -> list[str]:
        current_time = monotonic() if now is None else now
        with self._lock:
            watched_paths = list(self._version_watch_paths.items())

        changed_paths: list[str] = []
        for key, game_path in watched_paths:
            snapshot = self._version_directory_snapshot(game_path)
            with self._lock:
                if key not in self._version_watch_paths:
                    continue
                previous_snapshot = self._version_watch_snapshots.get(key)
                if previous_snapshot != snapshot:
                    self._version_watch_snapshots[key] = snapshot
                    self._version_scan_cache.pop(key, None)
                    self._version_watch_pending[key] = current_time
                pending_since = self._version_watch_pending.get(key)
                if pending_since is None or current_time - pending_since < self._version_watch_debounce:
                    continue
                self._version_watch_pending.pop(key, None)
                changed_paths.append(str(game_path.resolve(strict=False)))

        for game_path in changed_paths:
            EventBus().emit("game:versions_changed", {"gamePath": game_path})
        return changed_paths

    def _version_watch_loop(self) -> None:
        while not self._version_watch_stop.wait(self._version_watch_interval):
            try:
                self._poll_version_changes()
            except Exception:
                self.logger.exception("监视 Minecraft 版本目录失败")

    def _scan_game_path(self, game_path: Path) -> list[dict[str, Any]]:
        versions_path = game_path / "versions"
        if not versions_path.is_dir():
            self.logger.debug("跳过不存在的版本目录: %s", versions_path)
            return []
        try:
            versions = self._search_factory(game_path).search_minecraft()
        except (OSError, TypeError, ValueError) as exc:
            self.logger.exception("扫描 Minecraft 版本失败: %s", game_path)
            raise VersionScanError(f"扫描游戏目录失败: {game_path}: {exc}") from exc
        if not isinstance(versions, dict):
            raise VersionScanError(f"版本扫描器返回了无效数据: {game_path}")
        return [
            self._normalize_scanned_version(game_path, version_name.strip(), info)
            for version_name, info in versions.items()
            if isinstance(version_name, str) and version_name.strip()
        ]

    def scan_versions(self, paths: Any, *, force: bool = False) -> list[dict[str, Any]]:
        """扫描 Minecraft 目录；目录未变化时复用缓存结果。"""
        scanned_versions: list[dict[str, Any]] = []
        for game_path in self._normalize_scan_paths(paths):
            key = self._watch_version_path(game_path)
            with self._lock:
                cached_versions = None if force else self._version_scan_cache.get(key)
            if cached_versions is None:
                versions = self._scan_game_path(game_path)
                with self._lock:
                    self._version_scan_cache[key] = deepcopy(versions)
                    self._version_watch_snapshots[key] = self._version_directory_snapshot(game_path)
                    self._version_watch_pending.pop(key, None)
            else:
                versions = deepcopy(cached_versions)
            scanned_versions.extend(versions)
        return sorted(
            scanned_versions,
            key=lambda item: (str(item["sourceName"]).casefold(), str(item["displayName"]).casefold()),
        )

    @staticmethod
    def _java_major_version(version: Any) -> int:
        value = str(version or "").strip()
        if value.startswith("1."):
            value = value[2:]
        match = re.match(r"\d+", value)
        return int(match.group()) if match else 0

    def scan_java(self, user_java_paths: list[str] | None = None) -> list[dict[str, Any]]:
        """扫描 Java 运行时。"""
        user_paths = [path for path in user_java_paths or [] if isinstance(path, str) and path.strip()]
        scanner = self._java_scanner_factory(
            cache_file=self._java_cache_file,
            user_java_paths=user_paths,
        )
        self._java_runtimes = scanner.scan()
        installations = []
        for runtime in self._java_runtimes:
            architecture = str(runtime.architecture or "unknown").lower()
            architecture = {
                "amd64": "x64",
                "x86_64": "x64",
                "aarch64": "arm64",
                "i386": "x86",
                "i686": "x86",
            }.get(architecture, architecture)
            path = str(runtime.path)
            installations.append(
                {
                    "path": path,
                    "version": str(runtime.version),
                    "major_version": self._java_major_version(runtime.version),
                    "java_type": runtime.vendor or ("JDK" if runtime.is_jdk else "JRE"),
                    "arch": architecture,
                    "sources": ["user" if path in user_paths else "system"],
                }
            )
        return sorted(
            installations,
            key=lambda item: (-item["major_version"], item["java_type"].casefold(), item["path"].casefold()),
        )

    def _emit_install_progress(
        self,
        task_id: str,
        phase: str,
        message: str,
        *,
        done: int | None = None,
        total: int | None = None,
        subtask: str | None = None,
        error_code: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "phase": phase,
            "task_id": task_id,
            "message": message,
        }
        if done is not None:
            payload["done"] = done
        if total is not None:
            payload["total"] = total
        if subtask:
            payload["subtask"] = subtask
        if error_code:
            payload["errorCode"] = error_code
        EventBus().emit("game:install_progress", payload)

    def install_version(
        self,
        body: dict[str, Any],
        *,
        game_path: Any,
        source: Any = "official",
        java_path: str | None = None,
    ) -> dict[str, str]:
        """开始安装版本，返回任务 ID 和最终保存的版本名称。"""
        path = self._normalize_game_path(game_path)
        normalized_source = self._normalize_source(source)
        version_id = self._normalize_version_name(body.get("version_id"), "Minecraft 版本")
        save_name = self._normalize_version_name(body.get("version_name") or version_id)
        loader = str(body.get("loader_type") or "vanilla").strip().casefold()
        if loader in {"", "none"}:
            loader = "vanilla"
        if loader not in {"vanilla", "fabric", "forge", "neoforge", "quilt"}:
            raise GameServiceError(f"暂不支持安装加载器: {body.get('loader_type')}", "UNSUPPORTED_LOADER")

        loader_version = None
        if loader != "vanilla":
            field_name = f"{loader}_version"
            value = body.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise GameServiceError("未选择加载器版本", "LOADER_VERSION_REQUIRED")
            loader_version = value.strip()
        if loader in {"forge", "neoforge"}:
            java_path = self._resolve_java_path(java_path)

        path.mkdir(parents=True, exist_ok=True)
        (path / "versions").mkdir(parents=True, exist_ok=True)
        requested_task_id = body.get("task_id")
        task_id = requested_task_id.strip() if isinstance(requested_task_id, str) else ""
        if not task_id:
            task_id = f"install-{uuid4().hex}"

        loop = asyncio.get_running_loop()
        with self._lock:
            existing = self._install_tasks.get(task_id)
            if existing is not None and not existing.done():
                raise GameServiceError("相同的安装任务已在运行", "INSTALL_ALREADY_RUNNING")
            task = loop.create_task(
                self._run_install(
                    task_id,
                    version_id,
                    save_name,
                    loader,
                    loader_version,
                    path,
                    normalized_source,
                    java_path,
                ),
                name=f"ECLInstall-{task_id}",
            )
            self._install_tasks[task_id] = task
        self.logger.info("开始安装 %s，保存为 %s，加载器: %s", version_id, save_name, loader)
        return {"taskId": task_id, "versionId": version_id, "versionName": save_name}

    async def _run_install(
        self,
        task_id: str,
        version_id: str,
        save_name: str,
        loader: str,
        loader_version: str | None,
        game_path: Path,
        source: str,
        java_path: str | None,
    ) -> None:
        self._emit_install_progress(task_id, "install", "正在读取版本信息", done=0, total=1)
        try:
            games = self._context(game_path, source).games
            if loader == "vanilla":
                download_list = await to_thread.run_sync(
                    games.build_minecraft_download_list,
                    version_id,
                    save_name,
                )
            elif loader == "fabric":
                download_list = await to_thread.run_sync(
                    games.build_fabric_download_list,
                    version_id,
                    loader_version,
                    save_name,
                )
            elif loader == "quilt":
                download_list = await to_thread.run_sync(
                    games.build_quilt_download_list,
                    version_id,
                    loader_version,
                    save_name,
                )
            elif loader == "forge":
                download_list = await to_thread.run_sync(
                    games.build_forge_download_list,
                    version_id,
                    loader_version,
                    java_path,
                    save_name,
                )
            else:
                download_list = await to_thread.run_sync(
                    games.build_neoforged_download_list,
                    version_id,
                    loader_version,
                    java_path,
                    save_name,
                )

            if not download_list:
                self._emit_install_progress(task_id, "done", f"{save_name} 已安装完成", done=1, total=1)
                return

            downloader = self._downloader_factory(
                download_list,
                progress_callback=lambda done, total: self._emit_install_progress(
                    task_id,
                    "download",
                    f"正在下载 {save_name}",
                    done=done,
                    total=total,
                    subtask="download_files",
                ),
            )
            with self._lock:
                self._active_downloads[task_id] = downloader

            self._emit_install_progress(
                task_id,
                "download",
                f"准备下载 {len(download_list)} 个文件",
                done=0,
                total=len(download_list),
                subtask="download_files",
            )
            await downloader.run()
            if downloader.failed_entries:
                failed_url, failed_path = next(iter(downloader.failed_entries))
                raise GameServiceError(
                    f"有 {len(downloader.failed_entries)} 个文件下载失败，例如 {failed_path}（{failed_url}）",
                    "GAME_DOWNLOAD_FAILED",
                )
            self.logger.info("版本安装完成: %s", save_name)
            self._emit_install_progress(task_id, "done", f"{save_name} 已安装完成", done=1, total=1)
        except asyncio.CancelledError:
            self.logger.info("安装任务已取消: %s", task_id)
            self._emit_install_progress(task_id, "error", "安装已取消", error_code="INSTALL_CANCELLED")
        except GameServiceError as exc:
            self.logger.error("版本安装失败 [%s]: %s", exc.error_code, exc)
            self._emit_install_progress(
                task_id,
                "error",
                str(exc),
                done=0,
                total=1,
                error_code=exc.error_code,
            )
        except Exception as exc:
            self.logger.exception("Core 安装版本失败: %s", save_name)
            self._emit_install_progress(
                task_id,
                "error",
                f"安装 {save_name} 失败: {exc}",
                done=0,
                total=1,
                error_code="VERSION_INSTALL_FAILED",
            )
        finally:
            with self._lock:
                self._active_downloads.pop(task_id, None)
                self._install_tasks.pop(task_id, None)

    def uninstall_version(self, version_id: Any, game_path: Any) -> None:
        """从指定 Minecraft 目录卸载版本。"""
        name = self._normalize_version_name(version_id)
        root = self._normalize_game_path(game_path) / "versions"
        target = (root / name).resolve(strict=False)
        if target.parent != root.resolve(strict=False):
            raise GameServiceError("版本目录超出允许范围", "INVALID_VERSION_PATH")
        if not target.exists():
            raise GameServiceError("要卸载的版本不存在", "VERSION_NOT_FOUND")
        try:
            shutil.rmtree(target)
        except OSError as exc:
            raise GameServiceError(f"卸载版本失败: {exc}", "VERSION_UNINSTALL_FAILED") from exc

    def _emit_launch_progress(
        self,
        phase: str,
        message: str,
        percent: int | None = None,
        error_code: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"phase": phase, "message": message}
        if percent is not None:
            payload["percent"] = percent
        if error_code:
            payload["errorCode"] = error_code
        EventBus().emit("game:launch_progress", payload)

    def _resolve_java_path(self, value: Any, required_major: int | None = None) -> str:
        raw_path = str(value or "").strip()
        if raw_path:
            path = Path(raw_path).expanduser()
            if not path.is_file():
                raise GameServiceError("Java 可执行文件不存在", "JAVA_NOT_FOUND")
            return str(path.resolve())

        if not self._java_runtimes:
            self.scan_java()
        candidates = self._java_runtimes
        if required_major:
            candidates = [
                runtime for runtime in candidates if self._java_major_version(runtime.version) >= required_major
            ]
        if not candidates:
            if required_major:
                raise GameServiceError(f"未找到 Java {required_major} 或更高版本", "JAVA_VERSION_NOT_FOUND")
            raise GameServiceError("未找到 Java，请先在设置中选择 Java", "JAVA_NOT_FOUND")
        if required_major:
            runtime = min(
                candidates,
                key=lambda item: (self._java_major_version(item.version), str(item.path).casefold()),
            )
        else:
            runtime = max(candidates, key=lambda item: self._java_major_version(item.version))
        return str(runtime.path)

    async def launch_instance(
        self,
        body: dict[str, Any],
        *,
        game_path: Any,
        source: Any = "official",
        java_path: Any = None,
        memory: Any = 4096,
        width: Any = 854,
        height: Any = 480,
        jvm_args: Any = None,
        game_args: Any = None,
        version_isolation: Any = False,
    ) -> dict[str, str]:
        """检查游戏文件并启动实例。"""
        version_name = self._normalize_version_name(body.get("version_id"))
        path = self._normalize_game_path(game_path)
        version_json = path / "versions" / version_name / f"{version_name}.json"
        if not version_json.is_file():
            raise GameServiceError("游戏版本不存在或版本 JSON 缺失", "VERSION_NOT_FOUND")
        scanned_versions = self._search_factory(path).search_minecraft()
        version_info = scanned_versions.get(version_name, {}) if isinstance(scanned_versions, dict) else {}
        required_java_value = str(version_info.get("RequestJava") or "")
        required_java = int(required_java_value) if required_java_value.isdigit() else None
        java = self._resolve_java_path(java_path, required_java)
        ram = self._normalize_positive_int(memory, 4096, 256, 131072, "游戏内存")
        window_width = self._normalize_positive_int(width, 854, 320, 16384, "窗口宽度")
        window_height = self._normalize_positive_int(height, 480, 240, 16384, "窗口高度")
        custom_jvm_args = self._normalize_string_list(jvm_args, "JVM 参数")
        custom_game_args = self._normalize_string_list(game_args, "游戏参数")
        context = self._context(path, self._normalize_source(source))
        isolated = bool(version_isolation)

        cancel_event = Event()
        with self._lock:
            if self._launch_cancel_event is not None:
                raise GameServiceError("已有游戏启动任务正在运行", "LAUNCH_ALREADY_RUNNING")
            self._launch_cancel_event = cancel_event

        try:
            self._emit_launch_progress("preparing", f"正在准备启动 {version_name}", 3)
            current_account_getter = getattr(self.accounts, "current_account", None)
            current_account = current_account_getter() if callable(current_account_getter) else None
            account_type = current_account.get("type") if isinstance(current_account, dict) else None
            if account_type == "microsoft":
                self._emit_launch_progress(
                    "microsoft_token",
                    "正在检查正版登录令牌，过期时将自动刷新",
                    7,
                )
            elif account_type == "authlib":
                self._emit_launch_progress(
                    "authlib_token",
                    "正在验证外置登录令牌，过期时将自动刷新",
                    7,
                )
            elif account_type == "offline":
                self._emit_launch_progress("offline_account", "正在读取离线账户信息", 7)
            else:
                self._emit_launch_progress("account", "正在验证游戏账户", 7)
            credentials = await to_thread.run_sync(self.accounts.get_launch_credentials)
            if credentials["user_type"] == "msa":
                self._emit_launch_progress("account_ready", "正版登录令牌已就绪", 17)
            elif credentials["user_type"] == "yggdrasil":
                self._emit_launch_progress("account_ready", "外置登录令牌已就绪", 17)
            else:
                self._emit_launch_progress("account_ready", "离线账户已就绪", 17)
            if cancel_event.is_set():
                raise GameServiceError("启动已取消", "LAUNCH_CANCELLED")

            authlib_path = None
            auth_server = None
            if credentials["user_type"] == "yggdrasil":
                if self.authlib_injector is None:
                    raise GameServiceError("未配置外置登录组件目录", "AUTHLIB_INJECTOR_UNAVAILABLE")
                auth_server = credentials.get("auth_server")
                if not auth_server:
                    raise GameServiceError("外置登录认证服务器地址缺失", "AUTHLIB_SERVER_MISSING")
                self._emit_launch_progress("authlib", "正在准备外置登录组件", 20)
                try:
                    authlib_path = await to_thread.run_sync(self.authlib_injector.ensure)
                except (AuthlibError, OSError, KeyError, TypeError, ValueError, httpx.HTTPError) as exc:
                    raise GameServiceError(f"准备外置登录组件失败: {exc}", "AUTHLIB_INJECTOR_FAILED") from exc

            self._emit_launch_progress("checking", "正在检查游戏文件", 25)
            download_list = await to_thread.run_sync(context.files_checker.check_files, path, version_name)
            if cancel_event.is_set():
                raise GameServiceError("启动已取消", "LAUNCH_CANCELLED")
            self._emit_launch_progress(
                "files_checked",
                f"文件检查完成，共需补全 {len(download_list)} 个文件",
                55,
            )
            if download_list:
                downloader = self._downloader_factory(
                    download_list,
                    progress_callback=lambda done, total: self._emit_launch_progress(
                        "downloading",
                        "正在补全游戏文件",
                        55 + int(done * 15 / total) if total else 55,
                    ),
                )
                with self._lock:
                    self._active_downloads["__launch__"] = downloader
                try:
                    await downloader.run()
                except Exception as exc:
                    if cancel_event.is_set():
                        raise GameServiceError("启动已取消", "LAUNCH_CANCELLED") from exc
                    raise
                finally:
                    with self._lock:
                        self._active_downloads.pop("__launch__", None)
                if cancel_event.is_set():
                    raise GameServiceError("启动已取消", "LAUNCH_CANCELLED")
                if downloader.failed_entries:
                    failed_url, failed_path = next(iter(downloader.failed_entries))
                    raise GameServiceError(
                        f"有 {len(downloader.failed_entries)} 个游戏文件补全失败，例如 {failed_path}（{failed_url}）",
                        "GAME_DOWNLOAD_FAILED",
                    )

            self._emit_launch_progress("building_args", "正在生成启动参数", 72)
            launch_config = LaunchConfig(
                java_path=java,
                game_path=path,
                version_name=version_name,
                use_ram=ram,
                player_name=credentials["player_name"],
                auth_uuid=credentials["uuid"],
                user_type=credentials["user_type"],
                access_token=credentials["access_token"],
                custom_jvm_params=custom_jvm_args or None,
                version_isolation=isolated,
                window_width=window_width,
                window_height=window_height,
                authlib_path=authlib_path,
                yggdrasil_api=auth_server,
            )
            command = await to_thread.run_sync(self._command_builder, launch_config)
            if custom_game_args:
                if sys.platform == "win32":
                    formatted_args = subprocess.list2cmdline(custom_game_args)
                else:
                    formatted_args = shlex.join(custom_game_args)
                command = f"{command} {formatted_args}"
            self._emit_launch_progress("args_built", "启动参数生成完成", 84)
            if cancel_event.is_set():
                raise GameServiceError("启动已取消", "LAUNCH_CANCELLED")

            self._emit_launch_progress("about_to_launch", "即将启动游戏", 94)
            self._emit_launch_progress("launching", "正在创建游戏进程", 97)
            instance_id = self.instances.create_instance(
                instance_name=version_name,
                instance_type="Minecraft",
                args=command,
                cwd=path / "versions" / version_name,
                new_session=True,
                log_callback=lambda line, current_id: self.logger.debug("[%s] %s", current_id, line),
                exit_callback=lambda code, name: self.logger.info("Minecraft %s 已退出，退出码: %s", name, code),
            )
            with self._lock:
                self._instance_versions[instance_id] = version_name
            self._emit_launch_progress("launched", f"{version_name} 已启动", 100)
            return {
                "instanceId": instance_id,
                "versionId": version_name,
                "gamePath": str(path),
            }
        except GameServiceError as exc:
            if exc.error_code != "LAUNCH_CANCELLED":
                self._emit_launch_progress("error", str(exc), 0, exc.error_code)
            raise
        except Exception as exc:
            self.logger.exception("启动 Minecraft 失败")
            error = GameServiceError(f"启动游戏失败: {exc}", "GAME_LAUNCH_FAILED")
            self._emit_launch_progress("error", str(error), 0, error.error_code)
            raise error from exc
        finally:
            with self._lock:
                self._launch_cancel_event = None

    def cancel_launch(self) -> bool:
        """取消正在执行的启动或文件补全任务。"""
        with self._lock:
            cancel_event = self._launch_cancel_event
            downloader = self._active_downloads.get("__launch__")
        if cancel_event is None:
            return False
        cancel_event.set()
        if downloader is not None:
            downloader.stop()
        return True

    def list_instances(self) -> list[dict[str, Any]]:
        """返回由启动器管理的运行中 Minecraft 实例。"""
        raw_instances = self.instances.get_instances_info()
        live_ids = {str(item.get("ID")) for item in raw_instances if item.get("ID")}
        with self._lock:
            for instance_id in list(self._instance_versions):
                if instance_id not in live_ids:
                    self._instance_versions.pop(instance_id, None)
            versions = dict(self._instance_versions)

        result = []
        for item in raw_instances:
            if item.get("Type") != "Minecraft":
                continue
            instance_id = str(item.get("ID") or "")
            process = item.get("Instance")
            result.append(
                {
                    "id": instance_id,
                    "name": str(item.get("Name") or versions.get(instance_id) or "Minecraft"),
                    "type": "Minecraft",
                    "isRunning": bool(process is not None and process.poll() is None),
                    "version": versions.get(instance_id) or str(item.get("Name") or ""),
                }
            )
        return result

    def stop_instance(self, instance_id: Any) -> None:
        """终止指定的运行中 Minecraft 实例。"""
        if not isinstance(instance_id, str) or not instance_id.strip():
            raise GameServiceError("实例 ID 不能为空", "INVALID_INSTANCE_ID")
        existing_ids = {
            str(item.get("ID")) for item in self.instances.get_instances_info() if item.get("Type") == "Minecraft"
        }
        if instance_id not in existing_ids:
            raise GameServiceError("游戏实例不存在", "INSTANCE_NOT_FOUND")
        self.instances.stop_instance(instance_id, wait_timeout=3.0)
        with self._lock:
            self._instance_versions.pop(instance_id, None)

    def close(self) -> None:
        """取消后台任务并释放服务资源，保留已启动的游戏实例。"""
        self._version_watch_stop.set()
        with self._lock:
            downloads = list(self._active_downloads.values())
            install_tasks = list(self._install_tasks.values())
            contexts = list(self._contexts.values())
            version_watch_thread = self._version_watch_thread
            self._version_watch_thread = None
            self._version_scan_cache.clear()
            self._version_watch_paths.clear()
            self._version_watch_snapshots.clear()
            self._version_watch_pending.clear()
            self._active_downloads.clear()
            self._install_tasks.clear()
            self._contexts.clear()
        if version_watch_thread is not None and version_watch_thread.is_alive():
            version_watch_thread.join(timeout=self._version_watch_interval + 0.5)
        for downloader in downloads:
            try:
                downloader.stop()
            except Exception:
                self.logger.exception("停止下载任务失败")
        for task in install_tasks:
            if task.done():
                continue
            loop = task.get_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(task.cancel)
            else:
                task.cancel()
        for context in contexts:
            try:
                context.api_client.close()
            except Exception:
                self.logger.exception("关闭游戏 API 客户端失败")
        if self.authlib_injector is not None:
            self.authlib_injector.close()
