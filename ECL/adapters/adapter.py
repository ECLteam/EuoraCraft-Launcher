from pathlib import Path
from typing import TYPE_CHECKING

from anyio.from_thread import start_blocking_portal
from pytauri import Commands
from pytauri_wheel.lib import builder_factory, context_factory

from ECL.Api.frontend import FrontendApi
from ECL.Utils.logger import get_logger

if TYPE_CHECKING:
    from ECL.lunacher import EuoraCraftLauncher


class Adapter:
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
        self.tauri_config: dict = None
        self.launcher_instance = launcher_instance
        self.app_path: Path = self.launcher_instance.app_path
        self.is_frozen: bool = self.launcher_instance.is_frozen
        self.config: dict = self.launcher_instance.config
        self.launcher_version: str = self.launcher_instance.launcher_version
        self.fronteanapi_instance = FrontendApi()

    def run_adapter(self) -> bool:
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
                        "decorations": self.config.get("tauri", {}).get("decorations", False),
                        "title": self.config.get("tauri", {}).get("title", "EuoraCraft Launcher"),
                        "width": self.config.get("tauri", {}).get("width", 950),
                        "height": self.config.get("tauri", {}).get("height", 600),
                        "minWidth": 950,
                        "minHeight": 600,
                        "visible": False,
                    }
                ]
            },
        }
        with start_blocking_portal("asyncio") as portal:
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
        try:
            self.commands.command("frontend_ready")(self.fronteanapi_instance.frontend_ready)
            self.commands.command("ping")(self.fronteanapi_instance.ping)
            return True
        except Exception:
            return False
