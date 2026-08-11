import logging
import sys
from pathlib import Path
from typing import Any

from ECL.Adapters import Adapter
from ECL.Common import __version__, __version_type__, get_runtime_info
from ECL.Events import EventBus
from ECL.Infrastructure import ConfigManager, EnvManager, LoggerManager
from ECL.Plugin import PluginFramework
from ECL.Services import register_services
from ECL.Services.maintenance import apply_pending_debug_maintenance


class EuoraCraftLauncher:
    """EuoraCraft Launcher 主类"""

    def __init__(self) -> None:
        runtime_info = get_runtime_info()
        self.app_path: Path = runtime_info["app_path"]  # 获取启动器运行目录
        self.resource_path: Path = runtime_info["resource_path"]  # 获取资源目录
        self.launcher_version: str = __version__  # 启动器版本
        self.launcher_version_type: str = __version_type__  # alpha | beta | release
        self.debug: bool = False  # 调试模式
        self.is_frozen: bool = runtime_info["is_frozen"]  # 是否已经打包
        self.data_path: Path = self.app_path / "ECL_data"  # 数据目录
        self.config: dict[str, Any] = {}  # 配置
        self.plugin_framework_instance: PluginFramework | None = None
        self.service_instances: tuple[Any, ...] = ()
        self._shutdown_complete = False

        self.logger = LoggerManager(data_path=self.data_path).get_logger("EuoraCraft_Launcher")
        self.config_instance = ConfigManager(self.data_path)
        self.env_instance = EnvManager(self.app_path)

    def run(self) -> int:
        """
        启动器主入口
        :return: 启动器退出状态
        """
        self.logger.info("正在启动 EuoraCraft Launcher V%s %s", self.launcher_version, self.launcher_version_type)

        if self.launcher_version_type == "alpha":
            self.logger.warning("当前启动器版本为内部测试版本")
        elif self.launcher_version_type == "beta":
            self.logger.warning("当前启动器版本为测试版本，可能存在未知问题")

        try:
            self._initialize()
        except Exception:
            self.logger.exception("启动器初始化失败")
            self._shutdown()
            return 2

        try:
            self.logger.info("启动前端")
            Adapter().run()
        except Exception:
            self.logger.exception("前端适配器运行失败")
            return 3
        finally:
            self._shutdown()

        self.logger.info("启动器已退出")
        return 0

    def _initialize(self) -> None:
        self.logger.info("正在初始化启动器...")

        if sys.platform == "win32":
            self.logger.info("启动器运行系统: Windows")
        elif sys.platform == "linux":
            self.logger.info("启动器运行系统: Linux")
        elif sys.platform == "darwin":
            self.logger.info("启动器运行系统: MacOS")
        else:
            raise RuntimeError(f"不支持的系统环境: {sys.platform}")

        if not self.is_frozen:
            self.logger.warning("当前处于开发环境，可能会出现未知问题")

        self.logger.info("程序路径: %s", self.app_path)
        self.logger.info("资源路径: %s", self.resource_path)

        try:
            maintenance_results = apply_pending_debug_maintenance(self.data_path)  # 用来重置启动器的，真的有意义吗
        except OSError:
            self.logger.exception("执行待处理的调试维护操作失败")
        else:
            for result in maintenance_results:
                self.logger.warning(
                    "已执行调试维护操作 %s，备份位置: %s",
                    result.action,
                    result.backup_path or "无现有数据",
                )

        config = self.config_instance.get_config()  # 读取配置
        self.config = self.env_instance.apply_to_config(config)  # 使用环境变量覆盖配置

        if (self.config.get("launcher") or {}).get("debug"):  # 启用 debug 模式
            self.debug = True
            LoggerManager().set_level(logging.DEBUG)
            self.logger.warning("调试模式已启动")

        # 注册启动器基础共享实例到总线
        bus = EventBus()
        bus.register("config", self.config_instance)
        bus.register("env", self.env_instance)
        bus.register("launcher", self)

        self.service_instances = register_services(self.data_path, self.resource_path)
        self.plugin_framework_instance = PluginFramework()
        bus.register("plugins", self.plugin_framework_instance)
        self.plugin_framework_instance.initialize(self.data_path, self.resource_path)

        bus.subscribe("config:updated", self._on_config_updated)  # 订阅配置变更
        self.logger.info("初始化完成")

    def _shutdown(self) -> None:
        if self._shutdown_complete:
            return
        self._shutdown_complete = True
        self.logger.info("正在关闭启动器后端")

        if self.plugin_framework_instance is not None:
            try:
                self.plugin_framework_instance.close()
            except Exception:
                self.logger.exception("关闭插件框架失败")

        for service in reversed(self.service_instances):
            close = getattr(service, "close", None)
            if not callable(close):
                continue
            try:
                close()
            except Exception:
                self.logger.exception("关闭后端服务失败: %s", type(service).__name__)

        self.logger.info("启动器后端已关闭")

    def _on_config_updated(self, section: str, data: Any) -> None:
        if section != "launcher":
            return
        debug_enabled = bool((data or {}).get("debug", False))
        if debug_enabled == self.debug:
            return
        self.debug = debug_enabled
        LoggerManager().set_level(logging.DEBUG if debug_enabled else logging.INFO)
        self.logger.warning("调试模式已%s", "启用" if debug_enabled else "关闭")
