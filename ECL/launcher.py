import shutil
import sys
from pathlib import Path

import colorama

from .common.logger import LoggerManager, get_logger
from .common.state import AppState

logger = get_logger("launcher")


class EuoraCraftLauncher:
    def __init__(self) -> None:
        self.config: dict | None = None
        self.debug_mode: bool = False
        self.system_type: str = sys.platform
        self.work_dir: Path = Path.cwd()
        self.program_dir: Path = Path(sys.executable).parent
        self.executable_path: Path = Path(sys.executable)
        self.java_list: list[dict] = []
        self.core_dir: Path = self.work_dir / "ECL_Libs"
        self.state = AppState()

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
        logger.info("开始初始化默认皮肤目录...")
        logger.info(f"工作目录: {self.work_dir}")
        logger.info(f"程序目录: {self.program_dir}")

        possible_source_paths = [
            self.work_dir / "resources" / "Skins",
            self.program_dir / "resources" / "Skins",
            self.work_dir / "EuoraCraft-Launcher" / "resources" / "Skins",
        ]

        resources_skins = None
        for path in possible_source_paths:
            logger.debug(f"检查源路径: {path}")
            if path.exists() and path.is_dir():
                resources_skins = path
                logger.info(f"找到源目录: {resources_skins}")
                break

        if not resources_skins:
            logger.error("未找到默认皮肤源目录，尝试的路径:")
            for path in possible_source_paths:
                logger.error(f"  - {path}")
            return

        source_files = list(resources_skins.glob("*.png"))
        logger.info(f"源目录包含 {len(source_files)} 个皮肤文件")

        ecl_libs_skins = self.work_dir / "ECL_Libs" / "Skins"
        logger.info(f"目标目录: {ecl_libs_skins}")

        if ecl_libs_skins.exists():
            skin_files = list(ecl_libs_skins.glob("*.png"))
            if skin_files:
                logger.info(f"默认皮肤目录已存在且包含 {len(skin_files)} 个文件")
                return
            else:
                logger.info("默认皮肤目录为空，重新初始化")

        ecl_libs_skins.mkdir(parents=True, exist_ok=True)
        logger.info(f"创建目标目录: {ecl_libs_skins}")

        copied_count = 0
        failed_count = 0
        for skin_file in source_files:
            try:
                dest_file = ecl_libs_skins / skin_file.name
                shutil.copy2(skin_file, dest_file)
                copied_count += 1
                logger.info(f"复制皮肤文件: {skin_file.name} -> {dest_file}")
            except Exception as e:
                failed_count += 1
                logger.error(f"复制皮肤文件失败 {skin_file.name}: {e}")

        if copied_count > 0:
            logger.info(f"已初始化默认皮肤目录，成功复制了 {copied_count} 个文件")
            if failed_count > 0:
                logger.warning(f"有 {failed_count} 个文件复制失败")
        else:
            logger.warning("未找到任何默认皮肤文件")

    def __check_game_paths(self) -> None:
        logger.info("检查游戏目录...")

        game_config = self.state.config_manager.get_game_config()
        paths = game_config.get("minecraft_paths", [])

        has_default = any((p.get("path", "") if isinstance(p, dict) else p) == "./.minecraft" for p in paths)

        if not has_default:
            logger.info("默认路径 ./.minecraft 不在配置中，自动添加")
            self.state.config_manager.update_game_config(
                {"minecraft_paths": [{"name": "默认路径", "path": "./.minecraft", "protected": True}, *paths]}
            )

        path_status = self.state.config_manager.check_game_paths_exist()

        for status in path_status:
            if status["exists"]:
                logger.info(f"游戏目录已就绪: {status['name']} ({status['path']})")
            else:
                if status["raw_path"] == "./.minecraft":
                    logger.info(f"默认游戏目录不存在，正在创建: {status['raw_path']}")
                    self.state.config_manager.init_game_paths()
                    logger.info(f"默认游戏目录已创建: {status['path']}")
                else:
                    logger.warning(f"自定义游戏目录不存在: {status['name']} ({status['raw_path']})")

    def init_launcher(self) -> bool:
        logger.info("EuoraCraft Launcher 启动中...")

        try:
            self.__init_system_test()
            logger.info(f"当前工作目录：{self.work_dir}")
            logger.info(f"执行文件路径：{self.executable_path}")
            logger.info(f"程序目录：{self.program_dir}")

            self.__check_launcher_coredir()

            if not self.state.initialize():
                logger.error("全局状态初始化失败")
                sys.exit(1)

            self.config = self.state.config_manager.config
            self.__handle_version_info()
            self.__check_game_paths()

            launcher_cfg = self.state.config_manager.get_launcher_config()
            self.debug_mode = bool(launcher_cfg.get("debug", False))
            logger.info(f"调试模式: {self.debug_mode}")

            if self.debug_mode:
                LoggerManager().set_level(10)
                logger.debug("调试模式已启用")
                import json

                logger.debug(f"完整配置内容：\n{json.dumps(self.config, ensure_ascii=False, indent=2)}")

            return True

        except Exception as e:
            logger.error(f"初始化启动器时出错: {e}")
            return False

    def run(self) -> None:
        if not self.init_launcher():
            sys.exit(1)
        try:
            from .adapters.webview import run_ui

            run_ui(self.state, self.debug_mode)
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在关闭...")
        finally:
            self.state.shutdown()
            logger.info("程序已安全退出")
