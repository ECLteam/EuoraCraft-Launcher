from __future__ import annotations

from typing import Any

from anyio import to_thread

from ECL.api.contracts import ApiResponse, failure, success

from .bridge import _FrontendState, _ipc_handler, _open_folder


class ModHandlers(_FrontendState):
    """
    提供本地模组文件管理 IPC；在线目录尚未纳入当前 Game API。
    """

    @_ipc_handler("MOD_LIST_FAILED")
    async def get_mods(self, body: dict[str, Any]) -> ApiResponse:
        """
        列出指定 Minecraft 根目录中的本地模组。

        :param body: 包含 ``game_path`` 的请求数据
        :return: 本地模组列表
        """
        return success(await to_thread.run_sync(self.game.list_mods, body.get("game_path")))

    @_ipc_handler("MOD_TOGGLE_FAILED")
    async def toggle_mod(self, body: dict[str, Any]) -> ApiResponse:
        """
        切换指定本地模组的启用状态。

        :param body: 包含 ``game_path`` 和 ``filename`` 的请求数据
        :return: 切换后的启用状态
        """
        enabled = await to_thread.run_sync(self.game.toggle_mod, body.get("game_path"), body.get("filename"))
        return success({"enabled": enabled})

    @_ipc_handler("MOD_ADD_FAILED")
    async def add_mod(self, body: dict[str, Any]) -> ApiResponse:
        """
        将用户选择的 Jar 文件复制到目标 ``mods`` 目录。

        :param body: 包含 ``game_path`` 和 ``source_path`` 的请求数据
        :return: 安装后的模组文件名
        """
        filename = await to_thread.run_sync(self.game.add_mod, body.get("game_path"), body.get("source_path"))
        return success({"filename": filename})

    @_ipc_handler("MOD_REMOVE_FAILED")
    async def remove_mod(self, body: dict[str, Any]) -> ApiResponse:
        """
        删除目标 ``mods`` 目录中的一个文件。

        :param body: 包含 ``game_path`` 和 ``filename`` 的请求数据
        :return: 空的成功响应
        """
        await to_thread.run_sync(self.game.remove_mod, body.get("game_path"), body.get("filename"))
        return success()

    @_ipc_handler("MOD_FOLDER_FAILED")
    async def open_mods_folder(self, body: dict[str, Any]) -> ApiResponse:
        """
        创建并使用系统文件管理器打开目标 ``mods`` 目录。

        :param body: 包含 ``game_path`` 的请求数据
        :return: 模组目录路径
        """
        path = await to_thread.run_sync(self.game.mods_path, body.get("game_path"))
        await to_thread.run_sync(_open_folder, str(path))
        return success({"path": str(path)})

    async def search_mods(self, body: dict[str, Any]) -> ApiResponse:
        """
        明确拒绝尚未接入的在线模组搜索，避免前端收到未知命令错误。

        :param body: 在线搜索条件
        :return: 稳定的功能不可用响应
        """
        return failure("在线模组目录尚未接入当前后端", "ONLINE_MOD_CATALOG_UNAVAILABLE")

    async def get_mod_info(self, body: dict[str, Any]) -> ApiResponse:
        """
        明确拒绝尚未接入的在线模组详情查询。

        :param body: 在线模组标识和来源
        :return: 稳定的功能不可用响应
        """
        return failure("在线模组目录尚未接入当前后端", "ONLINE_MOD_CATALOG_UNAVAILABLE")

    async def get_mod_versions(self, body: dict[str, Any]) -> ApiResponse:
        """
        明确拒绝尚未接入的在线模组版本查询。

        :param body: 在线模组标识、来源和筛选条件
        :return: 稳定的功能不可用响应
        """
        return failure("在线模组目录尚未接入当前后端", "ONLINE_MOD_CATALOG_UNAVAILABLE")

    async def download_mod(self, body: dict[str, Any]) -> ApiResponse:
        """
        明确拒绝尚未接入的在线模组下载。

        :param body: 在线模组版本和安装目标
        :return: 稳定的功能不可用响应
        """
        return failure("在线模组下载尚未接入当前后端", "ONLINE_MOD_CATALOG_UNAVAILABLE")


__all__ = ["ModHandlers"]
