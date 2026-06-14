import webview

from ..api.handlers import Api
from ..common.logger import get_logger
from ..common.state import AppState

logger = get_logger("ui")


def on_closed(state: AppState):
    logger.info("窗口已关闭，开始清理资源...")
    state.shutdown()
    logger.info("资源清理完成")


def on_loaded():
    logger.info("窗口已加载完成")
    if webview.windows:
        webview.windows[0].show()


def run_ui(state: AppState, debug: bool = False) -> None:
    if not state.initialized:
        logger.error("应用状态未初始化，无法启动 UI")
        return

    config = state.config_manager.config
    ui_config = config[0].get("ui", {}) if config else {}
    width = ui_config.get("width", 1000)
    height = ui_config.get("height", 700)
    title = ui_config.get("title", "EuoraCraft Launcher")

    api = Api(state)

    html_path = "http://localhost:5173"

    window = webview.create_window(
        title,
        url=html_path,
        js_api=api,
        width=width,
        height=height,
        frameless=True,
        easy_drag=False,
        hidden=True,
        shadow=True,
        text_select=False,
    )

    window.events.minimized += lambda: logger.info("窗口已最小化")
    window.events.restored += lambda: logger.info("窗口已还原")
    window.events.loaded += on_loaded
    window.events.closed += lambda: on_closed(state)

    webview.start(debug=debug)
    logger.info("程序已退出")
