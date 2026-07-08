import asyncio
import logging
import shutil
import sys
from pathlib import Path

import colorama

from .common.logger import LoggerManager, get_logger
from .common.state import AppState

logger = get_logger("launcher")


class EuoraCraftLauncher:
    def __init__(self):
        self.config = None
        self.debug_mode = False
        self.system_type = sys.platform
        self.work_dir = Path.cwd()
        self.program_dir = Path(sys.executable).parent
        self.executable_path = Path(sys.executable)
        self.java_list = []
        self.core_dir = self.work_dir / "ECL_Libs"
        self.state = AppState()
        self._needs_password = False

    def __init_system_test(self) -> bool:
        logger.info(f"当前工作系统：{self.system_type}")
        if self.system_type == "win32":
            colorama.init()
            logger.info("已初始化 colorama")
            return True
        elif self.system_type == "linux" or self.system_type == "darwin":
            return True
        logger.warning(f"未知平台：{self.system_type}")
        return False

    def __handle_version_info(self) -> None:
        launcher_cfg = self.state.config_manager.get_launcher_config()
        version = launcher_cfg.get("version", "未知")
        version_type = launcher_cfg.get("version_type", "unknown")
        logger.info(f"启动器版本: v{version}")
        logger.info(f"启动器版本类型: {version_type}")
        if version_type == "dev":
            logger.warning("当前运行的是开发版本，可能存在不稳定因素")
        elif version_type == "beta":
            logger.warning("当前运行的是测试版本，可能存在一些问题")
        elif version_type == "release":
            logger.info("当前运行的是正式版本，祝您使用愉快！")
        else:
            logger.warning("未知的版本类型, 请移除配置文件并重启启动器")

    def __check_launcher_coredir(self) -> None:
        logger.info("检查启动器核心目录...")
        if not self.core_dir.is_dir():
            logger.warning(f"启动器核心目录不存在: {self.core_dir}")
            self.core_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"启动器核心目录已创建: {self.core_dir}")

        self.__init_skins_directory()

    def __init_skins_directory(self) -> None:
        # 目标目录
        ecl_skins = self.core_dir / "Skins"

        # 已有皮肤文件则跳过
        if ecl_skins.is_dir():
            existing = list(ecl_skins.glob("*.png"))
            if existing:
                logger.info(f"皮肤目录已就绪: {ecl_skins} ({len(existing)} 个文件)")
                return

        # 查找源目录：打包模式(sys._MEIPASS) > 开发模式(resources/Skins)
        source = self.__find_resource_dir(Path("resources") / "Skins")
        if source is None:
            logger.warning("未找到默认皮肤资源目录，跳过皮肤初始化")
            return

        source_files = list(source.glob("*.png"))
        if not source_files:
            logger.warning(f"皮肤资源目录为空: {source}")
            return

        ecl_skins.mkdir(parents=True, exist_ok=True)
        copied = 0
        for f in source_files:
            try:
                shutil.copy2(f, ecl_skins / f.name)
                copied += 1
            except OSError as e:
                logger.error(f"复制皮肤文件失败 {f.name}: {e}")
        logger.info(f"皮肤初始化完成: {copied} 个文件 -> {ecl_skins}")

    def __find_resource_dir(self, relative) -> Path | None:
        # 打包模式：从 PyInstaller 临时解压目录查找
        if getattr(sys, "frozen", False):
            base = Path(getattr(sys, "_MEIPASS", "."))
            p = base / relative
            if p.is_dir():
                return p
            return None

        # 开发模式：从项目根目录查找
        return self.work_dir / relative

    def __check_game_paths(self) -> None:
        logger.info("检查游戏目录...")

        path_status = self.state.config_manager.check_game_paths_exist()

        for status in path_status:
            if status["exists"]:
                logger.info(f"游戏目录已就绪: {status['name']} ({status['path']})")
            else:
                logger.info(f"游戏目录不存在，正在创建: {status['name']} ({status['raw_path']})")
                self.state.config_manager.init_game_paths()
                logger.info(f"游戏目录已创建: {status['path']}")

    def __setup_debug_mode(self) -> None:
        launcher_cfg = self.state.config_manager.get_launcher_config()
        self.debug_mode = bool(launcher_cfg.get("debug", False))
        logger.info(f"调试模式: {self.debug_mode}")
        if self.debug_mode:
            LoggerManager().set_level(logging.DEBUG)
            logger.debug("调试模式已启用")
            import json as _json

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("完整配置内容：\n%s", _json.dumps(self.config, ensure_ascii=False, indent=2))

    async def __preload_version_list(self) -> None:
        # 后台预加载 Minecraft 版本列表、最新 Fabric 版本和本地已安装版本，缓存到内存中
        try:
            logger.info("正在预加载 Minecraft 版本列表...")
            versions = await asyncio.to_thread(self.state.get_games.get_minecraft_versions)
            self.state.get_games._cached_versions = versions
            version_count = len(versions.get("All", [])) if versions else 0
            logger.info(f"Minecraft 版本列表预加载完成，共 {version_count} 个版本")

            # 预加载最新正式版的 Fabric 版本
            latest_release = versions.get("Latest", {}).get("release", "")
            if latest_release:
                try:
                    logger.info(f"正在预加载 Fabric 版本: {latest_release}")
                    fabric_versions = await asyncio.to_thread(self.state.get_games.get_fabric_versions, latest_release)
                    if fabric_versions:
                        fabric_versions["_game_version"] = latest_release
                    self.state.get_games._cached_fabric_versions = fabric_versions
                    fabric_count = len(fabric_versions.get("All", [])) if fabric_versions else 0
                    logger.info(f"Fabric 版本预加载完成，共 {fabric_count} 个")
                except (OSError, RuntimeError, ValueError, ConnectionError) as e:
                    logger.warning(f"Fabric 版本预加载失败（不影响启动）: {e}")

            # 预扫描第一个游戏路径的已安装版本
            game_paths = self.state.config_manager.get_game_config().get("minecraft_paths", [])
            if game_paths:
                first = game_paths[0]
                first_path = first.get("path", "") if isinstance(first, dict) else str(first)
                if first_path:
                    logger.info(f"正在预扫描已安装版本: {first_path}")
                    import json as _json
                    from pathlib import Path as _Path

                    versions_dir = _Path(first_path) / "versions"
                    cached_local = []
                    if versions_dir.is_dir():
                        for vjson in versions_dir.glob("*/*.json"):
                            try:
                                data = _json.loads(vjson.read_text("utf-8"))
                                cached_local.append(
                                    {
                                        "id": vjson.parent.name,
                                        "type": data.get("type", "unknown"),
                                        "inheritsFrom": data.get("inheritsFrom"),
                                        "path": str(vjson.parent),
                                    }
                                )
                            except (OSError, ValueError, KeyError):
                                pass
                    self.state._cached_local_versions = cached_local
                    logger.info(f"已安装版本预扫描完成，共 {len(cached_local)} 个版本")
        except (OSError, RuntimeError, ValueError) as e:
            logger.warning(f"版本列表预加载失败（不影响启动）: {e}")

    async def init_launcher_async(self):
        logger.info("EuoraCraft Launcher 异步启动中...")

        # Phase 1 串行：系统检测 + 目录创建 + 配置加载
        try:
            self.__init_system_test()
            logger.info(f"当前工作目录：{self.work_dir}")
            logger.info(f"执行文件路径：{self.executable_path}")
            logger.info(f"程序目录：{self.program_dir}")

            self.__check_launcher_coredir()
        except (OSError, RuntimeError) as e:
            logger.error(f"Phase 1 初始化失败: {e}")
            return False

        # Phase 2 并行：Java 扫描 + 账户初始化
        state_result = await self.state.initialize_async()
        self.config = self.state.config_manager.config

        # 记录密码需求状态，供 adapter 在 app 就绪后推送事件
        self._needs_password = state_result.get("needs_password", False)

        # Phase 3 收尾：版本信息 + 游戏目录检查 + 预加载数据
        try:
            self.__handle_version_info()
            self.__check_game_paths()

            self.__setup_debug_mode()

            # 后台预加载版本列表（不阻塞启动）
            _ = asyncio.create_task(self.__preload_version_list()) # noqa: RUF006

        except (OSError, RuntimeError, ValueError) as e:
            logger.error(f"Phase 3 收尾阶段异常: {e}")

        logger.info("EuoraCraft Launcher 异步初始化完成")
        return True

    def init_launcher(self) -> bool:
        try:
            return asyncio.run(self.init_launcher_async())
        except RuntimeError:
            # 已有事件循环在运行时回退到同步初始化
            logger.warning("事件循环已存在，回退到同步初始化")
            return self.__init_launcher_sync()

    def __init_launcher_sync(self) -> bool:
        logger.info("EuoraCraft Launcher 启动中...")

        try:
            self.__init_system_test()
            logger.info(f"当前工作目录：{self.work_dir}")
            logger.info(f"执行文件路径：{self.executable_path}")
            logger.info(f"程序目录：{self.program_dir}")

            self.__check_launcher_coredir()

            state_result = self.state.initialize()
            self.config = self.state.config_manager.config
            self._needs_password = state_result.get("needs_password", False)
            self.__handle_version_info()
            self.__check_game_paths()

            self.__setup_debug_mode()

            return True

        except (OSError, RuntimeError, ValueError) as e:
            logger.error(f"初始化启动器时出错: {e}")
            return False

    def run(self) -> None:
        if not self.init_launcher():
            sys.exit(1)
        try:
            from .adapters.adapter import run_app

            run_app(self)
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在关闭...")
        finally:
            logger.info("程序已安全退出")
