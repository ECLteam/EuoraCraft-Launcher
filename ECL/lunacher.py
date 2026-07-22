import sys
from pathlib import Path

from ECL.Adapters.adapter import Adapter
from ECL.Common.version import __version__, __version_type__
from ECL.Utils.config import ConfigManager
from ECL.Utils.env import EnvManager
from ECL.Utils.logger import LoggerManager, logging
from ECL.Utils.utils import get_runtime_info


class EuoraCraftLauncher:
    def __init__(self):
        self.runtime_info: dict = get_runtime_info()
        self.app_path: Path = Path(self.runtime_info.get("app_path"))
        self.is_frozen = self.runtime_info.get("is_frozen")
        self.system_type: str = None
        self.logger = LoggerManager().get_logger("EuoraCraftLauncher")
        self.system_type: str = sys.platform
        self.config: dict = None
        self.data_path: Path = self.app_path / "ECL_data"
        self.config_instance = ConfigManager(self.data_path)
        self.env_instance = EnvManager(self.app_path)
        self.launcher_version: str = __version__
        self.launcher_version_type: str = __version_type__
        self.env_data: dict = None
        self.debug: bool = False
        self.adapter_instance = None

    def main_run(self) -> bool:
        self.logger.info("正在启动 EuoraCraft Launcher")
        self.logger.info(f"当前运行版本为 {self.launcher_version} {self.launcher_version_type}")
        if self.launcher_version_type is not None:
            if self.launcher_version_type == "dev":
                self.logger.warning("当前启动器版本为开发版本")
            if self.launcher_version_type == "beta":
                self.logger.warning("当前启动器版本为测试版本，可能存在未知问题")
        if not self._init():
            self.logger.error("初始化失败")
            return False
        print(self.config)
        self.logger.info("启动前端")
        self.adapter_instance = Adapter(self)
        if self.adapter_instance.run_adapter():
            self.logger.info("开始退出程序")
        return True

    def _init(self) -> bool:
        """启动器初始化"""
        # 获取系统类型
        self.logger.info("正在初始化启动器...")
        if self.system_type == 'win32':
            self.system_type = 'Windows'
        elif self.system_type == 'linux':
            self.system_type = 'Linux'
        elif self.system_type == 'darwin':
            self.system_type = 'MacOS'
        else:
            self.logger.info("未知的系统环境")
            return False
        # self.logger.info(f"是否打包: {self.is_frozen}")
        if not self.is_frozen:
            self.logger.warning("当前处于开发环境,可能会出现未知问题")
        self.logger.info(f"启动器运行系统: {self.system_type}")
        self.logger.info(f"程序路径目录: {self.app_path}")
        self.logger.info("开始获取配置文件")
        self.config = self.config_instance.get_config() # 获取配置
        self.env_data = self.env_instance.get_env() # 获取环境变量
        # print(self.env_data)
        self.config = self.env_instance.config_replace(self.config) # 使用环境变量替换config
        print(self.config)
        if self.config["launcher"]["debug"]:
            self.debug = True
            LoggerManager().set_level(logging.DEBUG)
            self.logger.warning("调试模式已启动")
        self.logger.info("初始化完成")
        return True
