from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ..auth.manager import AccountManager
from ..game.Core.C_GetGames import GetGames
from ..game.Core.ECLauncherCore import ECLauncherCore
from ..java.detector import JavaDetector
from ..java.models import JavaInfo
from .config import ConfigManager
from ..common.env import singleton
from .logger import get_logger

try:
    from ..api.events import emit as _emit
    def _safe_emit(event: str, data: dict) -> None:
        try:
            _emit(event, data)
        except (RuntimeError, ValueError, TypeError, ConnectionError, OSError):
            pass
except ImportError:
    def _safe_emit(event: str, data: dict) -> None:
        pass

logger = get_logger("state")


@singleton
class AppState:

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self.config_manager: ConfigManager = ConfigManager()
        self.account_manager: AccountManager = AccountManager()
        self.java_list: list[JavaInfo] = []
        self.version_info: dict[str, Any] = {}
        self._initialized: bool = False
        self._shutdown_done: bool = False
        self._cached_local_versions: list[dict[str, Any]] = []

        # Core 实例（单例，由 AppState 统一持有）
        self.launcher_core: ECLauncherCore = ECLauncherCore()
        self.get_games: GetGames = GetGames(self.launcher_core.files_checker)

        # 配置 Core 实例的日志回调
        def _on_launcher_log(msg: str) -> None:
            logger.info(f"[Core] {msg}")
            # 映射 Core 日志到启动进度阶段
            if "正在启动游戏" in msg:
                _safe_emit("game:launch_progress", {"phase": "launching", "message": msg, "percent": 95})
            elif "系统平台" in msg:
                _safe_emit("game:launch_progress", {"phase": "building_args", "message": "构建启动参数...", "percent": 90})
            elif "文件校验完成" in msg:
                _safe_emit("game:launch_progress", {"phase": "files_checked", "message": msg, "percent": 50})
            elif "启动参数构建完成" in msg:
                _safe_emit("game:launch_progress", {"phase": "args_built", "message": msg, "percent": 75})
            elif "原生库解压完成" in msg:
                _safe_emit("game:launch_progress", {"phase": "natives_done", "message": msg, "percent": 85})
            elif "即将启动游戏进程" in msg:
                _safe_emit("game:launch_progress", {"phase": "about_to_launch", "message": msg, "percent": 92})
        self.launcher_core.set_output_launcher_log(_on_launcher_log)
        self.launcher_core.set_output_jvm_params(lambda msg: logger.info(f"[Core] {msg}"))
        self.get_games.set_output_log(lambda msg: logger.info(f"[Core] {msg}"))

        # 文件校验日志回调 → 推送事件到前端
        def _on_files_check_log(msg: str) -> None:
            logger.info(f"[FilesCheck] {msg}")
            _safe_emit("game:launch_progress", {"phase": "checking", "message": msg})
        self.launcher_core.files_checker.set_output_log(_on_files_check_log)
        self.launcher_core.files_checker.set_cancel_check(lambda: self.launcher_core.is_canceled())

        # 下载日志回调 → 记录日志（进度通过 event_callback 推送）
        self.launcher_core.downloader.set_output_log(lambda msg: logger.info(f"[Downloader] {msg}"))

        # 下载进度回调 → 推送 N/M 百分比到前端
        def _on_download_progress(total: list, done: list) -> None:
            t = len(total)
            d = len(done)
            pct = int(d / t * 100) if t > 0 else 0
            _safe_emit("game:launch_progress", {
                "phase": "downloading",
                "message": f"下载资源 ({d}/{t})",
                "done": d,
                "total": t,
                "percent": pct,
            })
        self.launcher_core.downloader.set_output_progress(_on_download_progress)

        # 下载事件回调 → 推送详细进度
        def _on_download_event(event_data: dict) -> None:
            _safe_emit("game:launch_progress", {
                "phase": "downloading",
                "message": f"下载资源 ({event_data.get('done', 0)}/{event_data.get('total', 0)})",
                "done": event_data.get("done", 0),
                "total": event_data.get("total", 0),
                "percent": int(event_data.get("done", 0) / max(event_data.get("total", 1), 1) * 100),
            })
        self.launcher_core.downloader.event_callback = _on_download_event

        # 游戏实例日志/退出回调：不打印到终端，仅记录到日志文件
        self.launcher_core.instances_manager.set_log_callback(lambda msg: logger.debug(f"[Game] {msg}"))
        self.launcher_core.instances_manager.set_exit_callback(lambda code: logger.info(f"[Game] 进程退出，返回码: {code}"))

        # 插件框架（延迟初始化，在 initialize 中创建）
        self.plugin_framework = None

    @property
    def initialized(self) -> bool:
        return self._initialized

    def initialize(self) -> dict[str, Any]:
        if self._initialized:
            return {"needs_password": False}
        logger.info("正在初始化应用全局状态...")

        self.config_manager.load()
        error = self.config_manager.validate()
        if error:
            logger.error(f"配置校验失败: {error}")
            return {"needs_password": False, "error": error}

        self.version_info = self.config_manager.get_launcher_config()

        logger.info("开始扫描 Java 环境...")
        self.java_list = JavaDetector().detect_all()
        logger.info(f"Java 扫描完成，共找到 {len(self.java_list)} 个安装")

        logger.info("正在初始化账户管理器...")
        account_result = self.account_manager.initialize()
        if account_result.get("needs_password"):
            logger.info("账户管理器需要主密码")
        elif not account_result.get("success"):
            logger.error("账户管理器初始化失败")

        self._initialized = True
        logger.info("应用全局状态初始化完成")
        return {"needs_password": account_result.get("needs_password", False)}

    async def initialize_async(self):
        # 延迟导入避免循环依赖
        from ..api.events import emit

        def _on_download_progress(payload):
            emit(
                "game:install_progress",
                {
                    "phase": "download",
                    "done": payload.get("done", 0),
                    "total": payload.get("total", 0),
                    "message": f"下载中... ({payload.get('done', 0)}/{payload.get('total', 0)})",
                },
            )

        # 设置下载进度事件回调（必须在每次初始化时设置，因为单例 __init__ 只执行一次）
        self.launcher_core.downloader.event_callback = _on_download_progress

        if self._initialized:
            return {"java": True, "account": True}

        results = {}
        logger.info("正在异步初始化应用全局状态...")

        # 配置加载必须在最前面（同步）
        self.config_manager.load()
        error = self.config_manager.validate()
        if error:
            logger.error(f"配置校验失败: {error}")
            results["config"] = False
            return results
        results["config"] = True
        self.version_info = self.config_manager.get_launcher_config()

        async def _scan_java():
            detector = JavaDetector()
            self.java_list = await detector.detect_all_parallel()
            logger.info(f"Java 扫描完成，共找到 {len(self.java_list)} 个安装")
            return True

        async def _init_account():
            result = await asyncio.to_thread(self.account_manager.initialize)
            if result.get("needs_password"):
                logger.info("账户管理器需要主密码")
            elif not result.get("success"):
                logger.error("账户管理器初始化失败")
            return result

        java_ok, account_result = await asyncio.gather(_scan_java(), _init_account())
        results["java"] = java_ok
        results["account"] = account_result.get("success", False)
        results["needs_password"] = account_result.get("needs_password", False)

        self._initialized = True
        logger.info("应用全局状态异步初始化完成")
        return results

    def refresh_java_list(self) -> list[JavaInfo]:
        logger.info("重新扫描 Java 环境...")
        self.java_list = JavaDetector().detect_all()
        return self.java_list

    def get_java_dicts(self) -> list[dict[str, Any]]:
        return [
            {
                "path": str(java.path),
                "version": java.version,
                "major_version": java.major_version,
                "java_type": java.java_type,
                "arch": java.arch,
                "sources": java.sources,
            }
            for java in self.java_list
        ]

    def shutdown(self) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True
        logger.info("正在关闭应用全局状态...")
        from ..api.events import EventEmitter, emit_plugin_event
        EventEmitter.set_exiting(True)
        try:
            # 先取消正在进行的启动流程，让 check_files 等尽快退出
            self.launcher_core.cancel_launch()
            if self.plugin_framework is not None:
                try:
                    logger.info("[shutdown] 开始关闭插件框架...")
                    self.plugin_framework.shutdown()
                    logger.info("[shutdown] 插件框架已关闭")
                except (RuntimeError, OSError, ValueError, TypeError) as e:
                    logger.error(f"关闭插件框架失败: {e}")
            logger.info("[shutdown] 开始关闭账户管理器...")
            self.account_manager.shutdown()
            logger.info("[shutdown] 账户管理器已关闭")
            logger.info("[shutdown] 开始关闭实例管理器...")
            self.launcher_core.instances_manager.shutdown_all()
            logger.info("[shutdown] 实例管理器已关闭")
            # 关闭 Java 检测线程池
            try:
                from ..java.detector import JavaDetector
                JavaDetector.shutdown_executor()
            except (RuntimeError, OSError):
                pass
        finally:
            logger.info("应用全局状态已关闭")

    def _init_plugin_framework(self) -> None:
        try:
            from ..plugin import PluginFramework
            plugins_dir = Path.cwd() / "plugins"
            cache_root = Path.cwd() / "dep_cache"
            deps_meta = Path.cwd() / "deps_meta.json"
            self.plugin_framework = PluginFramework(
                plugins_dir=plugins_dir,
                cache_root=cache_root,
                deps_meta_path=deps_meta,
            )
            # 扫描并加载所有插件
            plugins = self.plugin_framework.scan_plugins()
            for p in plugins:
                if p["status"] == "unloaded" and p.get("name"):
                    try:
                        self.plugin_framework.load_plugin(p["name"])
                    except (RuntimeError, OSError, ValueError, TypeError, ImportError) as e:
                        logger.warning(f"自动加载插件 {p['name']} 失败: {e}")
            logger.info(f"插件框架已初始化，共扫描到 {len(plugins)} 个插件")
        except ImportError as e:
            logger.warning(f"插件框架模块导入失败: {e}")
        except (RuntimeError, OSError, ValueError, TypeError) as e:
            logger.error(f"初始化插件框架失败: {e}")
