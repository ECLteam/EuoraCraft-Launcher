import urllib.request
from os import environ
from pathlib import Path
from typing import Any

from anyio.from_thread import start_blocking_portal
from pytauri import Commands
from pytauri_wheel.lib import builder_factory, context_factory

from ..api.handlers import Api
from ..common.logger import get_logger

logger = get_logger("tauri")
commands = Commands()

_launcher_instance = None


def set_launcher_instance(launcher):
    global _launcher_instance
    _launcher_instance = launcher


def _get_launcher():
    return _launcher_instance


@commands.command()
async def api_call(body: dict[str, Any]) -> Any:
    method = body.get("method")
    args = body.get("args") or []
    kwargs = body.get("kwargs") or {}

    launcher = _get_launcher()
    if launcher is None or not launcher.state.initialized:
        return {"success": False, "message": "启动器未初始化"}

    api = Api(launcher.state)

    if not hasattr(api, method):
        return {"success": False, "message": f"未知方法: {method}"}

    func = getattr(api, method)
    if not callable(func):
        return {"success": False, "message": f"不是可调用的方法: {method}"}

    try:
        result = func(*args, **kwargs)
        return result
    except Exception as e:
        return {"success": False, "message": f"调用失败: {e}"}


def _detect_dev_server(url: str = "http://localhost:5173") -> str | None:
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=1) as resp:
            if resp.status == 200:
                return url
    except Exception:
        pass
    return None


def run_tauri_app(launcher) -> int:
    set_launcher_instance(launcher)

    src_tauri_dir = Path(__file__).parent.parent.parent.absolute()

    dev_server = environ.get("DEV_SERVER")
    if dev_server is None:
        dev_server = _detect_dev_server()

    tauri_config = (
        {
            "build": {
                "frontendDist": dev_server,
            },
        }
        if dev_server is not None
        else None
    )

    with start_blocking_portal("asyncio") as portal:
        app = builder_factory().build(
            context=context_factory(src_tauri_dir, tauri_config=tauri_config),
            invoke_handler=commands.generate_handler(portal),
        )
        exit_code = app.run_return()
        logger.info("Tauri 应用已退出，开始清理资源...")
        if launcher is not None:
            launcher.state.shutdown()
        logger.info("资源清理完成")
        return exit_code
