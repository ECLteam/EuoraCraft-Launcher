from __future__ import annotations

from typing import Any

from ..auth.manager import AccountManager
from ..java.detector import JavaDetector
from ..java.models import JavaInfo
from .config import ConfigManager
from .logger import get_logger

logger = get_logger("state")


class AppState:
    _instance: AppState | None = None

    def __new__(cls) -> AppState:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return
        self.config_manager: ConfigManager = ConfigManager()
        self.account_manager: AccountManager = AccountManager()
        self.java_list: list[JavaInfo] = []
        self.version_info: dict[str, Any] = {}
        self._initialized: bool = False

    @property
    def initialized(self) -> bool:
        return self._initialized

    def initialize(self) -> bool:
        if self._initialized:
            return True
        try:
            logger.info("正在初始化应用全局状态...")

            self.config_manager.load()
            error = self.config_manager.validate()
            if error:
                logger.error(f"配置校验失败: {error}")
                return False

            self.version_info = self.config_manager.get_launcher_config()

            logger.info("开始扫描 Java 环境...")
            self.java_list = JavaDetector().detect_all()
            logger.info(f"Java 扫描完成，共找到 {len(self.java_list)} 个安装")

            logger.info("正在初始化账户管理器...")
            self.account_manager.initialize()

            self._initialized = True
            logger.info("应用全局状态初始化完成")
            return True
        except Exception as e:
            logger.error(f"初始化应用全局状态失败: {e}")
            return False

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
        logger.info("正在关闭应用全局状态...")
        self.account_manager.shutdown()
        logger.info("应用全局状态已关闭")
