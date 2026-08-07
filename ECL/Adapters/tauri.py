from pathlib import Path
from typing import Any

from anyio.from_thread import start_blocking_portal
from pytauri import Commands
from pytauri_plugins.dialog import init as dialog_init
from pytauri_wheel.lib import builder_factory, context_factory

from ECL.Api import FrontendApi
from ECL.Events import EventBus
from ECL.Events.event_bus import LAUNCHER_OWNER
from ECL.Infrastructure import get_logger


class Adapter:
    """PyTauri 前端适配器，负责注册 IPC 命令并启动 Tauri 应用"""

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        launcher = EventBus()["launcher"]
        self.logger = get_logger("Adapter")
        self.commands = Commands()
        self.resource_path: Path = launcher.resource_path  # 前端等只读资源目录
        self.config: dict[str, Any] = launcher.config  # 配置
        self.launcher_version: str = launcher.launcher_version  # 启动器版本
        self.frontend_api_instance = FrontendApi()
        self._initialized = True

    def run(self) -> None:
        """启动 Tauri 前端。"""
        self.logger.info("正在初始化前端适配器")
        self._register_commands()
        self._register_events()
        tauri_config = self._build_config()
        with start_blocking_portal("asyncio") as portal:  # 允许异步方法
            context = context_factory(self.resource_path, tauri_config=tauri_config)
            app = builder_factory().build(
                context=context,
                invoke_handler=self.commands.generate_handler(portal),
                plugins=[dialog_init()],
            )
            self.logger.info("前端适配器初始化完成")
            app.run_return()
        self.logger.info("前端已退出")

    def _build_config(self) -> dict[str, Any]:
        tauri_config = self.config.get("tauri", {})
        return {
            "version": self.launcher_version,
            "build": {"frontendDist": tauri_config.get("frontenddist", "frontend/dist")},
            "app": {
                "windows": [
                    {
                        "decorations": False,
                        "transparent": True,
                        "title": tauri_config.get("title", "EuoraCraft Launcher"),
                        "width": tauri_config.get("width", 900),
                        "height": tauri_config.get("height", 600),
                        "minWidth": 966,  # 真奇葩，窗口会无缘无故多了几个px出来
                        "minHeight": 609,
                        "visible": False,  # 初始不可见，前端加载完成后可见
                    }
                ]
            },
        }

    def _register_commands(self) -> None:
        api = self.frontend_api_instance

        self.commands.command("frontend_ready")(api.frontend_ready)
        self.commands.command("ping")(api.ping)
        self.commands.command("system_memory")(api.system_memory)
        self.commands.command("java_scan")(api.java_scan)
        self.commands.command("java_list")(api.java_scan)

        self.commands.command("config_get")(api.config_get)
        self.commands.command("config_set")(api.config_set)
        self.commands.command("config_list")(api.config_list)
        self.commands.command("config_get_all")(api.config_get_all)
        self.commands.command("config_get_many")(api.config_get_many)

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

        self.commands.command("accounts_list")(api.accounts_list)
        self.commands.command("accounts_current")(api.accounts_current)
        self.commands.command("accounts_add_offline")(api.accounts_add_offline)
        self.commands.command("accounts_add_authlib")(api.accounts_add_authlib)
        self.commands.command("accounts_select_authlib_profile")(api.accounts_select_authlib_profile)
        self.commands.command("accounts_microsoft_login_config")(api.accounts_microsoft_login_config)
        self.commands.command("accounts_start_microsoft_login")(api.accounts_start_microsoft_login)
        self.commands.command("accounts_poll_microsoft_login")(api.accounts_poll_microsoft_login)
        self.commands.command("accounts_cancel_microsoft_login")(api.accounts_cancel_microsoft_login)
        self.commands.command("accounts_complete_microsoft_login")(api.accounts_complete_microsoft_login)
        self.commands.command("accounts_switch")(api.accounts_switch)
        self.commands.command("accounts_remove")(api.accounts_remove)
        self.commands.command("accounts_refresh_profile")(api.accounts_refresh_profile)
        self.commands.command("authlib_resolve_server")(api.authlib_resolve_server)
        self.commands.command("authlib_servers")(api.authlib_servers)

        self.commands.command("image_save_url")(api.image_save_url)
        self.commands.command("image_save_as")(api.image_save_as)
        self.commands.command("image_read_file")(api.image_read_file)
        self.commands.command("image_list_files")(api.image_list_files)
        self.commands.command("avatar_data_url")(api.avatar_data_url)
        self.commands.command("select_directory")(api.select_directory)
        self.commands.command("select_java")(api.select_java)
        self.commands.command("select_image")(api.select_image)
        self.commands.command("select_file")(api.select_file)
        self.commands.command("open_folder")(api.open_folder)
        self.commands.command("open_url")(api.open_url)

        self.commands.command("instances_list")(api.instances_list)
        self.commands.command("launch_instance")(api.launch_instance)
        self.commands.command("cancel_launch")(api.cancel_launch)
        self.commands.command("instance_stop")(api.instance_stop)

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
        self.commands.command("plugin_notify_sidebar_state")(api.plugin_notify_sidebar_state)

        self.commands.command("launcher_info")(api.launcher_info)
        self.commands.command("info_card_get")(api.info_card_get)
        self.commands.command("debug_reset_launcher_data")(api.debug_reset_launcher_data)
        self.commands.command("debug_clear_plugins")(api.debug_clear_plugins)

    def _register_events(self) -> None:
        api = self.frontend_api_instance
        bus = EventBus()

        bus.subscribe(
            "config:updated",
            lambda section, data: api.emit_to_frontend("config:updated", {"section": section, "data": data}),
            owner=LAUNCHER_OWNER,
        )
        bus.subscribe(
            "accounts:changed",
            lambda data: api.emit_to_frontend("accounts_changed", data),
            owner=LAUNCHER_OWNER,
        )
        bus.subscribe(
            "accounts:microsoft_login_status",
            self._forward_microsoft_login_status,
            owner=LAUNCHER_OWNER,
        )
        bus.subscribe("launcher:error", api.emit_error_to_frontend, owner=LAUNCHER_OWNER)
        bus.subscribe("launcher:popup", api.emit_popup_to_frontend, owner=LAUNCHER_OWNER)
        bus.subscribe(
            "game:install_progress",
            lambda payload: api.emit_to_frontend("game:install_progress", payload),
            owner=LAUNCHER_OWNER,
        )
        bus.subscribe(
            "game:launch_progress",
            lambda payload: api.emit_to_frontend("game:launch_progress", payload),
            owner=LAUNCHER_OWNER,
        )
        bus.subscribe(
            "game:versions_changed",
            lambda payload: api.emit_to_frontend("game:versions_changed", payload),
            owner=LAUNCHER_OWNER,
        )

        # 插件状态发生变化时，前端只接收统一的 status_changed 事件
        bus.subscribe(
            "plugin:enabled",
            lambda plugin: api.emit_to_frontend(
                "plugin:status_changed", {"name": plugin.name, "action": "enabled", "result": True}
            ),
            owner=LAUNCHER_OWNER,
        )
        bus.subscribe(
            "plugin:disabled",
            lambda plugin: api.emit_to_frontend(
                "plugin:status_changed", {"name": plugin.name, "action": "disabled", "result": True}
            ),
            owner=LAUNCHER_OWNER,
        )
        bus.subscribe(
            "plugin:unloaded",
            lambda name: api.emit_to_frontend(
                "plugin:status_changed", {"name": name, "action": "unloaded", "result": True}
            ),
            owner=LAUNCHER_OWNER,
        )
        bus.subscribe(
            "plugin:installed",
            lambda name: api.emit_to_frontend("plugin:installed", {"name": name}),
            owner=LAUNCHER_OWNER,
        )
        bus.subscribe(
            "plugin:css_injected",
            lambda plugin, css, key: api.emit_to_frontend(
                "plugin:css_injected", {"plugin": plugin, "css": css, "key": key}
            ),
            owner=LAUNCHER_OWNER,
        )
        bus.subscribe(
            "plugin:html_injected",
            lambda plugin, slot, html, key: api.emit_to_frontend(
                "plugin:html_injected", {"plugin": plugin, "slot": slot, "html": html, "key": key}
            ),
            owner=LAUNCHER_OWNER,
        )
        bus.subscribe(
            "plugin:script_injected",
            lambda plugin, script: api.emit_to_frontend("plugin:script_injected", {"plugin": plugin, "script": script}),
            owner=LAUNCHER_OWNER,
        )
        bus.subscribe(
            "plugin:typescript_injected",
            lambda plugin, script: api.emit_to_frontend(
                "plugin:typescript_injected", {"plugin": plugin, "script": script}
            ),
            owner=LAUNCHER_OWNER,
        )
        bus.subscribe(
            "plugin:route_registered",
            lambda plugin, path, title, icon="": api.emit_to_frontend(
                "plugin:route_registered",
                {"plugin": plugin, "path": path, "title": title, "icon": icon},
            ),
            owner=LAUNCHER_OWNER,
        )
        bus.subscribe(
            "plugin:settings_changed",
            lambda plugin, key, old_value, new_value: api.emit_to_frontend(
                "plugin:settings_changed",
                {"plugin": plugin, "key": key, "old_value": old_value, "new_value": new_value},
            ),
            owner=LAUNCHER_OWNER,
        )
        bus.subscribe(
            "plugin:vue_slot_registered",
            lambda plugin, slot, component_name, template, script, style: api.emit_to_frontend(
                "plugin:vue_slot_registered",
                {
                    "plugin": plugin,
                    "slot": slot,
                    "component_name": component_name,
                    "template": template,
                    "script": script,
                    "style": style,
                },
            ),
            owner=LAUNCHER_OWNER,
        )
        bus.subscribe(
            "plugin:vue_route_registered",
            lambda plugin, path, title, component_name, template, script, style, icon="": api.emit_to_frontend(
                "plugin:vue_route_registered",
                {
                    "plugin": plugin,
                    "path": path,
                    "title": title,
                    "component_name": component_name,
                    "template": template,
                    "script": script,
                    "style": style,
                    "icon": icon,
                },
            ),
            owner=LAUNCHER_OWNER,
        )

    def _forward_microsoft_login_status(self, data: dict[str, Any]) -> None:
        if data.get("focus"):
            self.frontend_api_instance.focus_window()
        self.frontend_api_instance.emit_to_frontend("accounts_microsoft_login_status", data)
