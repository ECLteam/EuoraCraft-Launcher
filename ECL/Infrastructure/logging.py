import gzip
import logging
import logging.handlers
from contextlib import suppress
from datetime import datetime
from pathlib import Path


class ColoredFormatter(logging.Formatter):
    """控制台彩色日志格式化器"""

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
        """
        格式化日志记录，添加 ANSI 颜色
        :param record: 日志记录对象
        :return: 带颜色的格式化日志字符串
        """
        record = logging.makeLogRecord(record.__dict__.copy())
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{self.COLORS['BOLD']}{levelname:8s}{self.COLORS['RESET']}"
            record.msg = f"{self.COLORS[levelname]}{record.msg}{self.COLORS['RESET']}"
        return super().format(record)


class CompressedTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """按时间轮转并 gzip 压缩的日志文件处理器"""

    def __init__(
            self,
            filename: str,
            when: str = "midnight",
            interval: int = 1,
            backup_count: int = 30,
            encoding: str = "utf-8",
            delay: bool = False,
            utc: bool = False,
    ):
        self.backup_count = backup_count
        super().__init__(filename, when, interval, backup_count, encoding, delay, utc)

    def dorollover(self) -> None:
        """执行日志轮转，将旧日志压缩为 .gz 文件"""
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
            try:
                compressed_path = dfn + ".gz"
                with Path(dfn).open("rb") as f_in, gzip.open(compressed_path, "wb") as f_out:
                    f_out.writelines(f_in)
                Path(dfn).unlink()
            except (OSError, EOFError) as e:
                logging.warning(f"压缩日志文件失败 {dfn}: {e}")
        if not self.delay:
            self.stream = self._open()
        self.rolloverAt = self.computeRollover(int(datetime.now().timestamp()))
        try:
            log_dir = Path(self.baseFilename).parent
            base_name = Path(self.baseFilename).name
            log_files = [f for f in log_dir.iterdir() if f.name.startswith(base_name) and f.name != base_name]
            log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            for old_file in log_files[self.backup_count :]:
                with suppress(OSError, PermissionError):
                    old_file.unlink()
        except (OSError, PermissionError):
            pass


class LoggerManager:
    """全局日志管理器，支持彩色控制台输出和文件轮转"""

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, colored: bool = True, data_path: Path | None = None):
        if LoggerManager._initialized:
            return
        if data_path is None:
            from ECL.Common import get_runtime_info

            data_path = Path(get_runtime_info()["app_path"]) / "ECL_data"
        self.data_path = Path(data_path)
        self.log_dir = self.data_path / "logs"
        self._root_logger = logging.getLogger("EuoraCraft-Launcher")
        self._root_logger.setLevel(logging.DEBUG)
        self._setup_handlers(colored)
        LoggerManager._initialized = True

    def _setup_handlers(self, colored: bool) -> None:
        """
        初始化日志处理器
        :param colored: 是否启用彩色控制台输出
        """
        if self._root_logger.handlers:
            return
        self.log_dir.mkdir(parents=True, exist_ok=True)
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
            self.log_dir / "EuoraCraft-Launcher.log",
            when="midnight",
            interval=1,
            backup_count=30,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(base_formatter)
        error_handler = CompressedTimedRotatingFileHandler(
            self.log_dir / "error.log",
            when="midnight",
            interval=1,
            backup_count=30,
            encoding="utf-8",
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(base_formatter)
        self._root_logger.addHandler(console_handler)
        self._root_logger.addHandler(file_handler)
        self._root_logger.addHandler(error_handler)

    def get_logger(self, name: str | None = None) -> logging.Logger:
        """
        获取命名日志记录器
        :param name: 日志记录器名称，为 None 时返回根日志记录器
        :return: 日志记录器实例
        """
        return self._root_logger.getChild(name) if name else self._root_logger

    def set_level(self, level: int) -> None:
        """
        设置全局日志级别
        :param level: 日志级别常量
        """
        self._root_logger.setLevel(level)
        self._console_handler.setLevel(level)

    def shutdown(self) -> None:
        """关闭所有日志处理器"""
        for handler in self._root_logger.handlers[:]:
            with suppress(OSError, RuntimeError):
                handler.flush()
            with suppress(OSError, RuntimeError):
                handler.close()
            self._root_logger.removeHandler(handler)


def get_logger(name: str | None = None) -> logging.Logger:
    """
    获取日志记录器的便捷函数
    :param name: 日志记录器名称
    :return: 日志记录器实例
    """
    return LoggerManager().get_logger(name)
