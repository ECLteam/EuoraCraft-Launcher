from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from ECL.api.game import GameHandlers
from ECL.api.models import (
    GameVersionRequest,
    InstallRequest,
    LaunchRequest,
    LoaderCatalogRequest,
    SettingsQuery,
    WardrobeImportRequest,
    request_schemas,
)


def test_request_models_accept_valid_payloads() -> None:
    query = SettingsQuery.model_validate({"sections": ["launcher", "game"]})
    install = InstallRequest.model_validate(
        {"version_id": "1.21.1", "game_path": ".minecraft", "loader_type": "fabric"}
    )
    launch = LaunchRequest.model_validate({"version_id": "1.21.1", "game_path": ".minecraft"})
    version_stats = GameVersionRequest.model_validate({"version_id": "1.21.1", "game_path": ".minecraft"})
    wardrobe = WardrobeImportRequest.model_validate({"path": "skin.png", "kind": "skin", "model": "slim"})

    assert query.sections == ["launcher", "game"]
    assert install.loader_type.value == "fabric"
    assert launch.memory == 4096
    assert version_stats.version_id == "1.21.1"
    assert wardrobe.model.value == "slim"


@pytest.mark.parametrize(
    "model,payload",
    [
        (LoaderCatalogRequest, {"loader": "unknown", "game_version": "1.21.1"}),
        (LoaderCatalogRequest, {"loader": "fabric", "game_version": "1.21.1", "source": "mirror"}),
        (InstallRequest, {"game_path": ".minecraft"}),
        (LaunchRequest, {"version_id": "1.21.1", "game_path": ".minecraft", "memory": 1}),
        (LaunchRequest, {"version_id": "1.21.1", "game_path": "bad\0path"}),
        (WardrobeImportRequest, {"path": "cape.png", "kind": "cape", "model": "slim"}),
    ],
)
def test_request_models_reject_invalid_payloads(model, payload) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_request_schema_contains_every_consolidated_typed_command() -> None:
    schemas = request_schemas()

    assert set(schemas) == {
        "settings_get",
        "settings_set",
        "game_versions",
        "game_loader_versions",
        "game_scan",
        "game_java_scan",
        "game_install",
        "game_launch",
        "game_uninstall",
        "game_config_get",
        "game_config_set",
        "game_config_patch",
        "game_version_stats",
        "game_instance_stop",
        "wardrobe_import",
        "wardrobe_sync_account_skin",
        "wardrobe_update",
        "wardrobe_delete",
        "wardrobe_texture",
        "wardrobe_export",
        "wardrobe_apply_skin",
        "accounts_texture_urls",
        "select_image",
        "microsoft_reset_skin",
        "microsoft_set_cape",
        "microsoft_reset_cape",
    }
    assert all(schema["type"] == "object" for schema in schemas.values())


@pytest.mark.asyncio
async def test_invalid_ipc_payload_uses_stable_error_code() -> None:
    handler = object.__new__(GameHandlers)

    response = await handler.game_loader_versions({"loader": "invalid"})

    assert response["success"] is False
    assert response["errorCode"] == "INVALID_REQUEST"


@pytest.mark.asyncio
async def test_version_stats_ipc_validates_and_forwards_target() -> None:
    handler = object.__new__(GameHandlers)
    calls = []
    handler.game = SimpleNamespace(
        get_version_stats=lambda game_path, version_id: calls.append((game_path, version_id))
        or {"launchCount": 1, "lastRunDurationSeconds": 2, "totalRunDurationSeconds": 3}
    )

    response = await handler.game_version_stats({"game_path": ".minecraft", "version_id": "1.21.1"})

    assert response["success"] is True
    assert response["data"]["totalRunDurationSeconds"] == 3
    assert calls[0][1] == "1.21.1"
