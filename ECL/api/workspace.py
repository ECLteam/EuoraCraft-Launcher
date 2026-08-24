from __future__ import annotations

from collections.abc import Callable
from typing import Any

from anyio import to_thread
from pydantic import BaseModel

from ECL.api.contracts import ApiResponse, failure, success
from ECL.api.models import (
    InstanceCloneRequest,
    InstanceFolderRequest,
    InstancePackExportRequest,
    InstancePackImportRequest,
    InstanceTarget,
    OperationRequest,
    ResourceDeleteRequest,
    ResourceHashRequest,
    ResourceInstallRequest,
    ResourceManifestExportRequest,
    ResourceQuery,
    ResourceSearchRequest,
    ResourceToggleRequest,
    ResourceUpdateCheckRequest,
    ResourceUpdateRequest,
    ScreenshotRequest,
    ScreenshotSaveRequest,
    ScreenshotThumbnailRequest,
    ServerIdRequest,
    ServerOrderRequest,
    ServerStatusRequest,
    ServerUpsertRequest,
    WorldBackupRequest,
    WorldCopyRequest,
    WorldIconRequest,
    WorldImportRequest,
    WorldPatchRequest,
    WorldRequest,
    WorldTransferRequest,
)

from .bridge import _FrontendState, _ipc_handler, _validate_body


class WorkspaceHandlers(_FrontendState):
    """
    暴露实例工作台、内容管理和长任务的 Pydantic IPC 边界。
    """

    async def _validated_call(
        self,
        model: type[BaseModel],
        body: dict[str, Any],
        callback: Callable[[Any], Any],
    ) -> ApiResponse:
        request, invalid = _validate_body(model, body)
        if invalid is not None:
            return invalid
        return success(await to_thread.run_sync(lambda: callback(request)))

    @_ipc_handler("INSTANCE_FOLDER_OPEN_FAILED")
    async def game_instance_folder_open(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            InstanceFolderRequest,
            body,
            lambda request: self.game.open_instance_folder(
                request.game_path, request.version_id, request.folder, request.version_isolation
            ),
        )

    @_ipc_handler("INSTANCE_CLONE_FAILED")
    async def game_instance_clone(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            InstanceCloneRequest,
            body,
            lambda request: self.game.clone_instance(
                request.game_path, request.version_id, request.new_version_id, request.version_isolation
            ),
        )

    @_ipc_handler("INSTANCE_IMPORT_FAILED")
    async def game_instance_import(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            InstancePackImportRequest,
            body,
            lambda request: self.game.import_instance_pack(request.game_path, request.source_path, request.new_version_id),
        )

    @_ipc_handler("INSTANCE_EXPORT_FAILED")
    async def game_instance_export(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            InstancePackExportRequest,
            body,
            lambda request: self.game.export_instance_pack(
                request.game_path, request.version_id, request.output_path, request.pack_format
            ),
        )

    @_ipc_handler("INSTANCE_FILES_CHECK_FAILED")
    async def game_instance_files_check(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            InstanceTarget,
            body,
            lambda request: self.game.inspect_instance_files(request.game_path, request.version_id),
        )

    @_ipc_handler("INSTANCE_FILES_REPAIR_FAILED")
    async def game_instance_files_repair(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            InstanceTarget,
            body,
            lambda request: self.game.repair_instance_files(request.game_path, request.version_id),
        )

    @_ipc_handler("INSTANCE_DELETE_FAILED")
    async def game_instance_delete_to_trash(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            InstanceTarget,
            body,
            lambda request: self.game.delete_instance_to_trash(request.game_path, request.version_id),
        )

    @_ipc_handler("OPERATION_QUERY_FAILED")
    async def game_operation_get(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(OperationRequest, body, lambda request: self.game.operation_get(request.operation_id))

    @_ipc_handler("OPERATION_CANCEL_FAILED")
    async def game_operation_cancel(self, body: dict[str, Any]) -> ApiResponse:
        response = await self._validated_call(
            OperationRequest, body, lambda request: self.game.operation_cancel(request.operation_id)
        )
        if response.get("success") and response.get("data") is False:
            return failure("任务不存在或已经结束", "OPERATION_NOT_CANCELLABLE")
        return response

    @_ipc_handler("WORLD_LIST_FAILED")
    async def game_world_list(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            InstanceTarget,
            body,
            lambda request: self.game.list_worlds(request.game_path, request.version_id, request.version_isolation),
        )

    @_ipc_handler("WORLD_DETAIL_FAILED")
    async def game_world_detail(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            WorldRequest,
            body,
            lambda request: self.game.world_detail(
                request.game_path, request.version_id, request.world_id, request.version_isolation
            ),
        )

    @_ipc_handler("WORLD_UPDATE_FAILED")
    async def game_world_patch(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            WorldPatchRequest,
            body,
            lambda request: self.game.patch_world(
                request.game_path,
                request.version_id,
                request.world_id,
                request.patch.model_dump(by_alias=True, exclude_none=True),
                request.version_isolation,
            ),
        )

    @_ipc_handler("WORLD_COPY_FAILED")
    async def game_world_copy(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            WorldCopyRequest,
            body,
            lambda request: self.game.copy_world(
                request.game_path,
                request.version_id,
                request.world_id,
                request.new_world_id,
                request.version_isolation,
            ),
        )

    @_ipc_handler("WORLD_IMPORT_FAILED")
    async def game_world_import(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            WorldImportRequest,
            body,
            lambda request: self.game.import_world(
                request.game_path, request.version_id, request.source_path, request.version_isolation
            ),
        )

    @_ipc_handler("WORLD_EXPORT_FAILED")
    async def game_world_export(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            WorldTransferRequest,
            body,
            lambda request: self.game.export_world(
                request.game_path,
                request.version_id,
                request.world_id,
                request.output_path,
                request.version_isolation,
            ),
        )

    @_ipc_handler("WORLD_ICON_FAILED")
    async def game_world_icon_set(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            WorldIconRequest,
            body,
            lambda request: self.game.set_world_icon(
                request.game_path,
                request.version_id,
                request.world_id,
                request.source_path,
                request.version_isolation,
            ),
        )

    @_ipc_handler("WORLD_DELETE_FAILED")
    async def game_world_delete_to_trash(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            WorldRequest,
            body,
            lambda request: self.game.delete_world_to_trash(
                request.game_path, request.version_id, request.world_id, request.version_isolation
            ),
        )

    @_ipc_handler("WORLD_BACKUP_FAILED")
    async def game_world_backup_list(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            WorldRequest,
            body,
            lambda request: self.game.list_world_backups(request.game_path, request.version_id, request.world_id),
        )

    @_ipc_handler("WORLD_BACKUP_FAILED")
    async def game_world_backup_create(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            WorldRequest,
            body,
            lambda request: self.game.start_world_backup(
                request.game_path, request.version_id, request.world_id, request.version_isolation
            ),
        )

    @_ipc_handler("WORLD_RESTORE_FAILED")
    async def game_world_backup_restore(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            WorldBackupRequest,
            body,
            lambda request: self.game.restore_world_backup(
                request.game_path,
                request.version_id,
                request.world_id,
                request.backup_id,
                request.version_isolation,
            ),
        )

    @_ipc_handler("WORLD_BACKUP_FAILED")
    async def game_world_backup_lock(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            WorldBackupRequest,
            body,
            lambda request: self.game.lock_world_backup(
                request.game_path, request.version_id, request.world_id, request.backup_id, bool(request.locked)
            ),
        )

    @_ipc_handler("WORLD_BACKUP_FAILED")
    async def game_world_backup_delete_to_trash(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            WorldBackupRequest,
            body,
            lambda request: self.game.delete_world_backup(
                request.game_path, request.version_id, request.world_id, request.backup_id
            ),
        )

    @_ipc_handler("SCREENSHOT_LIST_FAILED")
    async def game_screenshot_list(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            InstanceTarget,
            body,
            lambda request: self.game.list_screenshots(request.game_path, request.version_id, request.version_isolation),
        )

    @_ipc_handler("SCREENSHOT_FAILED")
    async def game_screenshot_thumbnail(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            ScreenshotThumbnailRequest,
            body,
            lambda request: self.game.screenshot_thumbnail(
                request.game_path,
                request.version_id,
                request.screenshot_id,
                request.version_isolation,
                request.size,
            ),
        )

    @_ipc_handler("SCREENSHOT_FAILED")
    async def game_screenshot_copy(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            ScreenshotRequest,
            body,
            lambda request: self.game.copy_screenshot(
                request.game_path, request.version_id, request.screenshot_id, request.version_isolation
            ),
        )

    @_ipc_handler("SCREENSHOT_FAILED")
    async def game_screenshot_save_as(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            ScreenshotSaveRequest,
            body,
            lambda request: self.game.save_screenshot_as(
                request.game_path,
                request.version_id,
                request.screenshot_id,
                request.output_path,
                request.version_isolation,
            ),
        )

    @_ipc_handler("SCREENSHOT_FAILED")
    async def game_screenshot_delete_to_trash(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            ScreenshotRequest,
            body,
            lambda request: self.game.delete_screenshot_to_trash(
                request.game_path, request.version_id, request.screenshot_id, request.version_isolation
            ),
        )

    @_ipc_handler("SCREENSHOT_FAILED")
    async def game_screenshot_set_cover(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            ScreenshotRequest,
            body,
            lambda request: self.game.set_instance_cover(
                request.game_path, request.version_id, request.screenshot_id, request.version_isolation
            ),
        )

    @_ipc_handler("SCREENSHOT_FAILED")
    async def game_screenshot_set_background(self, body: dict[str, Any]) -> ApiResponse:
        request, invalid = _validate_body(ScreenshotRequest, body)
        if invalid is not None:
            return invalid
        candidate = await to_thread.run_sync(
            self.game.set_launcher_background_candidate,
            request.game_path,
            request.version_id,
            request.screenshot_id,
            request.version_isolation,
        )
        current = dict(self._get_effective_config().get("background") or {})
        current.update({"type": "local", "path": candidate["path"]})
        self.config.save_config("background", current)
        return success(candidate)

    @_ipc_handler("SERVER_LIST_FAILED")
    async def game_server_list(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            InstanceTarget,
            body,
            lambda request: self.game.list_servers(request.game_path, request.version_id, request.version_isolation),
        )

    @_ipc_handler("SERVER_UPDATE_FAILED")
    async def game_server_upsert(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            ServerUpsertRequest,
            body,
            lambda request: self.game.upsert_server(
                request.game_path,
                request.version_id,
                request.server_id,
                request.name,
                request.address,
                request.favorite,
                request.version_isolation,
            ),
        )

    @_ipc_handler("SERVER_DELETE_FAILED")
    async def game_server_delete(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            ServerIdRequest,
            body,
            lambda request: self.game.delete_server(
                request.game_path, request.version_id, request.server_id, request.version_isolation
            ),
        )

    @_ipc_handler("SERVER_ORDER_FAILED")
    async def game_server_reorder(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            ServerOrderRequest,
            body,
            lambda request: self.game.reorder_servers(
                request.game_path, request.version_id, request.server_ids, request.version_isolation
            ),
        )

    @_ipc_handler("SERVER_STATUS_FAILED")
    async def game_server_status_refresh(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            ServerStatusRequest,
            body,
            lambda request: self.game.refresh_server_statuses(request.addresses, request.timeout),
        )

    @_ipc_handler("RESOURCE_LIST_FAILED")
    async def game_resource_list(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            ResourceQuery,
            body,
            lambda request: self.game.list_resources(
                request.game_path,
                request.version_id,
                request.resource_type,
                request.version_isolation,
                request.world_id,
            ),
        )

    @_ipc_handler("RESOURCE_INSTALL_FAILED")
    async def game_resource_install(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            ResourceInstallRequest,
            body,
            lambda request: self.game.install_resources(
                request.game_path,
                request.version_id,
                request.resource_type,
                request.source_paths,
                request.version_isolation,
                request.world_id,
            ),
        )

    @_ipc_handler("RESOURCE_TOGGLE_FAILED")
    async def game_resource_toggle(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            ResourceToggleRequest,
            body,
            lambda request: self.game.toggle_resource(
                request.game_path,
                request.version_id,
                request.resource_type,
                request.resource_id,
                request.enabled,
                request.version_isolation,
                request.world_id,
            ),
        )

    @_ipc_handler("RESOURCE_DELETE_FAILED")
    async def game_resource_delete_to_trash(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            ResourceDeleteRequest,
            body,
            lambda request: self.game.delete_resources_to_trash(
                request.game_path,
                request.version_id,
                request.resource_type,
                request.resource_ids,
                request.version_isolation,
                request.world_id,
            ),
        )

    @_ipc_handler("RESOURCE_MANIFEST_FAILED")
    async def game_resource_manifest_export(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            ResourceManifestExportRequest,
            body,
            lambda request: self.game.export_resource_manifest(
                request.game_path,
                request.version_id,
                request.resource_type,
                request.output_path,
                request.output_format,
                request.version_isolation,
                request.world_id,
            ),
        )

    @_ipc_handler("RESOURCE_SEARCH_FAILED")
    async def game_resource_search(self, body: dict[str, Any]) -> ApiResponse:
        curseforge_key = str((self._get_effective_config().get("download") or {}).get("curseforge_api_key") or "")
        return await self._validated_call(
            ResourceSearchRequest,
            body,
            lambda request: self.game.search_online_resources(
                request.query,
                request.game_version,
                request.loader,
                request.source,
                curseforge_key or None,
                request.limit,
            ),
        )

    @_ipc_handler("RESOURCE_IDENTIFY_FAILED")
    async def game_resource_identify(self, body: dict[str, Any]) -> ApiResponse:
        curseforge_key = str((self._get_effective_config().get("download") or {}).get("curseforge_api_key") or "")
        return await self._validated_call(
            ResourceHashRequest,
            body,
            lambda request: self.game.identify_resource_hash(request.sha512, curseforge_key or None),
        )

    @_ipc_handler("RESOURCE_UPDATE_CHECK_FAILED")
    async def game_resource_update_check(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            ResourceUpdateCheckRequest,
            body,
            lambda request: self.game.check_resource_updates(
                request.game_path,
                request.version_id,
                request.resource_type,
                request.game_version,
                request.loader,
                request.version_isolation,
                request.world_id,
            ),
        )

    @_ipc_handler("RESOURCE_UPDATE_FAILED")
    async def game_resource_update(self, body: dict[str, Any]) -> ApiResponse:
        return await self._validated_call(
            ResourceUpdateRequest,
            body,
            lambda request: self.game.update_resource(
                request.game_path,
                request.version_id,
                request.resource_type,
                request.resource_id,
                request.update,
                request.version_isolation,
                request.world_id,
            ),
        )


__all__ = ["WorkspaceHandlers"]
