import asyncio
import sys
from importlib import import_module
from io import BytesIO
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import httpx
from PIL import Image


class _MockEmitter:
    @staticmethod
    def emit_str(*args):
        pass

    @staticmethod
    def emit_str_to(*args):
        pass

    @staticmethod
    def emit_str_filter(*args):
        pass


pytauri_ffi_module = ModuleType("pytauri.ffi")
pytauri_ffi_module.Emitter = _MockEmitter
pytauri_ffi_module.EXT_MOD = SimpleNamespace(pytauri_plugins=MagicMock())
for _ffi_name in [
    "IS_DEV", "RESTART_EXIT_CODE", "VERSION", "App", "AppHandle", "Assets",
    "Builder", "BuilderArgs", "CloseRequestApi", "Context", "CursorIcon",
    "DragDropEvent", "DragDropEventType", "Event", "EventId", "EventTargetType",
    "ExitRequestApi", "ImplEmitter", "ImplListener", "ImplManager", "Listener",
    "LogicalRect", "Manager", "PhysicalRect", "Position", "PositionType",
    "Rect", "RunEvent", "RunEventType", "Size", "SizeType", "Theme", "Url",
    "UserAttentionType", "WebviewEvent", "WebviewEventType", "WebviewUrl",
    "WebviewUrlType", "WindowEvent", "WindowEventType",
]:
    setattr(pytauri_ffi_module, _ffi_name, object)
pytauri_ffi_module.EventTarget = SimpleNamespace(Any=lambda: object())
pytauri_ffi_module.builder_factory = lambda: None
pytauri_ffi_module.context_factory = lambda *_args, **_kwargs: None
pytauri_ffi_module.webview_version = lambda: None

pytauri_ffi_typing_module = ModuleType("pytauri.ffi._typing")
pytauri_ffi_typing_module.Pyo3PathFrom = object
pytauri_ffi_typing_module.Pyo3PathInto = object

pytauri_ipc_module = ModuleType("pytauri.ipc")
pytauri_ipc_module.WebviewWindow = object
pytauri_ipc_module.Commands = object
pytauri_ipc_module.State = object

pytauri_plugin_module = ModuleType("pytauri.plugin")
pytauri_plugin_module.Plugin = object

pytauri_webview_module = ModuleType("pytauri.webview")
pytauri_webview_module.WebviewWindow = object

# 只 mock 子模块，让 pytauri/__init__.py 正常执行并把 mock 子模块的属性导入到 pytauri 命名空间
sys.modules["pytauri.ffi"] = pytauri_ffi_module
sys.modules["pytauri.ffi._typing"] = pytauri_ffi_typing_module
sys.modules["pytauri.ipc"] = pytauri_ipc_module
sys.modules["pytauri.plugin"] = pytauri_plugin_module
sys.modules["pytauri.webview"] = pytauri_webview_module

FrontendApi = import_module("ECL.Api").FrontendApi
frontend_module = import_module("ECL.Api.frontend")
ConfigManager = import_module("ECL.Infrastructure").ConfigManager
EventBus = import_module("ECL.Events").EventBus


class FakeAccounts:
    def add_offline(self, username, custom_uuid=None):
        return {"id": "offline-id", "alias": username, "type": "offline", "uuid": "offline-uuid"}


class FakePlugins:
    def on_frontend_ready(self) -> None:
        pass

    def list_plugins(self):
        return []


class FakeAvatars:
    def render_avatar(
        self,
        account_uuid,
        size,
        use_default_skin,
        account_type=None,
        account_id=None,
    ):
        return {"dataUrl": "", "base64": ""}


class FakeInfoCard:
    def get_info_card(self):
        return {}


def _reset_singletons() -> None:
    FrontendApi._instance = None
    FrontendApi._initialized = False
    ConfigManager._instance = None
    ConfigManager._initialized = False
    EventBus._instance = None
    EventBus._initialized = False


def _build_api(tmp_path):
    _reset_singletons()
    launcher = SimpleNamespace(
        app_path=tmp_path,
        data_path=tmp_path / "ECL_data",
        config={"launcher": {"debug": False}},
        debug=False,
        launcher_version="0.1.0",
        launcher_version_type="dev",
    )
    bus = EventBus()
    bus.register("launcher", launcher)
    bus.register("config", ConfigManager(tmp_path / "ECL_data"))
    bus.register("accounts", FakeAccounts())
    bus.register("avatars", FakeAvatars())
    bus.register("info_card", FakeInfoCard())
    bus.register("plugins", FakePlugins())
    return FrontendApi()


def _make_png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (100, 100), color="red").save(buffer, format="PNG")
    return buffer.getvalue()


class _AsyncMockClient:
    def __init__(self, response_chain):
        self._response_chain = list(response_chain)
        self._index = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def stream(self, method, url, **kwargs):
        response = self._response_chain[self._index]
        self._index += 1
        # 模拟 httpx 的 follow_redirects：遇到 3xx 且还有后续响应时返回下一个
        while 300 <= response.status_code < 400 and self._index < len(self._response_chain):
            location = response.headers.get("location")
            if not location:
                break
            response = self._response_chain[self._index]
            self._index += 1
        return _AsyncMockStream(response)


class _AsyncMockStream:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *args):
        return None


class _MockResponse:
    def __init__(self, status_code, content, headers=None, url=None):
        self.status_code = status_code
        self._content = content
        self.headers = httpx.Headers(headers or {})
        self.url = httpx.URL(url or "https://example.com/image.png")

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", self.url)
            raise httpx.HTTPStatusError("mock error", request=request, response=self)

    async def aiter_bytes(self, chunk_size=64 * 1024):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i : i + chunk_size]


def test_normalize_image_url_accepts_http_and_https() -> None:
    assert frontend_module._normalize_image_url("http://example.com/a.png") == "http://example.com/a.png"
    assert frontend_module._normalize_image_url("https://example.com/a.png") == "https://example.com/a.png"


def test_normalize_image_url_rejects_invalid_urls() -> None:
    assert frontend_module._normalize_image_url("ftp://example.com/a.png") is None
    assert frontend_module._normalize_image_url("") is None
    assert frontend_module._normalize_image_url(123) is None
    assert frontend_module._normalize_image_url("not-a-url") is None


def test_normalize_image_url_strips_trailing_punctuation() -> None:
    assert frontend_module._normalize_image_url("https://example.com/a.png,") == "https://example.com/a.png"
    assert frontend_module._normalize_image_url("https://example.com/a.png;\n") == "https://example.com/a.png"
    assert frontend_module._normalize_image_url("  https://example.com/a.png  ") == "https://example.com/a.png"


def test_guess_image_extension_from_content_type() -> None:
    response = _MockResponse(200, b"", headers={"content-type": "image/webp"})
    print("MIME_TO_EXT:", frontend_module._mime_to_ext)
    print("CT:", response.headers.get("content-type"))
    assert frontend_module._guess_image_extension(response, "https://example.com/a") == ".webp"


def test_guess_image_extension_from_content_disposition() -> None:
    response = _MockResponse(200, b"", headers={"content-disposition": 'attachment; filename="bg.PNG"'})
    assert frontend_module._guess_image_extension(response, "https://example.com/a") == ".png"


def test_guess_image_extension_from_final_url() -> None:
    response = _MockResponse(200, b"", url="https://example.com/path/to/photo.webp")
    assert frontend_module._guess_image_extension(response, "https://example.com/path/to/photo.webp") == ".webp"


def test_guess_image_extension_defaults_to_jpg() -> None:
    response = _MockResponse(200, b"", headers={"content-type": "image/jpeg"})
    assert frontend_module._guess_image_extension(response, "https://example.com/a") == ".jpg"


def test_image_save_url_rejects_invalid_url(tmp_path) -> None:
    api = _build_api(tmp_path)

    result = asyncio.run(api.image_save_url({"url": "not-a-url"}))

    assert result["success"] is False
    assert result["errorCode"] == "INVALID_IMAGE_URL"
    _reset_singletons()


def test_image_save_url_follows_redirect_and_returns_data_url(tmp_path, monkeypatch) -> None:
    api = _build_api(tmp_path)
    png_bytes = _make_png_bytes()
    redirect_response = _MockResponse(
        302,
        b"",
        headers={"location": "https://cdn.example.com/final.png"},
        url="https://example.com/redirect",
    )
    final_response = _MockResponse(
        200,
        png_bytes,
        headers={"content-type": "image/png"},
        url="https://cdn.example.com/final.png",
    )
    mock_client = _AsyncMockClient([redirect_response, final_response])
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: mock_client)

    result = asyncio.run(api.image_save_url({"url": "https://example.com/redirect"}))

    assert result["success"] is True
    data = result["data"]
    assert data["url"] == "https://example.com/redirect"
    assert data["dataUrl"].startswith("data:image/png;base64,")
    assert data["base64"]
    _reset_singletons()
