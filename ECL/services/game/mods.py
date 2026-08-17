from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .base import GameServiceError, _GameState
from .resources import ResourceCoordinator


class ModCoordinator(_GameState):
    """
    管理 Minecraft 根目录中的本地模组文件。

    所有写操作都限制在目标 ``mods`` 目录内，并使用临时文件完成复制。
    """

    def list_mods(self, game_path: Any) -> list[dict[str, Any]]:
        """
        列出目标 Minecraft 根目录中的 Jar 模组，并解析 jar 元数据。

        :param game_path: Minecraft 游戏根目录
        :return: 前端本地模组列表所需的完整信息
        """
        mods_dir = self._normalize_game_path(game_path) / "mods"
        if not mods_dir.is_dir():
            return []
        result = []
        for path in sorted(mods_dir.iterdir(), key=lambda item: item.name.casefold()):
            if not path.is_file() or not (path.name.endswith(".jar") or path.name.endswith(".jar.disabled")):
                continue
            enabled = path.name.endswith(".jar")
            metadata = ResourceCoordinator._parse_mod(path)
            result.append(
                {
                    "filename": path.name,
                    "name": metadata.get("name") or path.stem.removesuffix(".disabled"),
                    "version": metadata.get("version") or "",
                    "author": metadata.get("author") or "",
                    "loader_type": metadata.get("loader") or "",
                    "game_version": metadata.get("gameVersion") or "",
                    "project_id": metadata.get("projectId") or "",
                    "dependencies": metadata.get("dependencies") or [],
                    "enabled": enabled,
                    "size": path.stat().st_size,
                    "modified_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
                }
            )
        return result

    def toggle_mod(self, game_path: Any, filename: Any) -> bool:
        """
        通过 ``.disabled`` 后缀切换模组启用状态。

        :param game_path: Minecraft 游戏根目录
        :param filename: ``mods`` 目录内的文件名
        :return: 切换后的启用状态
        """
        source = self._mod_path(game_path, filename)
        if not source.is_file():
            raise GameServiceError("模组文件不存在", "MOD_NOT_FOUND")
        enabled = not source.name.endswith(".disabled")
        target_name = source.name.removesuffix(".disabled") if not enabled else f"{source.name}.disabled"
        target = self._mod_path(game_path, target_name)
        if target.exists():
            raise GameServiceError("目标模组文件已存在", "MOD_TARGET_EXISTS")
        source.replace(target)
        return not enabled

    def add_mod(self, game_path: Any, source_path: Any) -> str:
        """
        将本地 Jar 文件原子复制到目标 ``mods`` 目录。

        :param game_path: Minecraft 游戏根目录
        :param source_path: 用户选择的源 Jar 文件
        :return: 安装后的文件名
        """
        if not isinstance(source_path, (str, Path)) or not str(source_path).strip():
            raise GameServiceError("未选择模组文件", "INVALID_MOD_SOURCE")
        source = Path(source_path).expanduser().resolve(strict=False)
        if not source.is_file() or source.suffix.casefold() != ".jar":
            raise GameServiceError("模组源文件必须是 Jar 文件", "INVALID_MOD_SOURCE")
        target = self._mod_path(game_path, source.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            shutil.copy2(source, temporary)
            temporary.replace(target)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise GameServiceError(f"复制模组失败: {exc}", "MOD_COPY_FAILED") from exc
        return target.name

    def remove_mod(self, game_path: Any, filename: Any) -> None:
        """
        删除目标 ``mods`` 目录中的单个模组文件。

        :param game_path: Minecraft 游戏根目录
        :param filename: ``mods`` 目录内的文件名
        """
        target = self._mod_path(game_path, filename)
        if not target.is_file():
            raise GameServiceError("模组文件不存在", "MOD_NOT_FOUND")
        target.unlink()

    def mods_path(self, game_path: Any) -> Path:
        """
        创建并返回目标 Minecraft 根目录中的 ``mods`` 目录。

        :param game_path: Minecraft 游戏根目录
        :return: 绝对 ``mods`` 目录路径
        """
        path = (self._normalize_game_path(game_path) / "mods").resolve(strict=False)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _mod_path(self, game_path: Any, filename: Any) -> Path:
        if not isinstance(filename, str) or not filename.strip() or "\0" in filename:
            raise GameServiceError("模组文件名无效", "INVALID_MOD_FILENAME")
        mods_dir = (self._normalize_game_path(game_path) / "mods").resolve(strict=False)
        target = (mods_dir / filename).resolve(strict=False)
        if target.parent != mods_dir or target.name != filename:
            raise GameServiceError("模组路径超出允许范围", "INVALID_MOD_PATH")
        return target


__all__ = ["ModCoordinator"]
