from __future__ import annotations

import asyncio
import importlib
import io
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from threading import Event, RLock
from typing import Any
from uuid import uuid4

import httpx
from anyio import to_thread

from ECL.Events import EventBus
from ECL.Game.Core.Downloader import Downloader, DynamicSemaphore
from ECL.Game.Core.ECLauncherCore import LaunchConfig, build_minecraft_cmd
from ECL.Game.Core.FilesChecker import FilesChecker
from ECL.Game.Core.GetGames import GetGames
from ECL.Game.Core.InstancesManager import InstancesManager
from ECL.Game.Core.LoaderInstaller import LoaderInstaller
from ECL.Game.Core.NetLibs import ApiUrlConfig, BaseApiClient, BmclApiUrl
from ECL.Infrastructure import get_logger
from ECL.Services.accounts import AccountManager

ApiClientFactory = Callable[[ApiUrlConfig], BaseApiClient]
DownloaderFactory = Callable[..., Downloader]
CommandBuilder = Callable[[LaunchConfig], str]
SearchFactory = Callable[[Path], Any]

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


def _import_search_minecraft() -> type:
    """导入旧扫描器，并为其顶层绝对 Libs 导入提供临时兼容别名。"""
    module_name = "ECL.Game.Utils.SearchMinecraft"
    loaded_module = sys.modules.get(module_name)
    if loaded_module is not None:
        return loaded_module.SearchMinecraft

    game_libs = importlib.import_module("ECL.Game.Utils.Libs")
    previous_libs = sys.modules.get("Libs")
    sys.modules["Libs"] = game_libs
    try:
        module = importlib.import_module(module_name)
    finally:
        if previous_libs is None:
            sys.modules.pop("Libs", None)
        else:
            sys.modules["Libs"] = previous_libs
    return module.SearchMinecraft


SearchMinecraft = _import_search_minecraft()


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
    loader_installer: LoaderInstaller
    games: GetGames


class _WaitingLoaderInstaller(LoaderInstaller):
    """等待 Core 创建的加载器安装进程结束后再允许清理安装缓存。"""

    _PROCESS_TIMEOUT_SECONDS = 15 * 60

    def install_neoforged(
        self,
        installer_path: Path | str,
        java_path: Path | str,
        save_name: str,
    ) -> bool:
        before_ids = {
            str(item.get("ID"))
            for item in self.instances_mgr.get_instances_info()
            if item.get("ID")
        }
        result = super().install_neoforged(installer_path, java_path, save_name)
        new_processes = [
            item.get("Instance")
            for item in self.instances_mgr.get_instances_info()
            if item.get("ID") not in before_ids and item.get("Type") == "LoaderInstaller"
        ]
        deadline = time.monotonic() + self._PROCESS_TIMEOUT_SECONDS
        for process in new_processes:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("加载器安装进程等待超时")
            try:
                exit_code = process.wait(timeout=remaining)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                raise TimeoutError("加载器安装进程等待超时") from exc
            if exit_code != 0:
                raise RuntimeError(f"加载器安装进程异常退出，退出码: {exit_code}")
        return result


class _ResumableDownloader(Downloader):
    """为 Core Downloader 补充大文件断点续传和可观测错误。"""

    _CHUNK_SIZE = 1024 * 1024
    _READ_TIMEOUT_SECONDS = 120.0

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.logger = get_logger("GameDownloader")
        self._counted_resume_paths: set[str] = set()

    def _count_resumed_bytes(self, temp_path: Path, resumed_bytes: int) -> None:
        path_key = str(temp_path)
        if not self.use_byte_progress or resumed_bytes <= 0 or path_key in self._counted_resume_paths:
            return
        self._counted_resume_paths.add(path_key)
        self.downloaded_bytes += resumed_bytes
        progress = min(self.downloaded_bytes, self.total_bytes) if self.total_bytes > 0 else 0
        self._put_event("progress", progress, self.total_bytes)

    async def _download_file_once(self, url: str, path: Path, size_known: int | None) -> bool:
        if size_known is not None and path.is_file() and path.stat().st_size == size_known:
            self._mark_completed(url, path)
            return True

        acquired = False
        temp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            await self.semaphore.acquire()
            acquired = True
            await self.pause_event.wait()
            path.parent.mkdir(parents=True, exist_ok=True)

            resume_offset = temp_path.stat().st_size if temp_path.is_file() else 0
            if size_known is not None and resume_offset > size_known:
                temp_path.unlink(missing_ok=True)
                resume_offset = 0
            if size_known is not None and resume_offset == size_known:
                self._count_resumed_bytes(temp_path, resume_offset)
                temp_path.replace(path)
                self._mark_completed(url, path)
                return True

            request_headers = dict(self.headers)
            if resume_offset:
                request_headers["Range"] = f"bytes={resume_offset}-"
            timeout = httpx.Timeout(
                connect=15.0,
                read=self._READ_TIMEOUT_SECONDS,
                write=30.0,
                pool=30.0,
            )
            async with self.client.stream(
                "GET",
                url,
                headers=request_headers,
                timeout=timeout,
            ) as response:
                if response.status_code == 416 and size_known is not None and resume_offset == size_known:
                    self._count_resumed_bytes(temp_path, resume_offset)
                    temp_path.replace(path)
                    self._mark_completed(url, path)
                    return True
                response.raise_for_status()

                append_mode = response.status_code == 206 and resume_offset > 0
                if not append_mode:
                    resume_offset = 0
                self._count_resumed_bytes(temp_path, resume_offset)

                content_length = int(response.headers.get("content-length") or 0)
                expected_size = size_known
                if expected_size is None and content_length > 0:
                    expected_size = resume_offset + content_length
                mode = "ab" if append_mode else "wb"
                with temp_path.open(mode) as output:
                    async for chunk in response.aiter_bytes(self._CHUNK_SIZE):
                        await self.pause_event.wait()
                        await self.rate_limiter.acquire(len(chunk))
                        output.write(chunk)
                        self.bytes_downloaded_for_speed += len(chunk)
                        if self.use_byte_progress:
                            self.downloaded_bytes += len(chunk)
                            progress = min(self.downloaded_bytes, self.total_bytes) if self.total_bytes > 0 else 0
                            self._put_event("progress", progress, self.total_bytes)

            final_size = temp_path.stat().st_size
            if expected_size is not None and expected_size > 0 and final_size != expected_size:
                self.logger.warning(
                    "下载文件大小不完整，将保留临时文件继续重试: %s (%s/%s)",
                    path,
                    final_size,
                    expected_size,
                )
                return False
            temp_path.replace(path)
            self._mark_completed(url, path)
            if not self.use_byte_progress:
                self.downloaded_bytes += 1
                self._put_event("progress", self.downloaded_bytes, self.total_bytes)
            return True
        except Exception as exc:
            downloaded_size = temp_path.stat().st_size if temp_path.is_file() else 0
            self.logger.warning(
                "下载中断，将在下一轮从临时文件续传: %s (%s bytes), url=%s, error=%r",
                path,
                downloaded_size,
                url,
                exc,
            )
            return False
        finally:
            if acquired:
                self.semaphore.release()


class GameService:
    """Minecraft 版本查询、安装、校验和启动的统一门面。"""

    def __init__(
        self,
        accounts: AccountManager,
        *,
        search_factory: SearchFactory = SearchMinecraft,
        instances_manager: InstancesManager | None = None,
        api_client_factory: ApiClientFactory = BaseApiClient,
        downloader_factory: DownloaderFactory = _ResumableDownloader,
        command_builder: CommandBuilder = build_minecraft_cmd,
    ):
        self.logger = get_logger("GameService")
        self.accounts = accounts
        self._search_factory = search_factory
        self.instances = instances_manager or InstancesManager()
        self._api_client_factory = api_client_factory
        self._downloader_factory = downloader_factory
        self._command_builder = command_builder
        self._contexts: dict[tuple[str, str], _CoreContext] = {}
        self._active_downloads: dict[str, Downloader] = {}
        self._install_tasks: dict[str, asyncio.Task[None]] = {}
        self._instance_versions: dict[str, str] = {}
        self._launch_cancel_event: Event | None = None
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
            loader_installer = _WaitingLoaderInstaller(
                files_checker,
                self.instances,
                path,
                log_callback=lambda message: self.logger.info("%s", message),
            )
            context = _CoreContext(
                api_client=api_client,
                files_checker=files_checker,
                loader_installer=loader_installer,
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
        return {
            "id": version_name,
            "versionId": version_name,
            "versionType": version_type,
            "path": str(game_path),
            "displayName": version_name,
            "primaryLoader": primary_loader,
            "vanillaName": vanilla_name,
            "hasForge": loader_key == "forge",
            "hasNeoForge": loader_key == "neoforge",
            "hasFabric": loader_key == "fabric",
            "hasQuilt": loader_key == "quilt",
            "hasOptiFine": loader_key == "optifine",
            "isBroken": not json_path.is_file(),
            "jsonPath": str(json_path),
            "sourceName": game_path.name or str(game_path),
        }

    def scan_versions(self, paths: Any) -> list[dict[str, Any]]:
        scanned_versions: list[dict[str, Any]] = []
        for game_path in self._normalize_scan_paths(paths):
            versions_path = game_path / "versions"
            if not versions_path.is_dir():
                self.logger.debug("跳过不存在的版本目录: %s", versions_path)
                continue
            try:
                scanner = self._search_factory(game_path)
                with redirect_stdout(io.StringIO()):
                    versions = scanner.search_minecraft()
            except (OSError, TypeError, ValueError) as exc:
                self.logger.exception("扫描 Minecraft 版本失败: %s", game_path)
                raise VersionScanError(f"扫描游戏目录失败: {game_path}: {exc}") from exc
            if not isinstance(versions, dict):
                raise VersionScanError(f"版本扫描器返回了无效数据: {game_path}")
            for version_name, info in versions.items():
                if not isinstance(version_name, str) or not version_name.strip():
                    continue
                scanned_versions.append(
                    self._normalize_scanned_version(game_path, version_name.strip(), info)
                )
        return sorted(
            scanned_versions,
            key=lambda item: (str(item["sourceName"]).casefold(), str(item["displayName"]).casefold()),
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
        EventBus().emit("game:install_progress", payload)

    @staticmethod
    def _loader_version(body: dict[str, Any], loader: str) -> str | None:
        field_names = {
            "fabric": "fabric_version",
            "forge": "forge_version",
            "neoforge": "neoforge_version",
            "quilt": "quilt_version",
        }
        value = body.get(field_names.get(loader, ""))
        return value.strip() if isinstance(value, str) and value.strip() else None

    def _build_install_downloads(
        self,
        body: dict[str, Any],
        game_path: Path,
        source: str,
        java_path: str | None,
    ) -> tuple[str, list[tuple[str, str]]]:
        version_id = self._normalize_version_name(body.get("version_id"), "Minecraft 版本")
        save_name = self._normalize_version_name(body.get("version_name") or version_id)
        loader = str(body.get("loader_type") or "vanilla").strip().casefold()
        games = self._context(game_path, source).games
        if loader in {"", "vanilla", "none"}:
            return save_name, games.build_minecraft_download_list(version_id, save_name)

        loader_version = self._loader_version(body, loader)
        if not loader_version:
            raise GameServiceError("未选择加载器版本", "LOADER_VERSION_REQUIRED")
        if loader == "fabric":
            downloads = games.build_fabric_download_list(version_id, loader_version, save_name)
        elif loader == "quilt":
            downloads = games.build_quilt_download_list(version_id, loader_version, save_name)
        elif loader in {"forge", "neoforge"}:
            java_path = self._resolve_java_path(java_path)
            if loader == "forge":
                downloads = games.build_forge_download_list(version_id, loader_version, java_path, save_name)
            else:
                downloads = games.build_neoforged_download_list(version_id, loader_version, java_path, save_name)
        else:
            raise GameServiceError(f"暂不支持安装加载器: {body.get('loader_type')}", "UNSUPPORTED_LOADER")
        return save_name, downloads

    @staticmethod
    def _configure_downloader(downloader: Downloader, download_threads: int) -> None:
        downloader.concurrency = download_threads
        downloader.semaphore = DynamicSemaphore(download_threads)

    def start_install(
        self,
        body: dict[str, Any],
        *,
        game_path: Any,
        source: Any = "official",
        java_path: str | None = None,
        download_threads: Any = 16,
    ) -> str:
        """创建由游戏服务持有的安装任务，并立即返回任务 ID。"""
        path = self._normalize_game_path(game_path)
        normalized_source = self._normalize_source(source)
        threads = self._normalize_positive_int(download_threads, 16, 1, 256, "下载线程数")
        path.mkdir(parents=True, exist_ok=True)
        (path / "versions").mkdir(parents=True, exist_ok=True)

        task_id = str(body.get("task_id") or f"install-{uuid4().hex}")
        task_body = dict(body)
        task_body["task_id"] = task_id
        loop = asyncio.get_running_loop()
        with self._lock:
            existing = self._install_tasks.get(task_id)
            if existing is not None and not existing.done():
                self.logger.warning("拒绝重复安装任务: task_id=%s", task_id)
                raise GameServiceError("相同的安装任务已在运行", "INSTALL_ALREADY_RUNNING")
            task = loop.create_task(
                self.install_version(
                    task_body,
                    game_path=path,
                    source=normalized_source,
                    java_path=java_path,
                    download_threads=threads,
                ),
                name=f"ECLInstall-{task_id}",
            )
            self._install_tasks[task_id] = task
        self.logger.info(
            "安装任务已创建: task_id=%s, version=%s, loader=%s, game_path=%s, source=%s, threads=%s",
            task_id,
            body.get("version_id"),
            body.get("loader_type") or "vanilla",
            path,
            normalized_source,
            threads,
        )
        task.add_done_callback(
            lambda finished, install_id=task_id: self._finish_install_task(install_id, finished)
        )
        return task_id

    def _finish_install_task(self, task_id: str, task: asyncio.Task[None]) -> None:
        with self._lock:
            if self._install_tasks.get(task_id) is task:
                self._install_tasks.pop(task_id, None)
        try:
            task.result()
        except asyncio.CancelledError:
            self.logger.info("安装任务已取消: %s", task_id)
        except Exception:
            # install_version 已记录异常并向前端发送 error 进度；这里消费异常，
            # 避免后台 Task 产生 “exception was never retrieved” 警告。
            pass

    async def install_version(
        self,
        body: dict[str, Any],
        *,
        game_path: Any,
        source: Any = "official",
        java_path: str | None = None,
        download_threads: Any = 16,
    ) -> None:
        path = self._normalize_game_path(game_path)
        path.mkdir(parents=True, exist_ok=True)
        (path / "versions").mkdir(parents=True, exist_ok=True)
        normalized_source = self._normalize_source(source)
        threads = self._normalize_positive_int(download_threads, 16, 1, 256, "下载线程数")
        task_id = str(body.get("task_id") or f"install-{uuid4().hex}")
        started_at = time.monotonic()
        with self._lock:
            if task_id in self._active_downloads:
                raise GameServiceError("相同的安装任务已在运行", "INSTALL_ALREADY_RUNNING")

        self.logger.info(
            "开始执行安装任务: task_id=%s, version=%s, loader=%s",
            task_id,
            body.get("version_id"),
            body.get("loader_type") or "vanilla",
        )
        self._emit_install_progress(task_id, "install", "正在生成安装文件列表", done=0, total=1)
        try:
            save_name, download_list = await to_thread.run_sync(
                lambda: self._build_install_downloads(
                    body,
                    path,
                    normalized_source,
                    java_path,
                )
            )
            total_files = len(download_list)
            self.logger.info(
                "安装文件列表生成完成: task_id=%s, save_name=%s, files=%d",
                task_id,
                save_name,
                total_files,
            )
            if not download_list:
                self.logger.info(
                    "安装任务完成（无需下载）: task_id=%s, elapsed=%.2fs",
                    task_id,
                    time.monotonic() - started_at,
                )
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
            self._configure_downloader(downloader, threads)
            with self._lock:
                self._active_downloads[task_id] = downloader

            self.logger.info(
                "开始下载游戏文件: task_id=%s, files=%d, threads=%d",
                task_id,
                total_files,
                threads,
            )
            self._emit_install_progress(
                task_id,
                "download",
                f"准备下载 {total_files} 个文件",
                done=0,
                total=total_files,
                subtask="download_files",
            )
            await downloader.run()
            client = getattr(downloader, "client", None)
            if client is not None and not client.is_closed:
                await client.aclose()
            if downloader.failed_entries:
                for failed_url, failed_path in sorted(downloader.failed_entries):
                    self.logger.error("游戏文件下载失败: %s <- %s", failed_path, failed_url)
                raise GameServiceError(
                    f"有 {len(downloader.failed_entries)} 个文件下载失败",
                    "GAME_DOWNLOAD_FAILED",
                )
            self.logger.info(
                "安装任务完成: task_id=%s, save_name=%s, files=%d, elapsed=%.2fs",
                task_id,
                save_name,
                total_files,
                time.monotonic() - started_at,
            )
            self._emit_install_progress(task_id, "done", f"{save_name} 已安装完成", done=1, total=1)
        except asyncio.CancelledError:
            self.logger.info(
                "安装任务已取消: task_id=%s, elapsed=%.2fs",
                task_id,
                time.monotonic() - started_at,
            )
            raise
        except GameServiceError as exc:
            self.logger.warning(
                "安装任务失败: task_id=%s, error_code=%s, elapsed=%.2fs, error=%s",
                task_id,
                exc.error_code,
                time.monotonic() - started_at,
                exc,
            )
            self._emit_install_progress(task_id, "error", str(exc), done=0, total=1)
            raise
        except Exception as exc:
            self.logger.exception(
                "安装 Minecraft 版本失败: task_id=%s, elapsed=%.2fs",
                task_id,
                time.monotonic() - started_at,
            )
            error = GameServiceError(f"安装版本失败: {exc}", "VERSION_INSTALL_FAILED")
            self._emit_install_progress(task_id, "error", str(error), done=0, total=1)
            raise error from exc
        finally:
            with self._lock:
                self._active_downloads.pop(task_id, None)

    def uninstall_version(self, version_id: Any, game_path: Any) -> None:
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

    def _emit_launch_progress(self, phase: str, message: str, percent: int | None = None) -> None:
        payload: dict[str, Any] = {"phase": phase, "message": message}
        if percent is not None:
            payload["percent"] = percent
        EventBus().emit("game:launch_progress", payload)

    @staticmethod
    def _resolve_java_path(value: Any) -> str:
        raw_path = str(value or "").strip()
        if raw_path:
            path = Path(raw_path).expanduser()
            if path.is_dir():
                executable_name = "javaw.exe" if shutil.which("javaw") else "java.exe"
                path = path / "bin" / executable_name
            if not path.is_file():
                raise GameServiceError("Java 可执行文件不存在", "JAVA_NOT_FOUND")
            return str(path.resolve())

        discovered = shutil.which("javaw") or shutil.which("java")
        if not discovered:
            raise GameServiceError("未找到 Java，请先在设置中选择 Java", "JAVA_NOT_FOUND")
        return discovered

    async def _download_missing_launch_files(
        self,
        context: _CoreContext,
        game_path: Path,
        version_name: str,
        download_threads: int,
        cancel_event: Event,
    ) -> None:
        download_list = await to_thread.run_sync(context.files_checker.check_files, game_path, version_name)
        if cancel_event.is_set():
            raise GameServiceError("启动已取消", "LAUNCH_CANCELLED")
        self._emit_launch_progress("files_checked", f"文件检查完成，共需补全 {len(download_list)} 个文件", 20)
        if not download_list:
            return

        downloader = self._downloader_factory(
            download_list,
            progress_callback=lambda done, total: self._emit_launch_progress(
                "downloading",
                "正在补全游戏文件",
                int(done * 100 / total) if total else 0,
            ),
        )
        self._configure_downloader(downloader, download_threads)
        launch_download_id = "__launch__"
        with self._lock:
            self._active_downloads[launch_download_id] = downloader
        try:
            try:
                await downloader.run()
            except Exception as exc:
                if cancel_event.is_set():
                    raise GameServiceError("启动已取消", "LAUNCH_CANCELLED") from exc
                raise
            client = getattr(downloader, "client", None)
            if client is not None and not client.is_closed:
                await client.aclose()
        finally:
            with self._lock:
                self._active_downloads.pop(launch_download_id, None)
        if cancel_event.is_set():
            raise GameServiceError("启动已取消", "LAUNCH_CANCELLED")
        if downloader.failed_entries:
            raise GameServiceError(
                f"有 {len(downloader.failed_entries)} 个游戏文件补全失败",
                "GAME_DOWNLOAD_FAILED",
            )

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
        download_threads: Any = 16,
    ) -> str:
        version_name = self._normalize_version_name(body.get("version_id"))
        path = self._normalize_game_path(game_path)
        version_json = path / "versions" / version_name / f"{version_name}.json"
        if not version_json.is_file():
            raise GameServiceError("游戏版本不存在或版本 JSON 缺失", "VERSION_NOT_FOUND")
        java = self._resolve_java_path(java_path)
        ram = self._normalize_positive_int(memory, 4096, 256, 131072, "游戏内存")
        window_width = self._normalize_positive_int(width, 854, 320, 16384, "窗口宽度")
        window_height = self._normalize_positive_int(height, 480, 240, 16384, "窗口高度")
        threads = self._normalize_positive_int(download_threads, 16, 1, 256, "下载线程数")
        custom_jvm_args = self._normalize_string_list(jvm_args, "JVM 参数")
        custom_game_args = self._normalize_string_list(game_args, "游戏参数")
        context = self._context(path, source)

        cancel_event = Event()
        with self._lock:
            if self._launch_cancel_event is not None:
                raise GameServiceError("已有游戏启动任务正在运行", "LAUNCH_ALREADY_RUNNING")
            self._launch_cancel_event = cancel_event

        try:
            self._emit_launch_progress("preparing", f"正在准备启动 {version_name}", 5)
            credentials = await to_thread.run_sync(self.accounts.get_launch_credentials)
            if cancel_event.is_set():
                raise GameServiceError("启动已取消", "LAUNCH_CANCELLED")

            self._emit_launch_progress("checking", "正在检查游戏文件", 10)
            await self._download_missing_launch_files(context, path, version_name, threads, cancel_event)

            self._emit_launch_progress("building_args", "正在生成启动参数", 60)
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
                version_isolation=bool(version_isolation),
                window_width=window_width,
                window_height=window_height,
            )
            command = await to_thread.run_sync(self._command_builder, launch_config)
            if custom_game_args:
                command = f"{command} {' '.join(custom_game_args)}"
            self._emit_launch_progress("args_built", "启动参数生成完成", 75)
            if cancel_event.is_set():
                raise GameServiceError("启动已取消", "LAUNCH_CANCELLED")

            self._emit_launch_progress("about_to_launch", "即将启动游戏", 90)
            instance_id = self.instances.create_instance(
                instance_name=version_name,
                instance_type="Minecraft",
                args=command,
                cwd=path / "versions" / version_name if version_isolation else path,
                log_callback=lambda line, current_id: self.logger.info("[%s] %s", current_id, line),
                exit_callback=lambda code, name: self.logger.info("Minecraft %s 已退出，退出码: %s", name, code),
            )
            with self._lock:
                self._instance_versions[instance_id] = version_name
            self._emit_launch_progress("launched", f"{version_name} 已启动", 100)
            return instance_id
        except GameServiceError as exc:
            if exc.error_code != "LAUNCH_CANCELLED":
                self._emit_launch_progress("error", str(exc), 0)
            raise
        except Exception as exc:
            self.logger.exception("启动 Minecraft 失败")
            error = GameServiceError(f"启动游戏失败: {exc}", "GAME_LAUNCH_FAILED")
            self._emit_launch_progress("error", str(error), 0)
            raise error from exc
        finally:
            with self._lock:
                self._launch_cancel_event = None

    def cancel_launch(self) -> bool:
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
        if not isinstance(instance_id, str) or not instance_id.strip():
            raise GameServiceError("实例 ID 不能为空", "INVALID_INSTANCE_ID")
        existing_ids = {
            str(item.get("ID"))
            for item in self.instances.get_instances_info()
            if item.get("Type") == "Minecraft"
        }
        if instance_id not in existing_ids:
            raise GameServiceError("游戏实例不存在", "INSTANCE_NOT_FOUND")
        self.instances.stop_instance(instance_id, wait_timeout=3.0)
        with self._lock:
            self._instance_versions.pop(instance_id, None)

    def close(self) -> None:
        with self._lock:
            downloads = list(self._active_downloads.values())
            install_tasks = list(self._install_tasks.values())
            contexts = list(self._contexts.values())
            self._active_downloads.clear()
            self._install_tasks.clear()
            self._contexts.clear()
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
        self.instances.shutdown_all(wait_timeout=3.0)
        for context in contexts:
            try:
                context.api_client.close()
            except Exception:
                self.logger.exception("关闭游戏 API 客户端失败")
