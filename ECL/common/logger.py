from __future__ import annotations

import contextlib
import gzip
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path


class ColoredFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
        "RESET": "\033[0m",
        "BOLD": "\033[1m",
    }

    def format(self, record: logging.LogRecord) -> str:
        record = logging.makeLogRecord(record.__dict__.copy())
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{self.COLORS['BOLD']}{levelname:8s}{self.COLORS['RESET']}"
            record.msg = f"{self.COLORS[levelname]}{record.msg}{self.COLORS['RESET']}"
        return super().format(record)


class CompressedTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    def __init__(self, filename, when="midnight", interval=1, backupCount=30, encoding="utf-8", delay=False, utc=False):
        self.backup_count = backupCount
        super().__init__(filename, when, interval, backupCount, encoding, delay, utc)

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        current_time = int(self.rolloverAt - self.interval)
        dfn = self.rotation_filename(
            self.baseFilename + "." + datetime.fromtimestamp(current_time).strftime("%Y-%m-%d")
        )
        if Path(self.baseFilename).exists():
            if Path(dfn).exists():
                Path(dfn).unlink()
            Path(self.baseFilename).rename(dfn)
            self._compress_file(dfn)
        if not self.delay:
            self.stream = self._open()
        self.rolloverAt = self.computeRollover(int(datetime.now().timestamp()))
        self._cleanup_old_logs()

    def _compress_file(self, filepath: str) -> None:
        try:
            compressed_path = filepath + ".gz"
            with Path(filepath).open("rb") as f_in, gzip.open(compressed_path, "wb") as f_out:
                f_out.writelines(f_in)
            Path(filepath).unlink()
        except (OSError, EOFError) as e:
            logging.warning(f"压缩日志文件失败 {filepath}: {e}")

    def _cleanup_old_logs(self) -> None:
        try:
            log_dir = Path(self.baseFilename).parent
            base_name = Path(self.baseFilename).name
            log_files = [f for f in log_dir.iterdir() if f.name.startswith(base_name) and f.name != base_name]
            log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            for old_file in log_files[self.backup_count :]:
                with contextlib.suppress(OSError, PermissionError):
                    old_file.unlink()
        except (OSError, PermissionError):
            pass


class LoggerManager:
    _instance: LoggerManager | None = None
    _initialized: bool = False

    def __new__(cls) -> LoggerManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, colored: bool = True):
        if LoggerManager._initialized:
            return
        self._root_logger = logging.getLogger("EuoraCraft-Launcher")
        self._root_logger.setLevel(logging.DEBUG)
        self._setup_handlers(colored)
        LoggerManager._initialized = True

    def _setup_handlers(self, colored: bool) -> None:
        if self._root_logger.handlers:
            return
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        base_formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] [%(filename)s:%(lineno)d] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        if colored:
            console_formatter = ColoredFormatter(
                fmt="%(asctime)s %(levelname)s [%(name)s] [%(filename)s:%(lineno)d] - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        else:
            console_formatter = base_formatter
        console_handler.setFormatter(console_formatter)
        self._console_handler = console_handler
        file_handler = CompressedTimedRotatingFileHandler(
            log_dir / "EuoraCraft-Launcher.log", when="midnight", interval=1, backupCount=30, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(base_formatter)
        error_handler = CompressedTimedRotatingFileHandler(
            log_dir / "error.log", when="midnight", interval=1, backupCount=30, encoding="utf-8"
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(base_formatter)
        self._root_logger.addHandler(console_handler)
        self._root_logger.addHandler(file_handler)
        self._root_logger.addHandler(error_handler)

    def get_logger(self, name: str | None = None) -> logging.Logger:
        return self._root_logger.getChild(name) if name else self._root_logger

    def set_level(self, level: int) -> None:
        self._root_logger.setLevel(level)
        self._console_handler.setLevel(level)

    def shutdown(self) -> None:
        for handler in self._root_logger.handlers[:]:
            with contextlib.suppress(OSError, RuntimeError):
                handler.flush()
            with contextlib.suppress(OSError, RuntimeError):
                handler.close()
            self._root_logger.removeHandler(handler)


def get_logger(name: str | None = None) -> logging.Logger:
    return LoggerManager().get_logger(name)
