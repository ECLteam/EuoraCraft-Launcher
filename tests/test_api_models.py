from __future__ import annotations

import pytest
from pydantic import ValidationError

from ECL.api.game import GameHandlers
from ECL.api.models import (
    InstallRequest,
    LaunchRequest,
    LoaderCatalogRequest,
    SettingsQuery,
    request_schemas,
)


def test_request_models_accept_valid_payloads() -> None:
    query = SettingsQuery.model_validate({"sections": ["launcher", "game"]})
    install = InstallRequest.model_validate(
        {"version_id": "1.21.1", "game_path": ".minecraft", "loader_type": "fabric"}
    )
    launch = LaunchRequest.model_validate({"version_id": "1.21.1", "game_path": ".minecraft"})

    assert query.sections == ["launcher", "game"]
    assert install.loader_type.value == "fabric"
    assert launch.memory == 4096


@pytest.mark.parametrize(
    "model,payload",
    [
        (LoaderCatalogRequest, {"loader": "unknown", "game_version": "1.21.1"}),
        (LoaderCatalogRequest, {"loader": "fabric", "game_version": "1.21.1", "source": "mirror"}),
        (InstallRequest, {"game_path": ".minecraft"}),
        (LaunchRequest, {"version_id": "1.21.1", "game_path": ".minecraft", "memory": 1}),
        (LaunchRequest, {"version_id": "1.21.1", "game_path": "bad\0path"}),
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
        "game_instance_stop",
    }
    assert all(schema["type"] == "object" for schema in schemas.values())


@pytest.mark.asyncio
async def test_invalid_ipc_payload_uses_stable_error_code() -> None:
    handler = object.__new__(GameHandlers)

    response = await handler.game_loader_versions({"loader": "invalid"})

    assert response["success"] is False
    assert response["errorCode"] == "INVALID_REQUEST"
