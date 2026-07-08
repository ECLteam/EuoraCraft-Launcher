import inspect
import sys as _sys
from pathlib import Path
from typing import Any

from anyio.from_thread import start_blocking_portal
from pytauri import Commands
from pytauri_wheel.lib import builder_factory, context_factory

from ..api.handlers import Api
from ..common.env import get_app_dir, is_frozen
from ..common.logger import get_logger

logger = get_logger("adapter")


class TauriAdapter:
    def __init__(self):
        self._launcher = None
        self._app = None
        self._app_handle_obj = None

    # launcher
    def set_launcher(self, launcher):
        self._launcher = launcher

    def get_launcher(self):
        return self._launcher

    # app handle
    @property
    def app_handle_obj(self):
        return self._app_handle_obj

    def set_app_handle(self, app):
        self._app = app
        self._app_handle_obj = app.handle()

    # api
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

    def resolve_dev_server(self):
        # 解析前端开发服务器地址
        env = self._launcher.state.config_manager._env_loader
        dev_server = env.get("FRONTEND_DEV_SERVER")
        if dev_server:
            logger.info(f"检测到前端开发服务器: {dev_server!s}")
            return dev_server
        logger.info("使用本地前端文件")
        return None

    def resolve_frontend_path(self):
        # 解析前端静态文件路径
        # 打包环境：从 _MEIPASS 中读取 frontend 目录
        # 开发环境：可通过 FRONTEND_PATH 环境变量指定
        env = self._launcher.state.config_manager._env_loader
        frontend_path = env.get("FRONTEND_PATH")
        if frontend_path:
            logger.info(f"检测到前端静态文件路径: {frontend_path!s}")
            return frontend_path
        if is_frozen():
            app_dir = get_app_dir()
            default_frontend = app_dir / "frontend"
            if default_frontend.is_dir():
                logger.info(f"使用打包前端文件: {default_frontend!s}")
                return str(default_frontend)
        return None

    def post_init_events(self):
        # 初始化插件框架
        if self._launcher.state.plugin_framework is None:
            self._launcher.state._init_plugin_framework()

        # 插件事件：启动器初始化完成
        fw = self._launcher.state.plugin_framework
        if fw is not None:
            fw._event_registry.emit("launcher:init_complete", {})

    def run_app(self, launcher):
        self.set_launcher(launcher)

        src_tauri_dir = Path(__file__).parent.parent.parent.absolute()
        dev_server = self.resolve_dev_server()
        frontend_path = self.resolve_frontend_path()

        tauri_config = (
            {
                "build": {
                    "frontendDist": dev_server,
                },
            }
            if dev_server is not None
            else ({"build": {"frontendDist": frontend_path}} if frontend_path is not None else None)
        )

        with start_blocking_portal("asyncio") as portal:
            app = builder_factory().build(
                context=context_factory(src_tauri_dir, tauri_config=tauri_config),
                invoke_handler=commands.generate_handler(portal),
            )
            self.set_app_handle(app)

            # app 就绪后推送初始化事件
            self.post_init_events()

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


# PyTauri 命令注册
commands = Commands()


@commands.command()
async def api_call(body: dict[str, Any]) -> Any:
    return await _adapter_instance.api_call(body)


def run_app(launcher: Any) -> int:
    return _adapter_instance.run_app(launcher)
