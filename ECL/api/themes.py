from __future__ import annotations

from typing import Any

from ECL.api.contracts import failure, success
from ECL.api.models import (
    ThemeAssetRequest,
    ThemeDesignDiscardRequest,
    ThemeDesignOverlayRequest,
    ThemeDesignPatchRequest,
    ThemeDesignRevisionRequest,
    ThemeDesignSaveAsRequest,
    ThemeDesignSelectRequest,
    ThemeDesignSessionRequest,
    ThemeDesignStartRequest,
    ThemeExportRequest,
    ThemeIdRequest,
    ThemeImportRequest,
    ThemeSaveRequest,
)
from ECL.services.themes import ThemeRevisionConflict

from .bridge import _FrontendState, _validate_body


class ThemeHandlers(_FrontendState):
    """
    Versioned theme library and shared design-session IPC boundary.
    """

    async def theme_list(self, body: dict[str, Any]) -> dict[str, Any]:
        return success(self.themes.list_presets())

    async def theme_active(self, body: dict[str, Any]) -> dict[str, Any]:
        return success(self.themes.active_preset())

    async def theme_extensions(self, body: dict[str, Any]) -> dict[str, Any]:
        return success(self.themes.extension_catalog())

    async def theme_get(self, body: dict[str, Any]) -> dict[str, Any]:
        request, invalid = _validate_body(ThemeIdRequest, body)
        if invalid is not None:
            return invalid
        return success(self.themes.get_preset(request.preset_id))

    async def theme_save(self, body: dict[str, Any]) -> dict[str, Any]:
        request, invalid = _validate_body(ThemeSaveRequest, body)
        if invalid is not None:
            return invalid
        return success(self.themes.save_preset(request.preset))

    async def theme_asset(self, body: dict[str, Any]) -> dict[str, Any]:
        request, invalid = _validate_body(ThemeAssetRequest, body)
        if invalid is not None:
            return invalid
        return success(self.themes.asset_data_url(request.preset_id, request.asset_path))

    async def theme_delete(self, body: dict[str, Any]) -> dict[str, Any]:
        request, invalid = _validate_body(ThemeIdRequest, body)
        if invalid is not None:
            return invalid
        self.themes.delete_preset(request.preset_id)
        return success()

    async def theme_activate(self, body: dict[str, Any]) -> dict[str, Any]:
        request, invalid = _validate_body(ThemeIdRequest, body)
        if invalid is not None:
            return invalid
        return success(self.themes.activate(request.preset_id))

    async def theme_import(self, body: dict[str, Any]) -> dict[str, Any]:
        request, invalid = _validate_body(ThemeImportRequest, body)
        if invalid is not None:
            return invalid
        return success(self.themes.import_preset(request.source_path, replace=request.replace))

    async def theme_export(self, body: dict[str, Any]) -> dict[str, Any]:
        request, invalid = _validate_body(ThemeExportRequest, body)
        if invalid is not None:
            return invalid
        path = self.themes.export_preset(
            request.preset_id,
            request.output_path,
            include_instance_overrides=request.include_instance_overrides,
        )
        return success({"path": str(path)})

    async def theme_design_start(self, body: dict[str, Any]) -> dict[str, Any]:
        request, invalid = _validate_body(ThemeDesignStartRequest, body)
        if invalid is not None:
            return invalid
        return success(self.themes.start_session(request.preset_id, restore=request.restore))

    async def theme_design_get(self, body: dict[str, Any]) -> dict[str, Any]:
        request, invalid = _validate_body(ThemeDesignSessionRequest, body)
        if invalid is not None:
            return invalid
        return success(self.themes.get_session(request.session_id))

    async def theme_design_select(self, body: dict[str, Any]) -> dict[str, Any]:
        request, invalid = _validate_body(ThemeDesignSelectRequest, body)
        if invalid is not None:
            return invalid
        selection = request.selection.model_dump(mode="json", by_alias=True) if request.selection else None
        return success(self.themes.select(request.session_id, selection))

    async def theme_design_overlay(self, body: dict[str, Any]) -> dict[str, Any]:
        request, invalid = _validate_body(ThemeDesignOverlayRequest, body)
        if invalid is not None:
            return invalid
        slot_hosts = (
            [item.model_dump(mode="json", by_alias=True) for item in request.slot_hosts]
            if request.slot_hosts is not None
            else None
        )
        return success(
            self.themes.set_overlay(request.session_id, show_slots=request.show_slots, slot_hosts=slot_hosts)
        )

    async def theme_design_patch(self, body: dict[str, Any]) -> dict[str, Any]:
        request, invalid = _validate_body(ThemeDesignPatchRequest, body)
        if invalid is not None:
            return invalid
        try:
            snapshot = self.themes.patch(
                request.session_id,
                request.expected_revision,
                [operation.model_dump(mode="json") for operation in request.operations],
            )
        except ThemeRevisionConflict as exc:
            response = failure(str(exc), "THEME_REVISION_CONFLICT")
            response["data"] = exc.snapshot  # type: ignore[typeddict-unknown-key]
            return response
        return success(snapshot)

    async def theme_design_undo(self, body: dict[str, Any]) -> dict[str, Any]:
        request, invalid = _validate_body(ThemeDesignRevisionRequest, body)
        if invalid is not None:
            return invalid
        try:
            return success(self.themes.undo(request.session_id, request.expected_revision))
        except ThemeRevisionConflict as exc:
            response = failure(str(exc), "THEME_REVISION_CONFLICT")
            response["data"] = exc.snapshot  # type: ignore[typeddict-unknown-key]
            return response

    async def theme_design_redo(self, body: dict[str, Any]) -> dict[str, Any]:
        request, invalid = _validate_body(ThemeDesignRevisionRequest, body)
        if invalid is not None:
            return invalid
        try:
            return success(self.themes.redo(request.session_id, request.expected_revision))
        except ThemeRevisionConflict as exc:
            response = failure(str(exc), "THEME_REVISION_CONFLICT")
            response["data"] = exc.snapshot  # type: ignore[typeddict-unknown-key]
            return response

    async def theme_design_commit(self, body: dict[str, Any]) -> dict[str, Any]:
        request, invalid = _validate_body(ThemeDesignSessionRequest, body)
        if invalid is not None:
            return invalid
        return success(self.themes.commit(request.session_id))

    async def theme_design_discard(self, body: dict[str, Any]) -> dict[str, Any]:
        request, invalid = _validate_body(ThemeDesignDiscardRequest, body)
        if invalid is not None:
            return invalid
        self.themes.discard(request.session_id, keep_recovery=request.keep_recovery)
        return success()

    async def theme_design_save_as(self, body: dict[str, Any]) -> dict[str, Any]:
        request, invalid = _validate_body(ThemeDesignSaveAsRequest, body)
        if invalid is not None:
            return invalid
        return success(self.themes.save_as(request.session_id, request.name))


__all__ = ["ThemeHandlers"]
