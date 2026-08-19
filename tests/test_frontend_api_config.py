import asyncio
import json
import sys
from importlib import import_module
from pathlib import Path
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

pytauri_plugins_dialog_module = ModuleType("pytauri_plugins.dialog")
pytauri_plugins_dialog_module.DialogExt = object  # type: ignore[attr-defined]
pytauri_plugins_dialog_module.init = lambda: None  # type: ignore[attr-defined]

sys.modules["pytauri"] = pytauri_module
sys.modules["pytauri.ffi"] = pytauri_ffi_module
sys.modules["pytauri.ipc"] = pytauri_ipc_module
sys.modules["pytauri_plugins.dialog"] = pytauri_plugins_dialog_module

FrontendApi = import_module("ECL.api").FrontendApi
Adapter = import_module("ECL.adapters.tauri").Adapter
frontend_module = import_module("ECL.api.frontend")
files_module = import_module("ECL.api.files")
ConfigManager = import_module("ECL.utils").ConfigManager
EventBus = import_module("ECL.events").EventBus
AccountError = import_module("ECL.services.accounts").AccountError
command_handlers = import_module("ECL.api.registry").command_handlers


class FakeAccounts:
    def list_accounts(self):
        account = {
            "id": "microsoft-account",
            "alias": "Player",
            "type": "microsoft",
            "uuid": "profile-id",
            "isCurrent": True,
        }
        return {"accounts": [account], "current": account}

    def microsoft_login_config(self):
        return {"available": True}

    def texture_urls(self, account_id):
        assert account_id == "microsoft-account"
        return {"skinUrl": "https://textures.example.com/skin.png", "skinModel": "slim"}

    def add_offline(self, username, custom_uuid=None, skin=None):
        self.last_offline_input = (username, custom_uuid)
        self.last_offline_skin = skin
        return {"id": "offline-id", "alias": username, "type": "offline", "uuid": "offline-uuid"}

    def default_skins(self):
        return [{"id": "alice", "name": "Alice", "skinUrl": "data:image/png;base64,AAAA"}]

    def set_offline_skin(self, account_id, skin):
        self.last_offline_skin = skin
        return {
            "accounts": [{"id": account_id, "alias": "Steve", "type": "offline", "skin": skin}],
            "current": {"id": account_id},
        }

    def add_authlib(self, server_url, username, password):
        self.last_authlib_input = (server_url, username, password)
        return {
            "id": "authlib-id",
            "alias": "AuthlibPlayer",
            "type": "authlib",
            "uuid": "authlib-uuid",
            "auth_server": server_url,
        }

    def resolve_authlib_server(self, server_url):
        return f"{server_url.rstrip('/')}/api/yggdrasil"

    def select_authlib_profile(self, account_id, profile_id):
        self.last_authlib_profile = (account_id, profile_id)
        return {
            "id": account_id,
            "alias": "SelectedPlayer",
            "type": "authlib",
            "uuid": profile_id,
            "isCurrent": True,
        }

    async def upload_skin(self, account_id, model, texture):
        self.uploaded_skin = (account_id, model, texture)
        return {"id": account_id, "alias": "Player", "type": "microsoft"}


class FakePlugins:
    def __init__(self):
        self.frontend_ready_count = 0
        self.sidebar_states = []

    def on_frontend_ready(self) -> None:
        self.frontend_ready_count += 1

    def list_plugins(self):
        return [{"name": "example", "status": "enabled"}]

    def set_sidebar_state(self, collapsed: bool) -> None:
        self.sidebar_states.append(collapsed)


class FakeWardrobe:
    def list_items(self):
        return []

    def read_texture(self, item_id):
        return (
            {
                "id": item_id,
                "kind": "skin",
                "model": "slim",
                "width": 64,
                "height": 64,
            },
            b"png",
        )

    def import_bytes(self, texture, kind, name, model):
        self.imported = (texture, kind, name, model)
        return (
            {
                "id": "synced-skin",
                "kind": kind,
                "name": name,
                "model": model,
                "width": 64,
                "height": 64,
            },
            False,
        )


class FakeHttpResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def raise_for_status(self):
        return None

    def iter_bytes(self, _chunk_size):
        yield b"downloaded-png"


class FakeHttp:
    def stream(self, method, url):
        assert method == "GET"
        assert url == "https://textures.example.com/skin.png"
        return FakeHttpResponse()


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
        self.scan_force = False
        self.crash_call = None

    def curseforge_available(self):
        return True

    def scan_versions(self, paths, *, force=False):
        self.requested_paths = paths
        self.scan_force = force
        return [{"id": "1.20.1", "versionId": "1.20.1"}]

    def scan_java(self, user_paths):
        return [
            {
                "path": user_paths[0] if user_paths else "C:/Java/bin/java.exe",
                "version": "21.0.7",
                "major_version": 21,
                "java_type": "OpenJDK",
                "arch": "x64",
                "sources": ["system"],
            }
        ]

    def install_version(self, body, **options):
        self.install_call = (body, options)
        return {
            "taskId": str(body.get("task_id") or "install-task"),
            "versionId": body["version_id"],
            "versionName": body.get("version_name") or body["version_id"],
        }

    async def launch_instance(self, body, **options):
        self.launch_call = (body, options)
        return {
            "instanceId": "instance-id",
            "versionId": body["version_id"],
            "gamePath": str(options["game_path"]),
        }

    def analyze_crash_file(self, file_path, game_path, version_id):
        self.crash_call = (file_path, game_path, version_id)
        return {
            "reportId": "a" * 32,
            "versionId": version_id,
            "exitCode": None,
            "detectedBy": ["manual"],
            "reasons": [],
            "sourceFiles": [Path(file_path).name],
            "hasOutput": True,
        }

    def get_crash_output(self, report_id):
        return {"name": "game-output.log", "content": f"output:{report_id}"}

    def export_crash_report(self, report_id, output_path=None):
        return {"path": str(output_path or f"C:/exports/{report_id}.zip")}


class FakeWebviewWindow:
    def __init__(self):
        self.visible = False
        self.minimized = True
        self.focused = False
        self.main_thread_calls = 0

    def show(self) -> None:
        self.visible = True

    def unminimize(self) -> None:
        self.minimized = False

    def set_focus(self) -> None:
        self.focused = True

    def run_on_main_thread(self, handler) -> None:
        self.main_thread_calls += 1
        handler()


def _build_api(tmp_path) -> FrontendApi:
    launcher = SimpleNamespace(
        app_path=tmp_path,
        data_path=tmp_path / "ECL_data",
        config={"launcher": {"debug": True}},
        debug=True,
        launcher_version="0.1.0",
        launcher_version_type="dev",
    )
    bus = EventBus()
    context = SimpleNamespace(
        state=launcher,
        events=bus,
        config=ConfigManager(tmp_path / "ECL_data", bus),
        http=FakeHttp(),
        accounts=FakeAccounts(),
        connector=SimpleNamespace(),
        wardrobe=FakeWardrobe(),
        info_card=FakeInfoCard(),
        game=FakeGame(),
        plugins=FakePlugins(),
        processes=SimpleNamespace(),
    )
    return FrontendApi(context)


def test_launcher_config_uses_effective_runtime_debug(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.settings_get({"sections": ["launcher"]}))

    assert result["success"] is True
    assert result["data"]["launcher"] == {
        "debug": True,
        "disable_ssl_verify": False,
        "version": "0.1.0",
        "version_type": "dev",
    }


def test_launcher_info_matches_effective_launcher_config(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.launcher_info({}))

    assert result["success"] is True
    assert result["data"]["debug"] is True
    assert result["data"]["version"] == "0.1.0"
    assert result["data"]["version_type"] == "dev"


def test_info_card_delegates_to_registered_service(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.info_card_get({}))

    assert result["success"] is True
    assert result["data"]["tips"] == ["测试提示"]
    assert result["data"]["interval"] == 8000


def test_user_agreement_state_is_persisted_by_formal_system_api(tmp_path) -> None:
    api = _build_api(tmp_path)

    saved = asyncio.run(api.user_agreement_save({}))
    loaded = asyncio.run(api.user_agreement_get({}))
    cleared = asyncio.run(api.user_agreement_clear({}))

    assert saved["success"] is True
    assert saved["data"]["accepted"] is True
    assert loaded == saved
    assert cleared["success"] is True


def test_java_scan_delegates_to_game_service(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.game_java_scan({}))

    assert result["success"] is True
    assert result["data"][0]["major_version"] == 21
    assert result["data"][0]["path"] == "C:/Java/bin/java.exe"


def test_scan_versions_delegates_to_registered_service(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.game_scan({"paths": ["D:/Games/.minecraft"]}))

    assert result == {
        "success": True,
        "data": [{"id": "1.20.1", "versionId": "1.20.1"}],
    }
    assert [Path(path) for path in api.game.requested_paths] == [Path("D:/Games/.minecraft")]

    forced_result = asyncio.run(api.game_scan({"paths": ["D:/Games/.minecraft"], "force": True}))
    assert forced_result["success"] is True
    assert api.game.scan_force is True


def test_install_version_delegates_to_game_service_with_runtime_options(tmp_path) -> None:
    api = _build_api(tmp_path)
    api.game = FakeGame()
    game_path = tmp_path / ".minecraft"

    result = asyncio.run(
        api.game_install(
            {
                "version_id": "1.21.8",
                "game_path": str(game_path),
            }
        )
    )

    assert result == {
        "success": True,
        "data": {"taskId": "install-task", "versionId": "1.21.8", "versionName": "1.21.8"},
    }
    assert api.game.install_call[0]["version_id"] == "1.21.8"
    assert api.game.install_call[1]["game_path"] == game_path
    assert api.game.install_call[1]["source"] == "official"


def test_launch_instance_delegates_to_game_service_with_settings(tmp_path) -> None:
    api = _build_api(tmp_path)
    api.game = FakeGame()

    result = asyncio.run(
        api.game_launch(
            {
                "version_id": "1.21.8",
                "game_path": str(tmp_path / ".minecraft"),
                "java_path": str(tmp_path / "java.exe"),
                "memory": 6144,
                "version_isolation": True,
            }
        )
    )

    assert result == {
        "success": True,
        "data": {
            "instanceId": "instance-id",
            "versionId": "1.21.8",
            "gamePath": str(tmp_path / ".minecraft"),
        },
    }
    assert api.game.launch_call[1]["memory"] == 6144
    assert api.game.launch_call[1]["version_isolation"] is True


def test_crash_report_commands_validate_and_delegate(tmp_path) -> None:
    api = _build_api(tmp_path)
    log_path = tmp_path / "latest.log"
    log_path.write_text("crash", encoding="utf-8")
    report_id = "a" * 32

    analyzed = asyncio.run(
        api.game_crash_analyze(
            {
                "file_path": str(log_path),
                "game_path": str(tmp_path / ".minecraft"),
                "version_id": "1.21.8",
            }
        )
    )
    output = asyncio.run(api.game_crash_output({"report_id": report_id}))
    exported = asyncio.run(api.game_crash_export({"report_id": report_id}))

    assert analyzed["success"] is True
    assert analyzed["data"]["reportId"] == report_id
    assert api.game.crash_call == (log_path, tmp_path / ".minecraft", "1.21.8")
    assert output["data"]["content"] == f"output:{report_id}"
    assert exported["data"]["path"].endswith(f"{report_id}.zip")


def test_crash_report_id_rejects_invalid_values(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.game_crash_output({"report_id": "../report"}))

    assert result["success"] is False
    assert result["errorCode"] == "INVALID_REQUEST"


def test_select_save_file_uses_system_dialog_and_normalizes_zip_suffix(tmp_path, monkeypatch) -> None:
    api = _build_api(tmp_path)
    api._webview = object()
    calls = []

    class FakeSaveDialog:
        def blocking_save_file(self, **options):
            calls.append(options)
            return tmp_path / "crash-report"

    monkeypatch.setattr(files_module, "DialogExt", SimpleNamespace(file=lambda _webview: FakeSaveDialog()))

    result = asyncio.run(api.select_save_file({"purpose": "crash-report"}))

    assert result == {"success": True, "data": {"path": str(tmp_path / "crash-report.zip")}}
    assert calls == [
        {
            "add_filter": ("ZIP 压缩包", ["zip"]),
            "set_file_name": "EuoraCraft-crash-report.zip",
            "set_title": "保存 Minecraft 崩溃报告",
        }
    ]


def test_offline_account_delegates_to_registered_service(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.accounts_add_offline({"username": "Steve"}))

    assert result == {
        "success": True,
        "data": {"id": "offline-id", "alias": "Steve", "type": "offline", "uuid": "offline-uuid"},
    }


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


def test_offline_account_forwards_optional_skin(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.accounts_add_offline({"username": "Steve", "skin": "Alice"}))

    assert result["success"] is True
    assert api.accounts.last_offline_skin == "Alice"


def test_offline_default_skins_handler(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.accounts_default_skins({}))

    assert result == {
        "success": True,
        "data": [{"id": "alice", "name": "Alice", "skinUrl": "data:image/png;base64,AAAA"}],
    }


def test_offline_set_skin_handler(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.accounts_set_offline_skin({"account_id": "offline-id", "skin": "alice"}))

    assert result["success"] is True
    assert api.accounts.last_offline_skin == "alice"


def test_authlib_login_uses_account_manager_and_remembers_server(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    api = _build_api(tmp_path)

    result = asyncio.run(
        api.accounts_add_authlib(
            {
                "server_url": "https://skin.example.com/api/yggdrasil/",
                "email": "player@example.com",
                "password": "secret-password",
            }
        )
    )

    assert result["success"] is True
    assert result["data"]["id"] == "authlib-id"
    assert api.accounts.last_authlib_input == (
        "https://skin.example.com/api/yggdrasil/",
        "player@example.com",
        "secret-password",
    )
    # 外置登录服务器历史保存在独立用户文件中，setting.json 不再包含账户相关数据。
    assert api.config.get_config("authlib") is None
    servers_file = tmp_path / "home" / ".ECL" / "accounts" / "authlib" / "servers.json"
    assert json.loads(servers_file.read_text(encoding="utf-8")) == [
        {
            "url": "https://skin.example.com/api/yggdrasil/",
            "email": "player@example.com",
        }
    ]
    saved_servers = asyncio.run(api.authlib_servers({}))
    assert saved_servers["data"][0]["url"] == "https://skin.example.com/api/yggdrasil/"
    assert saved_servers["data"][0]["email"] == "player@example.com"


def test_authlib_profile_selection_is_forwarded_to_account_manager(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(
        api.accounts_select_authlib_profile({"account_id": "pending-authlib", "profile_id": "profile-two"})
    )

    assert result["success"] is True
    assert result["data"]["uuid"] == "profile-two"
    assert api.accounts.last_authlib_profile == ("pending-authlib", "profile-two")


def test_authlib_server_url_is_resolved_through_ali(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.authlib_resolve_server({"server_url": "skin.example.com"}))

    assert result == {
        "success": True,
        "data": "https://skin.example.com/api/yggdrasil",
    }


def test_frontend_ready_and_plugin_api_use_registered_framework(tmp_path) -> None:
    api = _build_api(tmp_path)
    webview_window = FakeWebviewWindow()

    ready_result = asyncio.run(api.frontend_ready({}, webview_window))
    plugin_result = asyncio.run(api.plugin_list({}))

    assert ready_result["success"] is True
    assert webview_window.visible is True
    assert api.plugins.frontend_ready_count == 1
    assert plugin_result["data"] == [{"name": "example", "status": "enabled"}]


def test_focus_window_restores_and_focuses_webview(tmp_path) -> None:
    api = _build_api(tmp_path)
    webview_window = FakeWebviewWindow()
    asyncio.run(api.frontend_ready({}, webview_window))

    assert api.focus_window() is True
    assert webview_window.minimized is False
    assert webview_window.visible is True
    assert webview_window.focused is True


def test_microsoft_authorization_event_focuses_before_forwarding() -> None:
    calls = []
    api = SimpleNamespace(
        focus_window=lambda: calls.append("focus"),
        emit_to_frontend=lambda event, data: calls.append((event, data)),
    )
    adapter = object.__new__(Adapter)
    adapter.frontend_api_instance = api
    event = {"status": "progress", "stage": "authorization_confirmed", "focus": True}

    adapter._forward_microsoft_login_status(event)

    assert calls == ["focus", ("accounts_microsoft_login_status", event)]


def test_adapter_forwards_launcher_notifications(tmp_path, monkeypatch) -> None:
    api = _build_api(tmp_path)
    forwarded = []
    monkeypatch.setattr(api, "emit_to_frontend", lambda event, payload: forwarded.append((event, payload)))
    adapter = object.__new__(Adapter)
    adapter.frontend_api_instance = api
    adapter.events = api.events
    payload = {"type": "warning", "title": "Notice", "message": "Please check settings"}

    adapter._register_events()
    api.events.emit("launcher:notify", payload)

    assert forwarded == [("launcher:notify", payload)]


def test_sidebar_state_is_forwarded_to_plugins(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.plugin_notify_sidebar_state({"collapsed": True}))

    assert result["success"] is True
    assert api.plugins.sidebar_states == [True]

    invalid = asyncio.run(api.plugin_notify_sidebar_state({"collapsed": "yes"}))
    assert invalid == {
        "success": False,
        "message": "侧栏状态必须是布尔值",
        "errorCode": "INVALID_SIDEBAR_STATE",
        "presentation": "message",
    }


def test_unexpected_ipc_error_returns_correlated_modal_and_emits_event(tmp_path, monkeypatch) -> None:
    api = _build_api(tmp_path)
    emitted = []
    api.events.subscribe("launcher:error", emitted.append)
    monkeypatch.setattr(api.accounts, "list_accounts", lambda: (_ for _ in ()).throw(RuntimeError("secret detail")))

    result = asyncio.run(command_handlers(api)["accounts_list"]({}))

    assert result["success"] is False
    assert result["errorCode"] == "INTERNAL_ERROR"
    assert result["presentation"] == "modal"
    assert result["errorId"]
    assert "secret detail" not in result["message"]
    assert emitted == [
        {
            "error_id": result["errorId"],
            "title": result["title"],
            "message": result["message"],
        }
    ]


def test_critical_persistence_error_returns_modal_metadata_and_emits_event(tmp_path, monkeypatch) -> None:
    api = _build_api(tmp_path)
    emitted = []
    api.events.subscribe("launcher:error", emitted.append)
    monkeypatch.setattr(
        api.accounts,
        "remove_account",
        lambda *_args: (_ for _ in ()).throw(AccountError("保存账号数据失败", "ACCOUNT_SAVE_FAILED")),
        raising=False,
    )

    result = asyncio.run(api.accounts_remove({"account_id": "account"}))

    assert result["success"] is False
    assert result["errorCode"] == "ACCOUNT_SAVE_FAILED"
    assert result["presentation"] == "modal"
    assert result["message"] == "账号数据保存失败，请重试。若问题持续，请导出日志以便排查。"
    assert result["detail"] == "保存账号数据失败"
    assert emitted[0]["error_id"] == result["errorId"]
    assert emitted[0]["message"] == result["message"]
    assert emitted[0]["detail"] == "保存账号数据失败"


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
        "kind": "game_crash",
        "crash": {
            "reportId": "a" * 32,
            "versionId": "1.21.8",
            "detectedBy": ["exit_code"],
            "reasons": [],
            "sourceFiles": [],
            "hasOutput": False,
        },
    }

    api.emit_popup_to_frontend(popup)
    api.emit_error_to_frontend(error)

    emitted = []
    monkeypatch.setattr(
        frontend_module._Emitter,
        "emit_str_to",
        lambda *args: emitted.append((args[-2], json.loads(args[-1]))),
    )
    webview = FakeWebviewWindow()
    asyncio.run(api.frontend_ready({}, webview))

    assert emitted == [
        ("launcher:popup", popup),
        ("launcher:error", error),
    ]
    assert webview.main_thread_calls == 2


def test_ready_frontend_events_are_marshaled_to_main_thread(tmp_path, monkeypatch) -> None:
    api = _build_api(tmp_path)
    api.launcher.debug = False
    webview = FakeWebviewWindow()
    asyncio.run(api.frontend_ready({}, webview))
    emitted = []
    monkeypatch.setattr(
        frontend_module._Emitter,
        "emit_str_to",
        lambda *args: emitted.append((args[-2], json.loads(args[-1]))),
    )
    payload = {"error_id": "worker-error", "title": "崩溃", "message": "后台分析完成"}

    api.emit_error_to_frontend(payload)

    assert webview.main_thread_calls == 1
    assert emitted == [("launcher:error", payload)]


def test_serious_errors_remain_available_until_frontend_acknowledges_them(tmp_path) -> None:
    api = _build_api(tmp_path)
    payload = {"error_id": "recoverable-event", "title": "崩溃", "message": "后台分析完成"}

    api.emit_error_to_frontend(payload)
    pending = asyncio.run(api.launcher_errors_pending({}))
    acknowledged = asyncio.run(api.launcher_errors_ack({"error_ids": ["recoverable-event"]}))
    empty = asyncio.run(api.launcher_errors_pending({}))

    assert pending == {"success": True, "data": [payload]}
    assert acknowledged == {"success": True, "data": {"removed": 1}}
    assert empty == {"success": True, "data": []}


def test_wardrobe_list_delegates_to_registered_store(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.wardrobe_list({}))

    assert result["success"] is True
    assert result["data"] == []


def test_wardrobe_sync_downloads_current_account_skin_into_store(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.wardrobe_sync_account_skin({"account_id": "microsoft-account"}))

    assert result["success"] is True
    assert result["data"]["item"]["id"] == "synced-skin"
    assert api.wardrobe.imported == (
        b"downloaded-png",
        "skin",
        "Player 当前皮肤",
        "slim",
    )


def test_wardrobe_apply_skin_uploads_internal_texture_without_base64_body(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(
        api.wardrobe_apply_skin({"item_id": "skin-id", "account_id": "microsoft-account"})
    )

    assert result["success"] is True
    assert api.accounts.uploaded_skin == ("microsoft-account", "slim", b"png")


def test_debug_maintenance_requires_debug_mode(tmp_path) -> None:
    api = _build_api(tmp_path)
    api.launcher.debug = False

    result = asyncio.run(api.debug_reset_launcher_data({}))

    assert result["success"] is False
    assert result["errorCode"] == "DEBUG_MODE_REQUIRED"
    assert not (api.data_path / ".pending_debug_maintenance.json").exists()


def test_debug_maintenance_schedules_allowed_action(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.debug_clear_plugins({}))

    assert result["success"] is True
    assert result["data"]["action"] == "clear_plugins"
    assert result["data"]["restart_required"] is True
    assert (api.data_path / ".pending_debug_maintenance.json").is_file()
