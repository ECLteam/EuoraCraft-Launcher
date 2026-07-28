from pathlib import Path
from typing import TYPE_CHECKING

from anyio.from_thread import start_blocking_portal
from pytauri import Commands
from pytauri_wheel.lib import builder_factory, context_factory

from ECL.Api.frontend import FrontendApi
from ECL.Utils.logger import get_logger

if TYPE_CHECKING:
    from ECL.launcher import EuoraCraftLauncher


class Adapter:
    """PyTauri 前端适配器，负责注册 IPC 命令并启动 Tauri 应用"""

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, launcher_instance: "EuoraCraftLauncher"):
        if self._initialized:
            return
        self.logger = get_logger("Adapter")
        self._initialized: bool = True
        self.commands = Commands()
        self.tauri_config: dict | None = None # tauri配置
        self.launcher_instance = launcher_instance
        self.app_path: Path = self.launcher_instance.app_path # 启动器运行目录
        self.is_frozen: bool = self.launcher_instance.is_frozen # 是否已经打包
        self.config: dict = self.launcher_instance.config# 配置
        self.launcher_version: str = self.launcher_instance.launcher_version # 启动器版本
        self.frontend_api_instance = FrontendApi(self.launcher_instance)

    def run_adapter(self) -> bool:
        """
        启动 Tauri 前端适配器
        :return: 适配器是否正常退出
        """
        self.logger.info("正在初始化前端适配器")
        if not self._api():
            self.logger.info("前端命令注册失败")
            return False
        self.tauri_config = {
            "version": self.launcher_version,
            "build": {"frontendDist": self.config.get("tauri", {}).get("frontenddist", "frontend/dist")},
            "app": {
                "windows": [
                    {
                        "decorations": False,
                        "transparent": True,
                        "title": self.config.get("tauri", {}).get("title", "EuoraCraft Launcher"),
                        "width": self.config.get("tauri", {}).get("width", 900),
                        "height": self.config.get("tauri", {}).get("height", 600),
                        "minWidth": 966, # 真奇葩，窗口会无缘无故多了几个px出来
                        "minHeight": 609,
                        "visible": False, # 初始不可见，前端加载完成后可见
                    }
                ]
            },
        }
        with start_blocking_portal("asyncio") as portal: # 允许异步方法
            context = context_factory(self.app_path, tauri_config=self.tauri_config)
            app = builder_factory().build(
                context=context,
                invoke_handler=self.commands.generate_handler(portal),
            )
            self.logger.info("初始化前端适配器完成")
            app.run_return()
            self.logger.info("前端已退出")
            return True

    def _api(self) -> bool:
        """注册全部 IPC 命令"""
        try:
            api = self.frontend_api_instance

            # ---------- 基础 ----------
            self.commands.command("frontend_ready")(api.frontend_ready)
            self.commands.command("ping")(api.ping)

            # ---------- 配置 ----------
            self.commands.command("config_get")(api.config_get)
            self.commands.command("config_set")(api.config_set)
            self.commands.command("config_list")(api.config_list)
            self.commands.command("config_get_all")(api.config_get_all)
            self.commands.command("config_get_many")(api.config_get_many)

            # ---------- Java ----------
            self.commands.command("java_scan")(api.java_scan)
            self.commands.command("java_list")(api.java_list)

            # ---------- 游戏版本 ----------
            self.commands.command("minecraft_versions")(api.minecraft_versions)
            self.commands.command("minecraft_versions_classified")(api.minecraft_versions_classified)
            self.commands.command("fabric_versions")(api.fabric_versions)
            self.commands.command("forge_versions")(api.forge_versions)
            self.commands.command("neoforge_versions")(api.neoforge_versions)
            self.commands.command("optifine_versions")(api.optifine_versions)
            self.commands.command("quilt_versions")(api.quilt_versions)
            self.commands.command("scan_versions")(api.scan_versions)
            self.commands.command("install_version")(api.install_version)
            self.commands.command("uninstall_version")(api.uninstall_version)

            # ---------- 账户 ----------
            self.commands.command("accounts_list")(api.accounts_list)
            self.commands.command("accounts_current")(api.accounts_current)
            self.commands.command("accounts_add_offline")(api.accounts_add_offline)
            self.commands.command("accounts_add_authlib")(api.accounts_add_authlib)
            self.commands.command("accounts_start_microsoft_login")(api.accounts_start_microsoft_login)
            self.commands.command("accounts_poll_microsoft_login")(api.accounts_poll_microsoft_login)
            self.commands.command("accounts_complete_microsoft_login")(api.accounts_complete_microsoft_login)
            self.commands.command("accounts_switch")(api.accounts_switch)
            self.commands.command("accounts_remove")(api.accounts_remove)
            self.commands.command("accounts_refresh_profile")(api.accounts_refresh_profile)
            self.commands.command("authlib_servers")(api.authlib_servers)

            # ---------- 用户协议 ----------
            self.commands.command("user_agreement_get")(api.user_agreement_get)
            self.commands.command("user_agreement_save")(api.user_agreement_save)
            self.commands.command("user_agreement_clear")(api.user_agreement_clear)

            # ---------- 图片和文件选择 ----------
            self.commands.command("image_fetch_data_url")(api.image_fetch_data_url)
            self.commands.command("image_save_url")(api.image_save_url)
            self.commands.command("image_read_file")(api.image_read_file)
            self.commands.command("avatar_data_url")(api.avatar_data_url)
            self.commands.command("select_directory")(api.select_directory)
            self.commands.command("select_java")(api.select_java)
            self.commands.command("select_image")(api.select_image)
            self.commands.command("select_file")(api.select_file)
            self.commands.command("open_folder")(api.open_folder)
            self.commands.command("open_url")(api.open_url)

            # ---------- 游戏实例和日志 ----------
            self.commands.command("instances_list")(api.instances_list)
            self.commands.command("launch_instance")(api.launch_instance)
            self.commands.command("cancel_launch")(api.cancel_launch)
            self.commands.command("instance_stop")(api.instance_stop)
            self.commands.command("export_logs")(api.export_logs)

            # ---------- 插件 ----------
            self.commands.command("plugin_list")(api.plugin_list)
            self.commands.command("plugin_info")(api.plugin_info)
            self.commands.command("plugin_enable")(api.plugin_enable)
            self.commands.command("plugin_disable")(api.plugin_disable)
            self.commands.command("plugin_unload")(api.plugin_unload)
            self.commands.command("plugin_reload")(api.plugin_reload)
            self.commands.command("plugin_install")(api.plugin_install)
            self.commands.command("plugin_get_routes")(api.plugin_get_routes)
            self.commands.command("plugin_get_slots")(api.plugin_get_slots)
            self.commands.command("plugin_call_command")(api.plugin_call_command)
            self.commands.command("plugin_get_settings")(api.plugin_get_settings)
            self.commands.command("plugin_update_setting")(api.plugin_update_setting)

            # ---------- Mod 管理 ----------
            self.commands.command("get_mods")(api.get_mods)
            self.commands.command("toggle_mod")(api.toggle_mod)
            self.commands.command("add_mod")(api.add_mod)
            self.commands.command("remove_mod")(api.remove_mod)
            self.commands.command("open_mods_folder")(api.open_mods_folder)

            # ---------- 整合包和游戏资源 ----------
            self.commands.command("detect_modpack_type")(api.detect_modpack_type)
            self.commands.command("import_modpack")(api.import_modpack)
            self.commands.command("export_modpack")(api.export_modpack)
            self.commands.command("list_resourcepacks")(api.list_resourcepacks)
            self.commands.command("list_shaderpacks")(api.list_shaderpacks)
            self.commands.command("list_saves")(api.list_saves)
            self.commands.command("remove_resourcepack")(api.remove_resourcepack)
            self.commands.command("remove_shaderpack")(api.remove_shaderpack)
            self.commands.command("delete_save")(api.delete_save)
            self.commands.command("open_resourcepacks_folder")(api.open_resourcepacks_folder)
            self.commands.command("open_shaderpacks_folder")(api.open_shaderpacks_folder)
            self.commands.command("open_saves_folder")(api.open_saves_folder)

            # ---------- 在线 Mod ----------
            self.commands.command("search_mods")(api.search_mods)
            self.commands.command("get_mod_info")(api.get_mod_info)
            self.commands.command("get_mod_versions")(api.get_mod_versions)
            self.commands.command("download_mod")(api.download_mod)

            # ---------- 启动器信息 ----------
            self.commands.command("launcher_info")(api.launcher_info)
            self.commands.command("info_card_get")(api.info_card_get)
            self.commands.command("list_sections")(api.list_sections)

            # ---------- 文件系统和路径 ----------
            self.commands.command("fs_read_dir")(api.fs_read_dir)
            self.commands.command("fs_read_file")(api.fs_read_file)
            self.commands.command("fs_exists")(api.fs_exists)
            self.commands.command("file_resolve")(api.file_resolve)

            return True
        except Exception:
            self.logger.exception("注册 IPC 命令时发生异常")
            return False