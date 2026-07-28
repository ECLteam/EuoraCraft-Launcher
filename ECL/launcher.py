import sys
from pathlib import Path
from typing import Any

from ECL.Adapters.adapter import Adapter
from ECL.Common.version import __version__, __version_type__
from ECL.Utils.config import ConfigManager
from ECL.Utils.env import EnvManager
from ECL.Utils.logger import LoggerManager, logging
from ECL.Utils.utils import get_runtime_info


class EuoraCraftLauncher:
    """EuoraCraft Launcher 主入口"""

    def __init__(self):
        runtime_info = get_runtime_info()
        self.app_path: Path = Path(runtime_info["app_path"])
        self.launcher_version: str = __version__
        self.launcher_version_type: str = __version_type__
        self.debug: bool = False
        self.is_frozen: bool = runtime_info["is_frozen"]
        self.data_path: Path = self.app_path / "ECL_data"
        self.config: dict[str, Any] | None = None

        self.logger = LoggerManager().get_logger("EuoraCraftLauncher")
        self.config_instance = ConfigManager(self.data_path)
        self.env_instance = EnvManager(self.app_path)

    def main_run(self) -> bool:
        """
        启动器主入口
        :return: 启动是否成功
        """
        self.logger.info("正在启动 EuoraCraft Launcher V%s %s", self.launcher_version, self.launcher_version_type)

        if self.launcher_version_type == "alpha":
            self.logger.warning("当前启动器版本为开发版本")
        elif self.launcher_version_type == "beta":
            self.logger.warning("当前启动器版本为测试版本，可能存在未知问题")

        if not self._init():
            self.logger.error("初始化失败")
            return False

        self.logger.info("启动前端")
        adapter = Adapter(self)
        if not adapter.run_adapter():
            self.logger.error("前端适配器异常退出")
            return False

        self.logger.info("启动器已退出")
        return True

    # ---------- 初始化 ----------

    def _init(self) -> bool:
        """
        初始化启动器：系统检测、配置加载、环境变量覆盖
        :return: 初始化是否成功
        """
        self.logger.info("正在初始化启动器...")

        system = sys.platform
        if system == "win32":
            self.logger.info("启动器运行系统: Windows")
        elif system == "linux":
            self.logger.info("启动器运行系统: Linux")
        elif system == "darwin":
            self.logger.info("启动器运行系统: MacOS")
        else:
            self.logger.error("不支持的系统环境: %s", system)
            return False

        if not self.is_frozen:
            self.logger.warning("当前处于开发环境，可能会出现未知问题")

        self.logger.info("程序路径: %s", self.app_path)

        config = self.config_instance.get_config()
        config = self.env_instance.config_replace(config)
        self.config = config

        if (config.get("launcher") or {}).get("debug"):
            self.debug = True
            LoggerManager().set_level(logging.DEBUG)
            self.logger.warning("调试模式已启动")

        self.logger.info("初始化完成")
        return True