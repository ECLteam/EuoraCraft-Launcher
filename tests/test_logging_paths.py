import logging
from pathlib import Path

from ECL.utils import LoggingRuntime


def test_logger_files_are_created_under_data_path(tmp_path) -> None:
    data_path = tmp_path / "ECL_data"

    manager = LoggingRuntime(colored=False, data_path=data_path)

    assert manager.log_dir == data_path / "logs"
    file_paths = {
        Path(handler.baseFilename)
        for handler in manager.get_logger().handlers
        if isinstance(handler, logging.FileHandler)
    }
    assert file_paths == {
        (data_path / "logs" / "EuoraCraft-Launcher.log").resolve(),
        (data_path / "logs" / "error.log").resolve(),
    }
    manager.shutdown()


def test_debug_records_remain_in_complete_log_when_console_is_info(tmp_path) -> None:
    data_path = tmp_path / "ECL_data"
    manager = LoggingRuntime(colored=False, data_path=data_path)
    manager.set_level(logging.INFO)

    manager.get_logger("Diagnostics").debug("debug-diagnostic-record")
    for handler in manager.get_logger().handlers:
        handler.flush()

    complete_log = (data_path / "logs" / "EuoraCraft-Launcher.log").read_text(encoding="utf-8")
    assert "debug-diagnostic-record" in complete_log
    manager.shutdown()
