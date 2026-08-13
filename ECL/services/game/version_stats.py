from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import TypedDict

from ECL.utils import atomic_write_text, get_logger


class VersionRunStats(TypedDict):
    launchCount: int
    lastRunDurationSeconds: int
    totalRunDurationSeconds: int


def _default_stats() -> VersionRunStats:
    return {
        "launchCount": 0,
        "lastRunDurationSeconds": 0,
        "totalRunDurationSeconds": 0,
    }


class VersionStatsStore:
    """
    管理每个 Minecraft 版本目录中的运行统计文件。

    存储层以进程内锁串行化同一启动器产生的并发更新，并通过同目录临时文件原子
    替换目标文件。统计失败只影响统计本身，不应阻止版本扫描或游戏启动。
    """

    FILE_NAME = "eclversion.json"

    def __init__(self) -> None:
        self._lock = RLock()
        self._logger = get_logger("VersionStatsStore")

    @staticmethod
    def _stats_path(game_path: Path, version_id: str) -> Path:
        return game_path / "versions" / version_id / VersionStatsStore.FILE_NAME

    @staticmethod
    def _normalize(data: object) -> VersionRunStats:
        source = data if isinstance(data, dict) else {}

        def non_negative_int(key: str) -> int:
            value = source.get(key, 0)
            if isinstance(value, bool):
                return 0
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                return 0

        return {
            "launchCount": non_negative_int("launchCount"),
            "lastRunDurationSeconds": non_negative_int("lastRunDurationSeconds"),
            "totalRunDurationSeconds": non_negative_int("totalRunDurationSeconds"),
        }

    def _read_unlocked(self, stats_path: Path) -> VersionRunStats:
        if not stats_path.is_file():
            return _default_stats()
        try:
            return self._normalize(json.loads(stats_path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            self._logger.warning("读取版本运行统计失败 %s: %s", stats_path, exc)
            return _default_stats()

    def _write_unlocked(self, stats_path: Path, stats: VersionRunStats) -> bool:
        try:
            stats_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(stats_path, json.dumps(stats, ensure_ascii=False, indent=2))
            return True
        except OSError as exc:
            self._logger.warning("写入版本运行统计失败 %s: %s", stats_path, exc)
            return False

    def ensure(self, game_path: Path, version_id: str) -> VersionRunStats:
        """
        确保已识别版本拥有默认统计文件，并返回规范化数据。

        :param game_path: Minecraft 游戏根目录
        :param version_id: 已通过游戏服务校验的版本目录名称
        :return: 统计文件当前数据；读取失败时返回零值
        """
        stats_path = self._stats_path(game_path, version_id)
        with self._lock:
            stats = self._read_unlocked(stats_path)
            if not stats_path.is_file():
                self._write_unlocked(stats_path, stats)
            return stats

    def read(self, game_path: Path, version_id: str) -> VersionRunStats:
        """
        读取版本运行统计，文件不存在时同时创建默认文件。

        :param game_path: Minecraft 游戏根目录
        :param version_id: 已通过游戏服务校验的版本目录名称
        :return: 可直接通过 IPC 返回的统计副本
        """
        return dict(self.ensure(game_path, version_id))

    def record_launch(self, game_path: Path, version_id: str) -> None:
        """
        在游戏进程成功创建后累计一次启动。

        :param game_path: Minecraft 游戏根目录
        :param version_id: 已通过游戏服务校验的版本目录名称
        """
        stats_path = self._stats_path(game_path, version_id)
        with self._lock:
            stats = self._read_unlocked(stats_path)
            stats["launchCount"] += 1
            self._write_unlocked(stats_path, stats)

    def record_duration(self, game_path: Path, version_id: str, duration_seconds: int) -> None:
        """
        在一次受管理运行结束或启动器关闭时累计观察到的时长。

        :param game_path: Minecraft 游戏根目录
        :param version_id: 已通过游戏服务校验的版本目录名称
        :param duration_seconds: 非负整数秒；不足一秒按零秒记录
        """
        stats_path = self._stats_path(game_path, version_id)
        duration = max(0, int(duration_seconds))
        with self._lock:
            stats = self._read_unlocked(stats_path)
            stats["lastRunDurationSeconds"] = duration
            stats["totalRunDurationSeconds"] += duration
            self._write_unlocked(stats_path, stats)


__all__ = ["VersionRunStats", "VersionStatsStore"]
