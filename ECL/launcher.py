from __future__ import annotations

import logging
import sys
from enum import IntEnum
from pathlib import Path
from typing import Any

from ECL.adapters import Adapter
from ECL.application import ApplicationContext, create_application
from ECL.common import __version__, __version_type__, get_runtime_info
from ECL.services.maintenance import apply_pending_debug_maintenance
from ECL.utils import configure_logging


class LauncherExitCode(IntEnum):
    SUCCESS = 0
    STARTUP_FAILED = 2
    FRONTEND_FAILED = 3


class EuoraCraftLauncher:
    """
    承载一次桌面应用运行，并连接日志、后端上下文与前端适配器。

    业务依赖由 :func:`create_application` 构造；启动器本身只协调初始化、运行和关闭。
    """

    def __init__(self) -> None:
        """
        读取运行目录并初始化最早可用的日志系统。
        """
        self.runtime_info = get_runtime_info()
        self.app_path: Path = self.runtime_info["app_path"]
        self.resource_path: Path = self.runtime_info["resource_path"]
        self.data_path = self.app_path / "ECL_data"
        self.launcher_version = __version__
        self.launcher_version_type = __version_type__
        self.is_frozen = self.runtime_info["is_frozen"]
        self.debug = False
        self.config: dict[str, Any] = {}
        self.context: ApplicationContext | None = None
        self._shutdown_complete = False
        self.logging = configure_logging(self.data_path)
        self.logger = self.logging.get_logger("EuoraCraft_Launcher")
        self.logger.debug(
            "启动器运行环境: app_path=%s, resource_path=%s, frozen=%s, python=%s",
            self.app_path,
            self.resource_path,
            self.is_frozen,
            sys.version.split()[0],
        )

    def run(self) -> LauncherExitCode:
        """
        初始化后端并运行前端事件循环。

        :return: 可直接交给操作系统的稳定退出码
        """
        self.logger.info("正在启动 EuoraCraft Launcher V%s %s", self.launcher_version, self.launcher_version_type)
        try:
            self._initialize()
        except Exception:
            self.logger.exception("启动器初始化失败")
            self._shutdown()
            return LauncherExitCode.STARTUP_FAILED

        try:
            self.logger.info("启动前端")
            Adapter(self._require_context()).run()
        except Exception:
            self.logger.exception("前端适配器运行失败")
            return LauncherExitCode.FRONTEND_FAILED
        finally:
            self._shutdown()
        return LauncherExitCode.SUCCESS

    def _initialize(self) -> None:
        """
        执行启动维护任务并构造后端应用上下文。
        """
        if sys.platform not in {"win32", "linux", "darwin"}:
            raise RuntimeError(f"不支持的系统环境: {sys.platform}")
        if not self.is_frozen:
            self.logger.warning("当前处于开发环境")

        try:
            maintenance_results = apply_pending_debug_maintenance(self.data_path)
        except OSError:
            self.logger.exception("执行待处理的调试维护操作失败")
        else:
            self.logger.debug("待处理的调试维护任务数量: %d", len(maintenance_results))
            for result in maintenance_results:
                self.logger.warning("已执行调试维护操作 %s，备份位置: %s", result.action, result.backup_path or "无")

        self.context = create_application(self.runtime_info)
        self.config = self.context.state.config
        self.debug = self.context.state.debug
        if self.debug:
            self.logging.set_level(logging.DEBUG)
        self.context.events.subscribe("config:updated", self._on_config_updated)
        self.logger.debug(
            "后端服务已就绪: accounts=%s, game=%s, plugins=%s",
            type(self.context.accounts).__name__,
            type(self.context.game).__name__,
            type(self.context.plugins).__name__,
        )
        self.logger.info("后端初始化完成")

    def _require_context(self) -> ApplicationContext:
        """
        返回已经初始化的应用上下文。

        :return: 当前应用上下文
        :raises RuntimeError: 后端尚未完成初始化
        """
        if self.context is None:
            raise RuntimeError("后端尚未初始化")
        return self.context

    def _shutdown(self) -> None:
        """
        幂等关闭后端上下文，并在最后刷新日志处理器。
        """
        if self._shutdown_complete:
            self.logger.debug("忽略重复的启动器关闭请求")
            return
        self._shutdown_complete = True
        self.logger.debug("开始关闭启动器后端")
        if self.context is not None:
            self.context.close()
            self.context = None
        self.logger.debug("启动器后端已关闭")
        self.logging.shutdown()

    def _on_config_updated(self, section: str, data: Any) -> None:
        """
        同步启动器镜像状态，并即时应用 Debug 日志级别。

        :param section: 被修改的配置分区
        :param data: 分区更新后的配置数据
        """
        if section != "launcher" or self.context is None:
            return
        self.config = self.context.state.config
        self.debug = self.context.state.debug
        self.logging.set_level(logging.DEBUG if self.debug else logging.INFO)
        self.logger.debug("Debug 日志已%s", "启用" if self.debug else "关闭")


__all__ = ["EuoraCraftLauncher", "LauncherExitCode"]
