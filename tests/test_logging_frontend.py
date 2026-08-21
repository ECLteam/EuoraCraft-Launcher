import ECL.utils.logging as logging_mod
from ECL.utils import LoggingRuntime
from ECL.utils.logging import FrontendLogHandler, get_frontend_log_history


class RecordingEvents:
    """记录 emit 调用的事件总线替身。"""

    def __init__(self) -> None:
        self.emitted: list[tuple[str, object]] = []

    def emit(self, event: str, payload: object) -> None:
        self.emitted.append((event, payload))


def test_frontend_log_handler_forwards_and_keeps_history(tmp_path) -> None:
    data_path = tmp_path / "ECL_data"
    manager = LoggingRuntime(colored=False, data_path=data_path)
    events = RecordingEvents()

    manager.install_frontend_handler(events, history_limit=10)
    # 幂等：重复安装不会产生第二个处理器
    manager.install_frontend_handler(events)
    handler_count = sum(isinstance(handler, FrontendLogHandler) for handler in manager.get_logger().handlers)
    assert handler_count == 1

    logger = manager.get_logger("Terminal")
    logger.info("hello-terminal")
    for handler in manager.get_logger().handlers:
        handler.flush()

    log_payloads = [p for event, p in events.emitted if event == "launcher:log"]
    assert log_payloads
    entry = log_payloads[-1]
    assert isinstance(entry, dict)
    assert entry["message"] == "hello-terminal"
    assert entry["level"] == "INFO"
    assert entry["logger"] == "EuoraCraft-Launcher.Terminal"

    history = get_frontend_log_history()
    assert history, "历史缓冲应保留已转发的日志"
    assert history[-1]["message"] == "hello-terminal"
    manager.shutdown()
    logging_mod._FRONTEND_BUFFER = None
