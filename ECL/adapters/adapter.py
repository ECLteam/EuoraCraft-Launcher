import inspect
import sys as _sys
from pathlib import Path
from typing import Any

from anyio.from_thread import start_blocking_portal
from pytauri import Commands
from pytauri_plugins import dialog
from pytauri_wheel.lib import builder_factory, context_factory

from ..api.handlers import Api
from ..common.logger import get_logger

logger = get_logger("adapter")


class TauriAdapter:
    def __init__(self):
        self._launcher = None
        self._app = None
        self._app_handle_obj = None

    @property
    def app_handle_obj(self):
        return self._app_handle_obj

    async def api_call(self, body):
        method = body.get("method")
        args = body.get("args") or []
        kwargs = body.get("kwargs") or {}

        launcher = self._launcher
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
            if inspect.isawaitable(result):
                result = await result
            return result
        except (TypeError, RuntimeError, OSError, ValueError, KeyError, AttributeError) as e:
            return {"success": False, "message": f"调用失败: {e}"}

    def run_app(self, launcher):
        self._launcher = launcher
        src_tauri_dir = Path(__file__).parent.parent.parent.absolute()
        with start_blocking_portal("asyncio") as portal:
            context = context_factory(src_tauri_dir)
            app = builder_factory().build(
                context=context,
                invoke_handler=commands.generate_handler(portal),
                plugins=[dialog.init()],
            )
            self._app = app
            self._app_handle_obj = app.handle()

            if launcher.state.plugin_framework is None:
                launcher.state._init_plugin_framework()
            fw = launcher.state.plugin_framework
            if fw is not None:
                fw._event_registry.emit("launcher:init_complete", {})

            exit_code = app.run_return()
            logger.info("应用已退出，开始清理资源...")

            _sys.stdout.flush()
            _sys.stderr.flush()
            if launcher is not None:
                launcher.state.shutdown()
            logger.info("资源清理完成")
            return exit_code


# 单例
_adapter_instance = TauriAdapter()


def get_app_handle_obj():
    return _adapter_instance.app_handle_obj


commands = Commands()


@commands.command()
async def api_call(body: dict[str, Any]) -> Any:
    return await _adapter_instance.api_call(body)


def run_app(launcher: Any) -> int:
    return _adapter_instance.run_app(launcher)
