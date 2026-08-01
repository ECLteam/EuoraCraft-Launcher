import asyncio
import json
import sys
from importlib import import_module
from types import ModuleType, SimpleNamespace

pytauri_module = ModuleType("pytauri")
pytauri_module.__path__ = []  # type: ignore[attr-defined]
pytauri_module.EventTarget = SimpleNamespace(Any=lambda: object())  # type: ignore[attr-defined]
pytauri_module.Commands = object  # type: ignore[attr-defined]
pytauri_module.Builder = object  # type: ignore[attr-defined]
pytauri_module.Context = object  # type: ignore[attr-defined]
pytauri_module.builder_factory = lambda: None  # type: ignore[attr-defined]
pytauri_module.context_factory = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]

pytauri_ffi_module = ModuleType("pytauri.ffi")
pytauri_ffi_module.Emitter = SimpleNamespace(emit_str_to=lambda *args: None)  # type: ignore[attr-defined]

pytauri_ipc_module = ModuleType("pytauri.ipc")
pytauri_ipc_module.WebviewWindow = object  # type: ignore[attr-defined]

sys.modules["pytauri"] = pytauri_module
sys.modules["pytauri.ffi"] = pytauri_ffi_module
sys.modules["pytauri.ipc"] = pytauri_ipc_module

FrontendApi = import_module("ECL.Api").FrontendApi
frontend_module = import_module("ECL.Api.frontend")
ConfigManager = import_module("ECL.Infrastructure").ConfigManager
EventBus = import_module("ECL.Events").EventBus


class FakeAccounts:
    def add_offline(self, username, custom_uuid=None):
        self.last_offline_input = (username, custom_uuid)
        return {"id": "offline-id", "alias": username, "type": "offline", "uuid": "offline-uuid"}


class FakePlugins:
    def __init__(self):
        self.frontend_ready_count = 0

    def on_frontend_ready(self) -> None:
        self.frontend_ready_count += 1

    def list_plugins(self):
        return [{"name": "example", "status": "enabled"}]


class FakeAvatars:
    def render_avatar(self, account_uuid, size, use_default_skin):
        return {
            "dataUrl": f"data:image/png;base64,{account_uuid}:{size}:{use_default_skin}",
            "base64": "avatar",
        }


class FakeInfoCard:
    def get_info_card(self):
        return {
            "mode": "rotate",
            "tips": ["测试提示"],
            "announcements": [],
            "welcome": None,
            "interval": 8000,
        }


class FakeGame:
    def __init__(self):
        self.install_call = None
        self.launch_call = None
        self.requested_paths = None

    def scan_versions(self, paths):
        self.requested_paths = paths
        return [{"id": "1.20.1", "versionId": "1.20.1"}]

    def start_install(self, body, **options):
        self.install_call = (body, options)
        return str(body.get("task_id") or "install-task")

    async def launch_instance(self, body, **options):
        self.launch_call = (body, options)
        return "instance-id"


class FakeWebviewWindow:
    def __init__(self):
        self.visible = False

    def show(self) -> None:
        self.visible = True


def _reset_singletons() -> None:
    FrontendApi._instance = None
    FrontendApi._initialized = False
    ConfigManager._instance = None
    ConfigManager._initialized = False
    EventBus._instance = None
    EventBus._initialized = False


def _build_api(tmp_path) -> FrontendApi:
    _reset_singletons()
    launcher = SimpleNamespace(
        app_path=tmp_path,
        data_path=tmp_path / "ECL_data",
        config={"launcher": {"debug": True}},
        debug=True,
        launcher_version="0.1.0",
        launcher_version_type="dev",
    )
    bus = EventBus()
    bus.register("launcher", launcher)
    bus.register("config", ConfigManager(tmp_path / "ECL_data"))
    bus.register("accounts", FakeAccounts())
    bus.register("avatars", FakeAvatars())
    bus.register("info_card", FakeInfoCard())
    bus.register("game", FakeGame())
    bus.register("plugins", FakePlugins())
    return FrontendApi()


def test_launcher_config_uses_effective_runtime_debug(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.config_get_many({"sections": ["launcher"]}))

    assert result["success"] is True
    assert result["data"]["launcher"] == {
        "debug": True,
        "version": "0.1.0",
        "version_type": "dev",
    }
    _reset_singletons()


def test_launcher_info_matches_effective_launcher_config(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.launcher_info({}))

    assert result["success"] is True
    assert result["data"]["debug"] is True
    assert result["data"]["version"] == "0.1.0"
    assert result["data"]["version_type"] == "dev"
    _reset_singletons()


def test_info_card_delegates_to_registered_service(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.info_card_get({}))

    assert result["success"] is True
    assert result["data"]["tips"] == ["测试提示"]
    assert result["data"]["interval"] == 8000
    _reset_singletons()


def test_scan_versions_delegates_to_registered_service(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.scan_versions({"path": ["D:/Games/.minecraft"]}))

    assert result == {
        "success": True,
        "data": [{"id": "1.20.1", "versionId": "1.20.1"}],
    }
    assert api.game.requested_paths == ["D:/Games/.minecraft"]
    _reset_singletons()


def test_install_version_delegates_to_game_service_with_runtime_options(tmp_path) -> None:
    api = _build_api(tmp_path)
    api.game = FakeGame()
    game_path = tmp_path / ".minecraft"

    result = asyncio.run(
        api.install_version(
            {
                "version_id": "1.21.8",
                "game_path": str(game_path),
                "download_threads": 12,
            }
        )
    )

    assert result == {"success": True, "data": None}
    assert api.game.install_call[0]["version_id"] == "1.21.8"
    assert api.game.install_call[1]["game_path"] == str(game_path)
    assert api.game.install_call[1]["source"] == "official"
    assert api.game.install_call[1]["download_threads"] == 12
    _reset_singletons()


def test_launch_instance_delegates_to_game_service_with_settings(tmp_path) -> None:
    api = _build_api(tmp_path)
    api.game = FakeGame()

    result = asyncio.run(
        api.launch_instance(
            {
                "version_id": "1.21.8",
                "game_path": str(tmp_path / ".minecraft"),
                "java_path": str(tmp_path / "java.exe"),
                "memory": 6144,
                "version_isolation": True,
            }
        )
    )

    assert result == {"success": True, "data": None}
    assert api.game.launch_call[1]["memory"] == 6144
    assert api.game.launch_call[1]["version_isolation"] is True
    assert api.game.launch_call[1]["download_threads"] == 16
    _reset_singletons()


def test_offline_account_delegates_to_registered_service(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.accounts_add_offline({"username": "Steve"}))

    assert result == {
        "success": True,
        "data": {"id": "offline-id", "alias": "Steve", "type": "offline", "uuid": "offline-uuid"},
    }
    _reset_singletons()


def test_offline_account_forwards_optional_custom_uuid(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(
        api.accounts_add_offline(
            {
                "username": "CustomPlayer",
                "uuid": "01234567-89ab-cdef-0123-456789abcdef",
            }
        )
    )

    assert result["success"] is True
    assert api.accounts.last_offline_input == (
        "CustomPlayer",
        "01234567-89ab-cdef-0123-456789abcdef",
    )
    _reset_singletons()


def test_authlib_login_reports_not_implemented(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(
        api.accounts_add_authlib(
            {
                "server_url": "https://skin.example.com/api/yggdrasil",
                "email": "player@example.com",
                "password": "secret-password",
            }
        )
    )

    assert result["success"] is False
    assert result["errorCode"] == "AUTHLIB_NOT_IMPLEMENTED"
    assert result["message"] == "外置登录暂未开发"
    _reset_singletons()


def test_frontend_ready_and_plugin_api_use_registered_framework(tmp_path) -> None:
    api = _build_api(tmp_path)
    webview_window = FakeWebviewWindow()

    ready_result = asyncio.run(api.frontend_ready({}, webview_window))
    plugin_result = asyncio.run(api.plugin_list({}))

    assert ready_result["success"] is True
    assert webview_window.visible is True
    assert api.plugins.frontend_ready_count == 1
    assert plugin_result["data"] == [{"name": "example", "status": "enabled"}]
    _reset_singletons()


def test_frontend_ready_pushes_cacheable_development_warning(tmp_path, monkeypatch) -> None:
    api = _build_api(tmp_path)
    webview_window = FakeWebviewWindow()
    emitted = []
    monkeypatch.setattr(
        frontend_module._Emitter,
        "emit_str_to",
        lambda *args: emitted.append((args[-2], json.loads(args[-1]))),
    )

    asyncio.run(api.frontend_ready({}, webview_window))

    development_popups = [
        payload
        for event, payload in emitted
        if event == "launcher:popup" and payload["id"] == "launcher-development-mode"
    ]
    assert development_popups == [
        {
            "id": "launcher-development-mode",
            "title": "开发模式提示",
            "content": (
                "当前启动器正以 **开发模式** 运行，部分功能可能尚未完成或存在不稳定行为。\n\n"
                "如果遇到问题，请保留相关日志以便排查。"
            ),
            "level": "warning",
            "dismissible": True,
            "cacheable": True,
        }
    ]
    _reset_singletons()


def test_important_backend_events_wait_until_frontend_is_ready(tmp_path, monkeypatch) -> None:
    api = _build_api(tmp_path)
    api.launcher.debug = False
    popup = {
        "id": "queued-popup",
        "title": "排队弹窗",
        "content": "前端就绪前产生的消息。",
        "cacheable": True,
    }
    error = {
        "error_id": "queued-error",
        "title": "后端错误",
        "message": "前端就绪前发生错误。",
        "detail": "测试详情",
    }

    api.emit_popup_to_frontend(popup)
    api.emit_error_to_frontend(error)

    emitted = []
    monkeypatch.setattr(
        frontend_module._Emitter,
        "emit_str_to",
        lambda *args: emitted.append((args[-2], json.loads(args[-1]))),
    )
    asyncio.run(api.frontend_ready({}, FakeWebviewWindow()))

    assert emitted == [
        ("launcher:popup", popup),
        ("launcher:error", error),
    ]
    _reset_singletons()


def test_avatar_data_url_delegates_to_registered_avatar_service(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(
        api.avatar_data_url(
            {
                "uuid": "avatar-id",
                "size": 48,
                "use_default_skin": True,
            }
        )
    )

    assert result["success"] is True
    assert result["data"]["dataUrl"].endswith("avatar-id:48:True")
    _reset_singletons()


def test_debug_maintenance_requires_debug_mode(tmp_path) -> None:
    api = _build_api(tmp_path)
    api.launcher.debug = False

    result = asyncio.run(api.debug_reset_launcher_data({}))

    assert result["success"] is False
    assert result["errorCode"] == "DEBUG_MODE_REQUIRED"
    assert not (api.data_path / ".pending_debug_maintenance.json").exists()
    _reset_singletons()


def test_debug_maintenance_schedules_allowed_action(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.debug_clear_plugins({}))

    assert result["success"] is True
    assert result["data"]["action"] == "clear_plugins"
    assert result["data"]["restart_required"] is True
    assert (api.data_path / ".pending_debug_maintenance.json").is_file()
    _reset_singletons()
