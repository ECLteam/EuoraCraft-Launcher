# ============================================================
# EuoraCraft Launcher
# ECLTeam © 2026 GPL-3.0 License
# https://github.com/ECLTeam/EuoraCraft-Launcher
#
# 文件作用：验证背景视频 IPC 从独立视频配置分支读取路径。
# ============================================================

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ECL.api.files import FileHandlers


@pytest.mark.anyio
async def test_background_video_open_prefers_nested_video_path() -> None:
    """
    使用新配置结构签发背景视频地址。

    ``ui.background.video.path`` 是新版唯一的持久化视频路径；旧版扁平 ``path``
    即使仍存在，也不能覆盖它。
    """

    opened_paths: list[str] = []
    handler = object.__new__(FileHandlers)
    handler.config = SimpleNamespace(
        get_config=lambda section: {
            "background": {
                "media_type": "video",
                "path": "C:/legacy-background.mp4",
                "video": {"path": "C:/saved-background.mp4"},
            }
        }
    )
    handler.background_media = SimpleNamespace(
        open=lambda path: opened_paths.append(path) or "http://127.0.0.1:9527/background/token"
    )

    result = await handler.background_video_open({})

    assert result == {"success": True, "data": {"url": "http://127.0.0.1:9527/background/token"}}
    assert opened_paths == ["C:/saved-background.mp4"]
