import asyncio
import json
import sys
from importlib import import_module
from types import ModuleType, SimpleNamespace

pytauri_module = ModuleType("pytauri")
pytauri_module.__path__ = []  # type: ignore[attr-defined]
pytauri_ipc_module = ModuleType("pytauri.ipc")
pytauri_ipc_module.WebviewWindow = object  # type: ignore[attr-defined]
sys.modules.setdefault("pytauri", pytauri_module)
sys.modules.setdefault("pytauri.ipc", pytauri_ipc_module)

FrontendApi = import_module("ECL.Api.frontend").FrontendApi
ConfigManager = import_module("ECL.Utils.config").ConfigManager


def _reset_singletons() -> None:
    FrontendApi._instance = None
    FrontendApi._initialized = False
    ConfigManager._instance = None
    ConfigManager._initialized = False


def test_launcher_config_uses_effective_runtime_debug(tmp_path, monkeypatch) -> None:
    _reset_singletons()
    monkeypatch.setattr("ECL.Api.frontend.get_runtime_info", lambda: {"app_path": str(tmp_path)})
    launcher = SimpleNamespace(
        config={"launcher": {"debug": True}},
        debug=True,
        launcher_version="0.1.0",
        launcher_version_type="dev",
    )
    api = FrontendApi(launcher)

    result = asyncio.run(api.config_get_many({"sections": ["launcher"]}))

    assert result["success"] is True
    assert result["data"]["launcher"] == {
        "debug": True,
        "version": "0.1.0",
        "version_type": "dev",
    }
    _reset_singletons()


def test_launcher_info_matches_effective_launcher_config(tmp_path, monkeypatch) -> None:
    _reset_singletons()
    monkeypatch.setattr("ECL.Api.frontend.get_runtime_info", lambda: {"app_path": str(tmp_path)})
    launcher = SimpleNamespace(
        config={"launcher": {"debug": True}},
        debug=True,
        launcher_version="0.1.0",
        launcher_version_type="dev",
    )
    api = FrontendApi(launcher)

    result = asyncio.run(api.launcher_info({}))

    assert result["success"] is True
    assert result["data"]["debug"] is True
    assert result["data"]["version"] == "0.1.0"
    assert result["data"]["version_type"] == "dev"
    _reset_singletons()


def test_authlib_server_url_is_persisted_without_credentials(tmp_path, monkeypatch) -> None:
    _reset_singletons()
    monkeypatch.setattr("ECL.Api.frontend.get_runtime_info", lambda: {"app_path": str(tmp_path)})
    api = FrontendApi()

    add_result = asyncio.run(
        api.accounts_add_authlib(
            {
                "server_url": "https://skin.example.com/api/yggdrasil/",
                "email": "player@example.com",
                "password": "secret-password",
            }
        )
    )
    list_result = asyncio.run(api.authlib_servers({}))

    assert add_result["success"] is True
    assert list_result == {
        "success": True,
        "data": [
            {
                "name": "skin.example.com",
                "url": "https://skin.example.com/api/yggdrasil",
                "description": "https://skin.example.com/api/yggdrasil",
            }
        ],
    }

    stored_config = json.loads((tmp_path / "ECL_data" / "setting.json").read_text(encoding="utf-8"))
    assert stored_config["authlib"]["servers"] == ["https://skin.example.com/api/yggdrasil"]
    assert "player@example.com" not in json.dumps(stored_config)
    assert "secret-password" not in json.dumps(stored_config)
    _reset_singletons()


def test_invalid_authlib_server_url_is_not_persisted(tmp_path, monkeypatch) -> None:
    _reset_singletons()
    monkeypatch.setattr("ECL.Api.frontend.get_runtime_info", lambda: {"app_path": str(tmp_path)})
    api = FrontendApi()

    result = asyncio.run(
        api.accounts_add_authlib(
            {
                "server_url": "not-a-url",
                "email": "player@example.com",
                "password": "secret-password",
            }
        )
    )

    assert result["success"] is False
    assert result["errorCode"] == "INVALID_AUTHLIB_SERVER_URL"
    assert api.config_instance.get_config("authlib") is None
    _reset_singletons()
