from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import gettempdir
from threading import Event, RLock, Thread
from typing import TYPE_CHECKING, Any

from ECL.events import EventBus
from ECL.game import (
    ApiUrlConfig,
    BaseApiClient,
    BmclApiUrl,
    Downloader,
    FilesChecker,
    GetGames,
    InstancesManager,
    JavaScanner,
    LaunchConfig,
    LoaderInstaller,
    SearchMinecraft,
    build_minecraft_cmd,
)
from ECL.services.accounts import AccountManager
from ECL.services.authlib import AuthlibInjector
from ECL.utils import get_logger

from .instance_profiles import InstanceProfileStore
from .operations import GameOperationManager
from .version_stats import VersionStatsStore

if TYPE_CHECKING:
    from .crash_analysis import CrashAnalyzer

ApiClientFactory = Callable[[ApiUrlConfig], BaseApiClient]
DownloaderFactory = Callable[..., Downloader]
CommandBuilder = Callable[[LaunchConfig], str]
SearchFactory = Callable[[Path], Any]
JavaScannerFactory = Callable[..., JavaScanner]


class GameServiceError(Exception):
    """
    表示可安全转换为稳定 IPC 错误码的游戏操作失败。

    :param message: 面向用户的错误说明
    :param error_code: 供前端识别的稳定错误码
    """

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


@dataclass
class _RunningGame:
    """
    保存一次游戏运行在当前启动器会话中的内存态元数据。

    ``token`` 在进程管理器返回实例 ID 前即可被退出回调捕获，用于消除极短生命周期
    进程带来的注册竞态；这些数据不会写入硬盘。
    """

    token: str
    version_id: str
    loader: str
    game_path: Path
    game_directory: Path
    started_at: float
    started_wall_time: float
    instance_id: str | None = None
    pending: bool = True
    exited: bool = False
    exit_code: int | None = None
    stopping: bool = False
    startup_complete: bool = False
    crash_marked: bool = False
    output_lines: deque[str] = field(default_factory=lambda: deque(maxlen=500))


class _GameState:
    """
    保存游戏目录、安装、启动协调器共享的运行状态与资源。

    该基类只承载跨协调器共享的依赖和生命周期，不对 API 直接公开。
    """

    _ECL_JSON_NAME = "ecl.json"

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
        event_bus: EventBus | None = None,
    ):
        """
        创建游戏服务共享状态，并注入可替换的 Core 边界实现。

        :param accounts: 提供当前启动凭据的账户服务
        :param search_factory: Minecraft 本地版本扫描器工厂
        :param instances_manager: 游戏进程生命周期管理器
        :param api_client_factory: Game API 客户端工厂
        :param downloader_factory: 下载任务工厂
        :param command_builder: 启动命令构建函数
        :param java_scanner_factory: Java 运行时扫描器工厂
        :param data_path: 用于缓存和 Authlib Injector 的数据目录
        :param authlib_injector: 可选的外置登录组件管理器
        :param enable_version_watcher: 是否启用本地版本目录监听
        :param version_watch_interval: 目录监听轮询间隔，单位为秒
        :param version_watch_debounce: 版本变化事件的防抖时间，单位为秒
        :param event_bus: 当前应用上下文拥有的事件总线
        """
        self.logger = get_logger("GameService")
        self.events = event_bus or EventBus()
        self.accounts = accounts
        self._search_factory = search_factory
        self.instances = instances_manager or InstancesManager()
        self._api_client_factory = api_client_factory
        self._downloader_factory = downloader_factory
        self._command_builder = command_builder
        self._java_scanner_factory = java_scanner_factory
        self._data_path = (
            Path(data_path).resolve(strict=False)
            if data_path
            else (Path(gettempdir()) / "EuoraCraft-Launcher").resolve(strict=False)
        )
        self._java_cache_file = self._data_path / "java_cache.json" if data_path else None
        self.authlib_injector = authlib_injector or (AuthlibInjector(data_path) if data_path else None)
        # Java 与 Core 上下文按需创建并复用，避免每次目录查询重新建立网络客户端。
        self._java_runtimes: list[Any] = []
        self._contexts: dict[tuple[str, str], _CoreContext] = {}
        # 下载器和 asyncio 任务必须持有强引用，关闭服务时才能可靠停止或取消。
        self._active_downloads: dict[str, Downloader] = {}
        self._install_tasks: dict[str, asyncio.Task[None]] = {}
        # 已启动进程由 InstancesManager 拥有；这里只保存当前会话的展示与统计元数据。
        self._running_games: dict[str, _RunningGame] = {}
        self._version_stats = VersionStatsStore()
        self._instance_profiles = InstanceProfileStore(self._data_path, self._version_stats)
        self._game_operations = GameOperationManager(self._data_path, self.events)
        self._server_status_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._server_status_lock = RLock()
        from .crash_analysis import CrashAnalyzer

        self._crash_analyzer: CrashAnalyzer = CrashAnalyzer(self._data_path)
        self._crash_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ECL-CrashAnalyzer")
        self._crash_futures: set[Future[Any]] = set()
        self._closing = False
        self._launch_cancel_event: Event | None = None
        # 版本目录监听状态由唯一后台线程使用，所有共享容器仍受同一把锁保护。
        self._version_scan_cache: dict[str, list[dict[str, Any]]] = {}
        self._version_watch_paths: dict[str, Path] = {}
        self._version_watch_qomicex_paths: dict[str, Path | None] = {}
        self._version_watch_snapshots: dict[str, tuple[tuple[str, int, int], ...]] = {}
        self._version_watch_pending: dict[str, float] = {}
        self._version_watcher_enabled = (
            data_path is not None if enable_version_watcher is None else enable_version_watcher
        )
        self._version_watch_interval = max(0.1, float(version_watch_interval))
        self._version_watch_debounce = max(0.0, float(version_watch_debounce))
        self._version_watch_stop = Event()
        self._version_watch_thread: Thread | None = None
        self._lock = RLock()
        self.logger.debug(
            "游戏服务状态已创建: java_cache=%s, version_watcher=%s",
            self._java_cache_file,
            self._version_watcher_enabled,
        )

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
    def _normalize_version_name(value: Any, field_name: str = "实例名称") -> str:
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
                self.logger.debug("复用 Game Core 上下文: path=%s, source=%s", path, normalized_source)
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
            self.logger.debug("创建 Game Core 上下文: path=%s, source=%s", path, normalized_source)
            return context

    def _query_context(self, source: Any = "official") -> _CoreContext:
        # GetGames 的查询方法仍要求 game_path；查询阶段使用一个不会写入的占位路径。
        return self._context(Path.cwd() / ".minecraft", source)

    def authlib_login_config(self) -> dict[str, bool]:
        """
        检查 authlib-injector 是否可用；不可用时前端应禁用外置登录。
        """
        available = False
        if self.authlib_injector is not None:
            try:
                self.authlib_injector.ensure()
                available = True
            except Exception:
                self.logger.warning("authlib-injector 不可用，外置登录将被禁用")
        return {"available": available}

    def close(self) -> None:
        """
        取消后台任务并释放服务资源，保留已启动的游戏实例。
        """
        self._version_watch_stop.set()
        with self._lock:
            self._closing = True
        with self._lock:
            running_tokens = [token for token, run in self._running_games.items() if not run.pending]
        for token in running_tokens:
            self._finalize_instance_run(token, action="launcher_closed")
        with self._lock:
            downloads = list(self._active_downloads.values())
            install_tasks = list(self._install_tasks.values())
            contexts = list(self._contexts.values())
            version_watch_thread = self._version_watch_thread
            self._version_watch_thread = None
            self._version_scan_cache.clear()
            self._version_watch_paths.clear()
            self._version_watch_qomicex_paths.clear()
            self._version_watch_snapshots.clear()
            self._version_watch_pending.clear()
            self._active_downloads.clear()
            self._install_tasks.clear()
            self._contexts.clear()
        self.logger.debug(
            "正在关闭游戏服务: downloads=%d, install_tasks=%d, core_contexts=%d",
            len(downloads),
            len(install_tasks),
            len(contexts),
        )
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
        self._crash_executor.shutdown(wait=True, cancel_futures=True)
        self._game_operations.close()
        self._crash_analyzer.close()
        if self.authlib_injector is not None:
            self.authlib_injector.close()
        self.logger.debug("游戏服务已关闭")
