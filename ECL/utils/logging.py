from __future__ import annotations

import gzip
import logging
import logging.handlers
import shutil
from contextlib import suppress
from pathlib import Path

LOGGER_NAME = "EuoraCraft-Launcher"


class ColoredFormatter(logging.Formatter):
    """
    为交互式终端中的日志级别和消息添加 ANSI 颜色。

    文件日志始终使用无颜色格式，保证归档文件可被普通文本工具读取。
    """

    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """
        格式化日志副本，避免修改随后写入文件的原始记录。

        :param record: 标准库创建的日志记录
        :return: 带终端颜色的日志文本
        """
        copy = logging.makeLogRecord(record.__dict__.copy())
        color = self.COLORS.get(copy.levelname)
        if color:
            copy.levelname = f"{color}\033[1m{copy.levelname:8s}{self.RESET}"
            copy.msg = f"{color}{copy.msg}{self.RESET}"
        return super().format(copy)


def _gzip_rotator(source: str, destination: str) -> None:
    with Path(source).open("rb") as source_file, gzip.open(destination, "wb") as destination_file:
        shutil.copyfileobj(source_file, destination_file)
    Path(source).unlink()


class LoggingRuntime:
    """
    管理一次应用运行所使用的控制台与滚动文件处理器。

    完整日志文件始终接收 ``DEBUG`` 及以上记录；启动器的 Debug 开关只控制控制台
    是否展示诊断信息，避免关闭开关后丢失复现问题所需的文件日志。

    :param data_path: 启动器数据目录，日志写入其 ``logs`` 子目录
    :param colored: 控制台是否使用 ANSI 颜色
    """

    def __init__(self, data_path: Path, colored: bool = True) -> None:
        """
        创建日志目录并安装本次运行独占的处理器。

        :param data_path: 启动器数据目录
        :param colored: 控制台是否使用 ANSI 颜色
        """
        self.data_path = Path(data_path)
        self.log_dir = self.data_path / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.root_logger = logging.getLogger(LOGGER_NAME)
        self.root_logger.setLevel(logging.DEBUG)
        self.root_logger.propagate = False
        self._replace_handlers(colored)

    def _replace_handlers(self, colored: bool) -> None:
        """
        关闭旧处理器并安装控制台、完整日志和错误日志处理器。

        :param colored: 控制台是否使用 ANSI 颜色
        """
        for handler in tuple(self.root_logger.handlers):
            handler.close()
            self.root_logger.removeHandler(handler)
        plain = logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(name)s] [%(filename)s:%(lineno)d] - %(message)s",
            "%Y-%m-%d %H:%M:%S",
        )
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(
            ColoredFormatter(
                "%(asctime)s %(levelname)s [%(name)s] [%(filename)s:%(lineno)d] - %(message)s",
                "%Y-%m-%d %H:%M:%S",
            )
            if colored
            else plain
        )
        self._console_handler = console
        self.root_logger.addHandler(console)
        self.root_logger.addHandler(self._file_handler("EuoraCraft-Launcher.log", logging.DEBUG, plain))
        self.root_logger.addHandler(self._file_handler("error.log", logging.ERROR, plain))

    def _file_handler(
        self,
        filename: str,
        level: int,
        formatter: logging.Formatter,
    ) -> logging.handlers.TimedRotatingFileHandler:
        handler = logging.handlers.TimedRotatingFileHandler(
            self.log_dir / filename,
            when="midnight",
            backupCount=30,
            encoding="utf-8",
        )
        handler.namer = lambda name: f"{name}.gz"
        handler.rotator = _gzip_rotator
        handler.setLevel(level)
        handler.setFormatter(formatter)
        return handler

    def get_logger(self, name: str | None = None) -> logging.Logger:
        """
        返回启动器根日志器或其命名子日志器。

        :param name: 可选的组件名称
        :return: 继承统一处理器配置的日志器
        """
        return self.root_logger.getChild(name) if name else self.root_logger

    def set_level(self, level: int) -> None:
        """
        调整控制台详细程度，同时保留文件中的 Debug 诊断记录。

        :param level: 控制台最低日志级别
        """
        self.root_logger.setLevel(logging.DEBUG)
        self._console_handler.setLevel(level)

    def shutdown(self) -> None:
        """
        刷新并关闭本次运行创建的全部日志处理器。
        """
        for handler in tuple(self.root_logger.handlers):
            with suppress(OSError, RuntimeError):
                handler.flush()
                handler.close()
            self.root_logger.removeHandler(handler)


def configure_logging(data_path: Path, colored: bool = True) -> LoggingRuntime:
    """
    为一次启动器运行配置统一日志输出。

    :param data_path: 启动器数据目录
    :param colored: 控制台是否使用 ANSI 颜色
    :return: 负责日志处理器生命周期的运行对象
    """
    return LoggingRuntime(data_path, colored)


def get_logger(name: str | None = None) -> logging.Logger:
    """
    获取由组合入口配置的启动器日志器。

    :param name: 可选的组件名称
    :return: 启动器根日志器或其命名子日志器
    """
    logger = logging.getLogger(LOGGER_NAME)
    return logger.getChild(name) if name else logger


LoggerManager = LoggingRuntime

__all__ = ["LoggerManager", "LoggingRuntime", "configure_logging", "get_logger"]
