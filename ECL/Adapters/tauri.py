from pathlib import Path
from typing import Any

from anyio.from_thread import start_blocking_portal
from pytauri import Commands
from pytauri_plugins.dialog import init as dialog_init
from pytauri_wheel.lib import builder_factory, context_factory

from ECL.Api import FrontendApi
from ECL.Events import EventBus
from ECL.Infrastructure import get_logger


class Adapter:
    """PyTauri 前端适配器，负责注册 IPC 命令并启动 Tauri 应用"""

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.logger = get_logger("Adapter")
        self._initialized: bool = True
        self.commands = Commands()
        launcher = EventBus()["launcher"]
        self.tauri_config: dict | None = None  # tauri配置
        self.resource_path: Path = launcher.resource_path  # 前端等只读资源目录
        self.is_frozen: bool = launcher.is_frozen  # 是否已经打包
        self.config: dict = launcher.config  # 配置
        self.launcher_version: str = launcher.launcher_version  # 启动器版本
        self.plugin_framework_instance = EventBus()["plugins"]
        self.frontend_api_instance = FrontendApi()

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
                        "minWidth": 966,  # 真奇葩，窗口会无缘无故多了几个px出来
                        "minHeight": 609,
                        "visible": False,  # 初始不可见，前端加载完成后可见
                    }
                ]
            },
        }
        with start_blocking_portal("asyncio") as portal:  # 允许异步方法
            context = context_factory(self.resource_path, tauri_config=self.tauri_config)
            app = builder_factory().build(
                context=context,
                invoke_handler=self.commands.generate_handler(portal),
                plugins=[dialog_init()],
            )
            self.logger.info("初始化前端适配器完成")
            app.run_return()
            self.logger.info("前端已退出")
            return True

    def _api(self) -> bool:
        """注册全部 IPC 命令"""
        try:
            api = self.frontend_api_instance

            self.commands.command("frontend_ready")(api.frontend_ready)
            self.commands.command("ping")(api.ping)

            self.commands.command("config_get")(api.config_get)
            self.commands.command("config_set")(api.config_set)
            self.commands.command("config_list")(api.config_list)
            self.commands.command("config_get_all")(api.config_get_all)
            self.commands.command("config_get_many")(api.config_get_many)

            self.commands.command("java_scan")(api.java_scan)
            self.commands.command("java_list")(api.java_list)

            self.commands.command("minecraft_versions")(api.minecraft_versions)
            self.commands.command("minecraft_versions_classified")(api.minecraft_versions_classified)
            self.commands.command("fabric_versions")(api.fabric_versions)
            self.commands.command("forge_versions")(api.forge_versions)
            self.commands.command("neoforge_versions")(api.neoforge_versions)
            self.commands.command("optifine_versions")(api.optifine_versions)
            self.commands.command("quilt_versions")(api.quilt_versions)
            self.commands.command("scan_versions")(api.scan_versions)
            # 临时禁用：游戏安装相关 IPC
            # self.commands.command("install_version")(api.install_version)
            # self.commands.command("uninstall_version")(api.uninstall_version)

            self.commands.command("accounts_list")(api.accounts_list)
            self.commands.command("accounts_current")(api.accounts_current)
            self.commands.command("accounts_add_offline")(api.accounts_add_offline)
            self.commands.command("accounts_add_authlib")(api.accounts_add_authlib)
            self.commands.command("accounts_microsoft_login_config")(api.accounts_microsoft_login_config)
            self.commands.command("accounts_start_microsoft_login")(api.accounts_start_microsoft_login)
            self.commands.command("accounts_poll_microsoft_login")(api.accounts_poll_microsoft_login)
            self.commands.command("accounts_cancel_microsoft_login")(api.accounts_cancel_microsoft_login)
            self.commands.command("accounts_complete_microsoft_login")(api.accounts_complete_microsoft_login)
            self.commands.command("accounts_switch")(api.accounts_switch)
            self.commands.command("accounts_remove")(api.accounts_remove)
            self.commands.command("accounts_refresh_profile")(api.accounts_refresh_profile)
            self.commands.command("authlib_servers")(api.authlib_servers)

            self.commands.command("user_agreement_get")(api.user_agreement_get)
            self.commands.command("user_agreement_save")(api.user_agreement_save)
            self.commands.command("user_agreement_clear")(api.user_agreement_clear)

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

            self.commands.command("instances_list")(api.instances_list)
            # 临时禁用：游戏启动相关 IPC
            # self.commands.command("launch_instance")(api.launch_instance)
            # self.commands.command("cancel_launch")(api.cancel_launch)
            # self.commands.command("instance_stop")(api.instance_stop)
            self.commands.command("export_logs")(api.export_logs)

            self.commands.command("plugin_list")(api.plugin_list)
            self.commands.command("plugin_info")(api.plugin_info)
            self.commands.command("plugin_enable")(api.plugin_enable)
            self.commands.command("plugin_disable")(api.plugin_disable)
            self.commands.command("plugin_unload")(api.plugin_unload)
            self.commands.command("plugin_reload")(api.plugin_reload)
            self.commands.command("plugin_install")(api.plugin_install)
            self.commands.command("plugin_get_routes")(api.plugin_get_routes)
            self.commands.command("plugin_get_slots")(api.plugin_get_slots)
            self.commands.command("plugin_get_vue_slots")(api.plugin_get_vue_slots)
            self.commands.command("plugin_get_vue_components")(api.plugin_get_vue_components)
            self.commands.command("plugin_call_command")(api.plugin_call_command)
            self.commands.command("plugin_get_settings")(api.plugin_get_settings)
            self.commands.command("plugin_update_setting")(api.plugin_update_setting)

            self.commands.command("get_mods")(api.get_mods)
            self.commands.command("toggle_mod")(api.toggle_mod)
            self.commands.command("add_mod")(api.add_mod)
            self.commands.command("remove_mod")(api.remove_mod)
            self.commands.command("open_mods_folder")(api.open_mods_folder)

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

            self.commands.command("search_mods")(api.search_mods)
            self.commands.command("get_mod_info")(api.get_mod_info)
            self.commands.command("get_mod_versions")(api.get_mod_versions)
            self.commands.command("download_mod")(api.download_mod)

            self.commands.command("launcher_info")(api.launcher_info)
            self.commands.command("info_card_get")(api.info_card_get)
            self.commands.command("list_sections")(api.list_sections)
            self.commands.command("debug_reset_launcher_data")(api.debug_reset_launcher_data)
            self.commands.command("debug_clear_plugins")(api.debug_clear_plugins)

            self.commands.command("fs_read_dir")(api.fs_read_dir)
            self.commands.command("fs_read_file")(api.fs_read_file)
            self.commands.command("fs_exists")(api.fs_exists)
            self.commands.command("file_resolve")(api.file_resolve)

            # 订阅内部事件，转发到前端（前端就绪后才实际推送）
            EventBus().subscribe("config:updated", self._forward_config_to_frontend)
            EventBus().subscribe("accounts:changed", self._forward_accounts_to_frontend)
            EventBus().subscribe("accounts:microsoft_login_status", self._forward_microsoft_login_to_frontend)
            EventBus().subscribe("launcher:error", api.emit_error_to_frontend)
            EventBus().subscribe("launcher:popup", api.emit_popup_to_frontend)
            EventBus().subscribe(
                "game:install_progress",
                lambda payload: api.emit_to_frontend("game:install_progress", payload),
            )
            EventBus().subscribe(
                "game:launch_progress",
                lambda payload: api.emit_to_frontend("game:launch_progress", payload),
            )
            self._subscribe_plugin_events()

            return True
        except Exception:
            self.logger.exception("注册 IPC 命令时发生异常")
            return False

    def _forward_config_to_frontend(self, section: str, data: Any) -> None:
        """
        将配置变更事件转发到前端，前端可据此刷新 UI 状态
        :param section: 变更的配置分区
        :param data: 变更后的配置数据
        """
        self.frontend_api_instance.emit_to_frontend("config:updated", {"section": section, "data": data})

    def _forward_accounts_to_frontend(self, data: dict[str, Any]) -> None:
        self.frontend_api_instance.emit_to_frontend("accounts_changed", data)

    def _forward_microsoft_login_to_frontend(self, data: dict[str, Any]) -> None:
        self.frontend_api_instance.emit_to_frontend("accounts_microsoft_login_status", data)

    def _subscribe_plugin_events(self) -> None:
        """订阅插件系统事件，转换为前端期望的格式后推送"""
        bus = EventBus()
        api = self.frontend_api_instance

        # 状态变更：plugin:enabled / plugin:disabled / plugin:unloaded → plugin:status_changed
        def on_enabled(plugin):
            api.emit_to_frontend("plugin:status_changed", {"name": plugin.name, "action": "enabled", "result": True})
            # 前端就绪后通知插件注入 UI 资源
            self.plugin_framework_instance.on_frontend_ready()

        bus.subscribe("plugin:enabled", on_enabled)

        def on_disabled(plugin):
            api.emit_to_frontend("plugin:status_changed", {"name": plugin.name, "action": "disabled", "result": True})

        bus.subscribe("plugin:disabled", on_disabled)

        def on_unloaded(name):
            api.emit_to_frontend("plugin:status_changed", {"name": name, "action": "unloaded", "result": True})

        bus.subscribe("plugin:unloaded", on_unloaded)

        def on_installed(name):
            api.emit_to_frontend("plugin:installed", {"name": name})

        bus.subscribe("plugin:installed", on_installed)

        # 前端资源注入：直接转发
        bus.subscribe(
            "plugin:css_injected",
            lambda *args: api.emit_to_frontend("plugin:css_injected", {"plugin": args[0], "css": args[1]}),
        )
        bus.subscribe(
            "plugin:html_injected",
            lambda *args: api.emit_to_frontend(
                "plugin:html_injected", {"plugin": args[0], "slot": args[1], "html": args[2]}
            ),
        )
        bus.subscribe(
            "plugin:script_injected",
            lambda *args: api.emit_to_frontend("plugin:script_injected", {"plugin": args[0], "script": args[1]}),
        )
        bus.subscribe(
            "plugin:typescript_injected",
            lambda *args: api.emit_to_frontend("plugin:typescript_injected", {"plugin": args[0], "script": args[1]}),
        )

        # 路由注册
        bus.subscribe(
            "plugin:route_registered",
            lambda *args: api.emit_to_frontend(
                "plugin:route_registered",
                {"plugin": args[0], "path": args[1], "title": args[2], "icon": args[3] if len(args) > 3 else ""},
            ),
        )

        # 设置变更
        bus.subscribe(
            "plugin:settings_changed",
            lambda *args: api.emit_to_frontend(
                "plugin:settings_changed",
                {"plugin": args[0], "key": args[1], "old_value": args[2], "new_value": args[3]},
            ),
        )

        # Vue 组件注册
        bus.subscribe(
            "plugin:vue_slot_registered",
            lambda *args: api.emit_to_frontend(
                "plugin:vue_slot_registered",
                {
                    "plugin": args[0],
                    "slot": args[1],
                    "component_name": args[2],
                    "template": args[3],
                    "script": args[4],
                    "style": args[5],
                },
            ),
        )
        bus.subscribe(
            "plugin:vue_route_registered",
            lambda *args: api.emit_to_frontend(
                "plugin:vue_route_registered",
                {
                    "plugin": args[0],
                    "path": args[1],
                    "title": args[2],
                    "component_name": args[3],
                    "template": args[4],
                    "script": args[5],
                    "style": args[6],
                    "icon": args[7] if len(args) > 7 else "",
                },
            ),
        )
