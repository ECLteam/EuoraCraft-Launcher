from typing import Any

from pytauri.ipc import WebviewWindow

from ECL.Utils.logger import get_logger


class FrontendApi:
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.logger = get_logger("FrontendApi")

    async def frontend_ready(self, body: dict[str, Any], webview_window: WebviewWindow) -> dict[str, Any]:
        webview_window.show()
        self.logger.info("前端加载完成，已显示主窗口")
        return {"success": True}
    
    async def ping(self, body: dict[str, Any]) -> dict[str, Any]:
        return { "status": "ok", "message": "正常" }
