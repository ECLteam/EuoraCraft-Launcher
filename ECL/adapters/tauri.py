from pathlib import Path
from typing import Any

from anyio.from_thread import start_blocking_portal
from pytauri import Commands
from pytauri_plugins.dialog import init as dialog_init
from pytauri_wheel.lib import builder_factory, context_factory

from ECL.api import FrontendApi
from ECL.api.registry import command_handlers
from ECL.application import ApplicationContext
from ECL.utils import get_logger


class Adapter:
    """
    PyTauri 前端适配器，负责注册 IPC 命令并启动 Tauri 应用
    """

    def __init__(self, context: ApplicationContext) -> None:
        launcher = context.state
        self.context = context
        self.logger = get_logger("Adapter")
        self.commands = Commands()
        self.events = context.events
        self.resource_path: Path = launcher.resource_path  # 前端等只读资源目录
        self.config: dict[str, Any] = launcher.config  # 配置
        self.launcher_version: str = launcher.launcher_version  # 启动器版本
        self.frontend_api_instance = FrontendApi(context)

    def run(self) -> None:
        """
        启动 Tauri 前端。
        """
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
        for name, handler in command_handlers(api).items():
            self.commands.command(name)(handler)

    def _register_events(self) -> None:
        api = self.frontend_api_instance
        bus = self.events

        bus.subscribe(
            "config:updated",
            lambda section, data: api.emit_to_frontend("config:updated", {"section": section, "data": data}),
        )
        bus.subscribe(
            "accounts:changed",
            lambda data: api.emit_to_frontend("accounts_changed", data),
        )
        bus.subscribe(
            "accounts:microsoft_login_status",
            self._forward_microsoft_login_status,
        )
        bus.subscribe("launcher:error", api.emit_error_to_frontend)
        bus.subscribe("launcher:popup", api.emit_popup_to_frontend)
        bus.subscribe(
            "game:install_progress",
            lambda payload: api.emit_to_frontend("game:install_progress", payload),
        )
        bus.subscribe(
            "game:launch_progress",
            lambda payload: api.emit_to_frontend("game:launch_progress", payload),
        )
        bus.subscribe(
            "game:versions_changed",
            lambda payload: api.emit_to_frontend("game:versions_changed", payload),
        )
        bus.subscribe(
            "game:instances_changed",
            lambda payload: api.emit_to_frontend("game:instances_changed", payload),
        )

        # 插件状态发生变化时，前端只接收统一的 status_changed 事件
        bus.subscribe(
            "plugin:enabled",
            lambda plugin: api.emit_to_frontend(
                "plugin:status_changed", {"name": plugin.name, "action": "enabled", "result": True}
            ),
        )
        bus.subscribe(
            "plugin:disabled",
            lambda plugin: api.emit_to_frontend(
                "plugin:status_changed", {"name": plugin.name, "action": "disabled", "result": True}
            ),
        )
        bus.subscribe(
            "plugin:unloaded",
            lambda name: api.emit_to_frontend(
                "plugin:status_changed", {"name": name, "action": "unloaded", "result": True}
            ),
        )
        bus.subscribe(
            "plugin:installed",
            lambda name: api.emit_to_frontend("plugin:installed", {"name": name}),
        )
        bus.subscribe(
            "plugin:css_injected",
            lambda plugin, css, key: api.emit_to_frontend(
                "plugin:css_injected", {"plugin": plugin, "css": css, "key": key}
            ),
        )
        bus.subscribe(
            "plugin:html_injected",
            lambda plugin, slot, html, key: api.emit_to_frontend(
                "plugin:html_injected", {"plugin": plugin, "slot": slot, "html": html, "key": key}
            ),
        )
        bus.subscribe(
            "plugin:script_injected",
            lambda plugin, script: api.emit_to_frontend("plugin:script_injected", {"plugin": plugin, "script": script}),
        )
        bus.subscribe(
            "plugin:typescript_injected",
            lambda plugin, script: api.emit_to_frontend(
                "plugin:typescript_injected", {"plugin": plugin, "script": script}
            ),
        )
        bus.subscribe(
            "plugin:route_registered",
            lambda plugin, path, title, icon="": api.emit_to_frontend(
                "plugin:route_registered",
                {"plugin": plugin, "path": path, "title": title, "icon": icon},
            ),
        )
        bus.subscribe(
            "plugin:settings_changed",
            lambda plugin, key, old_value, new_value: api.emit_to_frontend(
                "plugin:settings_changed",
                {"plugin": plugin, "key": key, "old_value": old_value, "new_value": new_value},
            ),
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
        )

    def _forward_microsoft_login_status(self, data: dict[str, Any]) -> None:
        if data.get("focus"):
            self.frontend_api_instance.focus_window()
        self.frontend_api_instance.emit_to_frontend("accounts_microsoft_login_status", data)
