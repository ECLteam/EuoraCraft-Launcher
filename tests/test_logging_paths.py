import logging
from pathlib import Path

from ECL.Infrastructure import LoggerManager


def _reset_logger_manager() -> None:
    if LoggerManager._instance is not None:
        LoggerManager._instance.shutdown()
    LoggerManager._instance = None
    LoggerManager._initialized = False


def test_logger_files_are_created_under_data_path(tmp_path) -> None:
    _reset_logger_manager()
    data_path = tmp_path / "ECL_data"

    manager = LoggerManager(colored=False, data_path=data_path)

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
    _reset_logger_manager()
