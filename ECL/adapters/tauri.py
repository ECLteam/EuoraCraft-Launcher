# ============================================================
# EuoraCraft Launcher
# ECLTeam © 2026 GPL-3.0 License
# https://github.com/ECLTeam/EuoraCraft-Launcher
#
# 文件作用：Tauri 宿主适配器：封装宿主侧回调与窗口环境访问。
#
# 公开接口：
#   - class Adapter — PyTauri 前端适配器，负责注册 IPC 命令并启动 Tauri 应用。
#       - run() -> None — 启动 Tauri 前端。
# ============================================================

from pathlib import Path
from typing import Any

from anyio.from_thread import start_blocking_portal
from pytauri import Commands
from pytauri_plugins.dialog import init as dialog_init
from pytauri_wheel.lib import builder_factory, context_factory

from ECL.api import FrontendApi
from ECL.api.registry import command_handlers
from ECL.application import ApplicationContext
from ECL.services.frontend_events import subscribe_all_frontend_events
from ECL.utils import get_logger


class Adapter:
    """
    PyTauri 前端适配器，负责注册 IPC 命令并启动 Tauri 应用。

    桥接后端事件总线与前端通道，将后端状态变更持久转发到 Tauri 前端。
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
        self.logger.info("正在初始化前端界面")
        self._register_commands()
        self._register_events()
        tauri_config = self._build_config()
        with start_blocking_portal("asyncio") as portal:  # 允许异步方法
            self.logger.debug("正在创建 Tauri 窗口")
            context = context_factory(self.resource_path, tauri_config=tauri_config)
            self.logger.debug("Tauri 窗口已创建")
            self.logger.debug("正在构建 Tauri 应用")
            app = builder_factory().build(
                context=context,
                invoke_handler=self.commands.generate_handler(portal),
                plugins=[dialog_init()],
            )
            self.logger.info("前端界面初始化完成")
            self.logger.info("Tauri 主循环已启动，正在等待前端就绪")
            app.run_return()
        self.logger.info("前端已退出")

    def _build_config(self) -> dict[str, Any]:
        # 根据配置拼装传给 Tauri 的应用配置结构。
        tauri_config = self.config.get("tauri", {})
        launcher_config = self.config.get("launcher") or {}
        # 开发模式下窗口默认可见，便于调试；生产环境初始隐藏，等待前端加载完成后再显示
        dev_mode = bool(launcher_config.get("debug", False))
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
                        "minWidth": 966,  # 补偿 Tauri 窗口在最小宽度下额外产生的空白像素
                        "minHeight": 609,
                        "visible": dev_mode,  # 开发模式可见；生产初始隐藏，前端加载完成后可见
                    }
                ]
            },
        }

    def _register_commands(self) -> None:
        # 将后端命令处理器注册为 Tauri 的 IPC 命令。
        api = self.frontend_api_instance
        logger = getattr(self, "logger", get_logger("Adapter"))
        handlers = command_handlers(api)
        for name, handler in handlers.items():
            self.commands.command(name)(handler)
        logger.debug("IPC 命令注册完成: count=%d", len(handlers))

    def _register_events(self) -> None:
        # 复用共享事件桥完成「后端事件 → 前端事件」的纯转换，仅保留含副作用的订阅。
        api = self.frontend_api_instance
        bus = self.events
        logger = getattr(self, "logger", get_logger("Adapter"))
        logger.debug("正在注册后端到前端的事件转发")

        subscribe_all_frontend_events(bus, api.emit_to_frontend)

        # 严重错误需要保留待确认的内存副本，供前端轮询补录；窗口侧副作用只在这些订阅里处理。
        bus.subscribe("launcher:error", api.emit_error_to_frontend)
        bus.subscribe(
            "accounts:microsoft_login_status",
            lambda data: api.focus_window() if data.get("focus") else None,
        )
        bus.subscribe(
            "plugin:disabled",
            lambda plugin: api.close_plugin_windows(plugin.name),
        )
        bus.subscribe(
            "plugin:unloaded",
            lambda name: api.close_plugin_windows(name),
        )
        logger.debug("后端到前端的事件转发注册完成")
