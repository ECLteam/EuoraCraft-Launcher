from __future__ import annotations

from typing import Any

from anyio import to_thread
from pydantic import ValidationError

from ECL.api.contracts import ApiResponse, failure, success
from ECL.api.models import (
    GameCatalogRequest,
    GameConfigPatch,
    GameConfigUpdate,
    GameInstanceRequest,
    GamePathRequest,
    GameScanRequest,
    GameUninstallRequest,
    GameVersionRequest,
    InstallRequest,
    LaunchRequest,
    LoaderCatalogRequest,
)

from .bridge import _FrontendState, _ipc_handler


class GameHandlers(_FrontendState):
    """
    提供游戏目录、安装任务和运行实例的正式 IPC 边界。
    """

    def _download_source(self, requested_source: str | None) -> str:
        """
        选择请求显式指定的下载源，缺失时使用启动器配置。

        :param requested_source: 请求模型中的可选下载源
        :return: Game Service 可识别的下载源名称
        """
        if requested_source:
            return requested_source
        return str((self._get_effective_config().get("download") or {}).get("mirror_source") or "official")

    @_ipc_handler("VERSION_CATALOG_FAILED")
    async def game_versions(self, body: dict[str, Any]) -> ApiResponse:
        """
        查询 Minecraft 版本列表或分类目录。

        :param body: 符合 ``GameCatalogRequest`` 的请求数据
        :return: 版本列表或按版本类型分类的目录
        """
        try:
            request = GameCatalogRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        source = self._download_source(request.source.value if request.source else None)
        if request.classified:
            catalog = await to_thread.run_sync(self.game.minecraft_versions_classified, source)
            return success(catalog)
        versions = await to_thread.run_sync(self.game.minecraft_versions, request.filter_type, source)
        return success(versions)

    @_ipc_handler("LOADER_VERSIONS_FAILED")
    async def game_loader_versions(self, body: dict[str, Any]) -> ApiResponse:
        """
        查询指定 Minecraft 版本可用的模组加载器版本。

        :param body: 符合 ``LoaderCatalogRequest`` 的请求数据
        :return: 加载器版本列表
        """
        try:
            request = LoaderCatalogRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        source = self._download_source(request.source.value if request.source else None)
        versions = await to_thread.run_sync(
            self.game.loader_versions,
            request.loader.value,
            request.game_version,
            source,
        )
        return success(versions)

    @_ipc_handler("VERSION_SCAN_FAILED")
    async def game_scan(self, body: dict[str, Any]) -> ApiResponse:
        """
        扫描一个或多个 Minecraft 根目录中的本地实例。

        :param body: 符合 ``GameScanRequest`` 的请求数据
        :return: 扫描到的实例列表
        """
        try:
            request = GameScanRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        paths = request.paths
        if paths is None:
            configured_paths = (self._get_effective_config().get("game") or {}).get("minecraft_paths") or []
            paths = [item.get("path") if isinstance(item, dict) else item for item in configured_paths]
        versions = await to_thread.run_sync(
            lambda: self.game.scan_versions([str(path) for path in paths if path], force=request.force)
        )
        return success(versions)

    @_ipc_handler("VERSION_INSTALL_FAILED")
    async def game_install(self, body: dict[str, Any]) -> ApiResponse:
        """
        创建受 Game Service 管理的版本安装任务。

        :param body: 符合 ``InstallRequest`` 的请求数据
        :return: 安装任务标识与最终实例名称
        """
        try:
            request = InstallRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        payload = request.model_dump(mode="json", exclude={"game_path", "java_path", "source"}, exclude_none=True)
        if request.loader_type is not None and request.loader_version is not None:
            payload[f"{request.loader_type.value}_version"] = request.loader_version
        result = self.game.install_version(
            payload,
            game_path=request.game_path,
            java_path=str(request.java_path) if request.java_path else None,
            source=self._download_source(request.source.value if request.source else None),
        )
        return success(result)

    @_ipc_handler("VERSION_UNINSTALL_FAILED")
    async def game_uninstall(self, body: dict[str, Any]) -> ApiResponse:
        """
        从指定 Minecraft 根目录卸载一个实例。

        :param body: 符合 ``GameUninstallRequest`` 的请求数据
        :return: 空的成功响应
        """
        try:
            request = GameUninstallRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        await to_thread.run_sync(self.game.uninstall_version, request.version_id, request.game_path)
        return success()

    @_ipc_handler("GAME_CONFIG_FAILED")
    async def game_config_get(self, body: dict[str, Any]) -> ApiResponse:
        """
        读取 Minecraft 根目录中的 ``ecl.json``。

        :param body: 符合 ``GamePathRequest`` 的请求数据
        :return: 完整游戏目录配置
        """
        try:
            request = GamePathRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        return success(await to_thread.run_sync(self.game.read_ecl_config, request.game_path))

    @_ipc_handler("GAME_CONFIG_FAILED")
    async def game_config_set(self, body: dict[str, Any]) -> ApiResponse:
        """
        原子替换 Minecraft 根目录中的 ``ecl.json``。

        :param body: 符合 ``GameConfigUpdate`` 的请求数据
        :return: 空的成功响应
        """
        try:
            request = GameConfigUpdate.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        await to_thread.run_sync(self.game.write_ecl_config, request.game_path, request.data)
        return success()

    @_ipc_handler("GAME_CONFIG_FAILED")
    async def game_config_patch(self, body: dict[str, Any]) -> ApiResponse:
        """
        合并更新 Minecraft 根目录中的 ``ecl.json``。

        :param body: 符合 ``GameConfigPatch`` 的请求数据
        :return: 更新后的完整游戏目录配置
        """
        try:
            request = GameConfigPatch.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        return success(await to_thread.run_sync(self.game.patch_ecl_config, request.game_path, request.patch))

    async def game_instances(self, body: dict[str, Any]) -> ApiResponse:
        """
        返回由启动器管理的运行中 Minecraft 实例。

        :param body: 必须为空的请求对象
        :return: 运行中实例列表
        """
        if body:
            return failure("game_instances 不接受请求参数", "INVALID_REQUEST")
        return success(self.game.list_instances())

    @_ipc_handler("VERSION_STATS_FAILED")
    async def game_version_stats(self, body: dict[str, Any]) -> ApiResponse:
        """
        返回指定 Minecraft 版本的持久化运行统计。

        :param body: 符合 ``GameVersionRequest`` 的请求数据
        :return: 启动次数、上次运行秒数和总运行秒数
        """
        try:
            request = GameVersionRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        return success(await to_thread.run_sync(self.game.get_version_stats, request.game_path, request.version_id))

    @_ipc_handler("GAME_LAUNCH_FAILED")
    async def game_launch(self, body: dict[str, Any]) -> ApiResponse:
        """
        校验启动参数、补全文件并创建 Minecraft 进程。

        :param body: 符合 ``LaunchRequest`` 的请求数据
        :return: 新游戏实例的标识、版本和目录
        """
        try:
            request = LaunchRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        values = request.model_dump()
        version_id = values.pop("version_id")
        game_path = values.pop("game_path")
        source = values.pop("source")
        java_path = values.pop("java_path")
        result = await self.game.launch_instance(
            {"version_id": version_id},
            game_path=game_path,
            source=self._download_source(source.value if source else None),
            java_path=str(java_path) if java_path else None,
            **values,
        )
        return success(result)

    async def game_launch_cancel(self, body: dict[str, Any]) -> ApiResponse:
        """
        取消当前仍处于准备或文件补全阶段的启动任务。

        :param body: 必须为空的请求对象
        :return: 空的成功响应
        """
        if body:
            return failure("game_launch_cancel 不接受请求参数", "INVALID_REQUEST")
        if not self.game.cancel_launch():
            return failure("当前没有可取消的启动任务", "NO_ACTIVE_LAUNCH")
        return success()

    @_ipc_handler("INSTANCE_STOP_FAILED")
    async def game_instance_stop(self, body: dict[str, Any]) -> ApiResponse:
        """
        通知指定的运行中 Minecraft 实例退出，超时后才强制结束。

        :param body: 符合 ``GameInstanceRequest`` 的请求数据
        :return: 空的成功响应
        """
        try:
            request = GameInstanceRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        await to_thread.run_sync(self.game.stop_instance, request.instance_id)
        return success()


__all__ = ["GameHandlers"]
