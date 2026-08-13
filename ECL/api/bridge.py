import base64
import functools
import json
import os
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import httpx
from pydantic import ValidationError
from pytauri import EventTarget
from pytauri.ffi import Emitter as _Emitter
from pytauri.ipc import WebviewWindow

from ECL.api.contracts import ApiResponse, failure
from ECL.application import ApplicationContext
from ECL.services.accounts import AccountError
from ECL.services.game import GameServiceError
from ECL.services.maintenance import DebugMaintenanceError
from ECL.services.wardrobe import WardrobeError
from ECL.utils import get_logger

_queued_frontend_events = frozenset({"launcher:error", "launcher:popup"})
_max_pending_frontend_events = 50

_image_mime_map = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}

_ext_to_mime = _image_mime_map
_mime_to_ext = {mime: ext for ext, mime in _image_mime_map.items()}
_mime_to_ext["image/jpeg"] = ".jpg"

_MAX_REMOTE_IMAGE_SIZE = 50 * 1024 * 1024
_REMOTE_IMAGE_TIMEOUT = 30.0

# 图片读取结果内存缓存（LRU）：避免重复读盘与 Base64 编码
_image_cache_max = 32
_image_cache: "OrderedDict[str, str]" = OrderedDict()


def _image_cache_key(file_path: Path) -> str:
    try:
        stat = file_path.stat()
        return f"{file_path}|{stat.st_mtime_ns}|{stat.st_size}"
    except OSError:
        return f"{file_path}|missing"


def _image_cache_get(key: str) -> str | None:
    value = _image_cache.get(key)
    if value is not None:
        _image_cache.move_to_end(key)
    return value


def _image_cache_put(key: str, value: str) -> None:
    _image_cache[key] = value
    _image_cache.move_to_end(key)
    while len(_image_cache) > _image_cache_max:
        _image_cache.popitem(last=False)


_IPC_ERRORS = (
    AccountError,
    WardrobeError,
    GameServiceError,
    DebugMaintenanceError,
    httpx.HTTPError,
    OSError,
    ValueError,
)

_MODAL_ERROR_CODES = frozenset(
    {
        "ACCOUNT_SAVE_FAILED",
        "ECL_CONFIG_WRITE_FAILED",
        "MOD_COPY_FAILED",
        "VERSION_UNINSTALL_FAILED",
        "WARDROBE_FILE_READ_FAILED",
        "WARDROBE_METADATA_INVALID",
    }
)


def _normalize_image_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    url = value.strip().rstrip(",.;:\n\r")
    if not url:
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        return None
    return url


def _extract_filename_from_header(header: str | None) -> str | None:
    if not header:
        return None
    try:
        if "filename*=" in header:
            part = header.split("filename*=")[1].split(";")[0].strip().strip('"')
            if "''" in part:
                encoding, _, name = part.partition("''")
                return unquote(name, encoding=encoding or "utf-8")
        if "filename=" in header:
            part = header.split("filename=")[1].split(";")[0].strip().strip('"')
            return unquote(part)
    except (ValueError, LookupError):
        pass
    return None


def _guess_image_extension(response: httpx.Response, url: str) -> str:
    filename = _extract_filename_from_header(response.headers.get("content-disposition"))
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in _image_mime_map:
            return ext

    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type in _mime_to_ext:
        return _mime_to_ext[content_type]

    parsed = urlsplit(str(response.url))
    ext = Path(unquote(parsed.path)).suffix.lower()
    if ext in _image_mime_map:
        return ext

    return ".jpg"


async def _download_remote_image(url: str) -> tuple[bytes, httpx.Response]:
    async with (
        httpx.AsyncClient(
            follow_redirects=True,
            verify=False,
            timeout=_REMOTE_IMAGE_TIMEOUT,
            headers={"User-Agent": "EuoraCraft-Launcher"},
        ) as client,
        client.stream("GET", url) as response,
    ):
        response.raise_for_status()
        data = bytearray()
        async for chunk in response.aiter_bytes(64 * 1024):
            data.extend(chunk)
            if len(data) > _MAX_REMOTE_IMAGE_SIZE:
                raise ValueError("远程图片超过最大大小限制")
        return bytes(data), response


def _encode_image_bytes(
    image_bytes: bytes,
    ext: str,
) -> tuple[str, str]:
    mime = _ext_to_mime.get(ext, "image/jpeg")
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}", b64


def _open_folder(path: str) -> None:
    target = Path(path).resolve()
    if not target.exists():
        raise FileNotFoundError(f"路径不存在: {target}")
    if sys.platform == "win32":
        os.startfile(str(target))
    elif sys.platform == "darwin":
        subprocess.run(["open", str(target)], check=False)
    else:
        subprocess.run(["xdg-open", str(target)], check=False)


def _make_error_response(exc: Exception, fallback_code: str, events: Any | None = None) -> ApiResponse:
    error_code = getattr(exc, "error_code", fallback_code)
    message = str(exc).strip() or type(exc).__name__
    is_unexpected_file_error = isinstance(exc, OSError) and not isinstance(exc, FileNotFoundError)
    if error_code in _MODAL_ERROR_CODES or is_unexpected_file_error:
        error_id = uuid4().hex
        title = "启动器无法完成本地数据操作"
        payload = {"error_id": error_id, "title": title, "message": message}
        if events is not None:
            events.emit("launcher:error", payload)
        return failure(message, error_code, presentation="modal", error_id=error_id, title=title)
    return failure(message, error_code)


def _make_unexpected_error_response(state: Any, operation: str) -> ApiResponse:
    error_id = uuid4().hex
    message = "启动器执行操作时发生内部错误，请导出日志以便排查"
    title = "启动器发生内部错误"
    state.logger.exception("%s 发生未预期异常，错误编号: %s", operation, error_id)
    state.events.emit("launcher:error", {"error_id": error_id, "title": title, "message": message})
    return failure(
        message,
        "INTERNAL_ERROR",
        presentation="modal",
        error_id=error_id,
        title=title,
    )


def guard_ipc_handler(state: Any, operation: str, handler: Any) -> Any:
    """
    为正式 IPC 命令补齐统一的异常边界与严重错误呈现元数据。

    :param state: 拥有日志与应用事件总线的前端 API 门面
    :param operation: 注册到 PyTauri 的稳定命令名
    :param handler: 原始异步命令处理器
    :return: 捕获所有异常并返回 ``ApiResponse`` 的异步处理器
    """

    @functools.wraps(handler)
    async def guarded(*args: Any, **kwargs: Any) -> ApiResponse:
        try:
            return await handler(*args, **kwargs)
        except _IPC_ERRORS as exc:
            if isinstance(exc, httpx.HTTPError):
                state.logger.warning("%s 远程请求失败: %s", operation, exc)
            else:
                state.logger.exception("%s 执行失败", operation)
            return _make_error_response(exc, "INTERNAL_ERROR", state.events)
        except Exception:
            return _make_unexpected_error_response(state, operation)

    return guarded


def _ipc_handler(fallback_code: str = "INTERNAL_ERROR"):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            try:
                return await func(self, *args, **kwargs)
            except _IPC_ERRORS as exc:
                if isinstance(exc, httpx.HTTPError):
                    self.logger.warning("%s 远程请求失败: %s", func.__name__, exc)
                else:
                    self.logger.exception("%s 执行失败", func.__name__)
                return _make_error_response(exc, fallback_code, self.events)
            except Exception:
                return _make_unexpected_error_response(self, func.__name__)

        return wrapper

    return decorator


class _FrontendState:
    def __init__(self, context: ApplicationContext):
        self.logger = get_logger("FrontendApi")
        self.events = context.events
        self.launcher = context.state
        self.config = context.config
        self.accounts = context.accounts
        self.wardrobe = context.wardrobe
        # HTTP 客户端由 ApplicationContext 统一关闭，API 处理器只能借用。
        self.http = context.http
        self.info_card = context.info_card
        self.game = context.game
        self.plugins = context.plugins
        self.app_path: Path = self.launcher.app_path
        self.data_path: Path = self.launcher.data_path
        self._webview: WebviewWindow | None = None
        self._pending_frontend_events: list[tuple[str, Any]] = []
        # 严重错误在收到前端确认前保留一份内存副本。Tauri 事件用于即时呈现，IPC
        # 拉取用于恢复工作线程事件丢失；两条链路由同一 error_id 在前端去重。
        self._pending_error_presentations: dict[str, dict[str, Any]] = {}
        self._frontend_event_lock = RLock()

    @staticmethod
    def _invalid_request(exc: ValidationError) -> ApiResponse:
        """
        将 Pydantic 边界校验错误转换为稳定 IPC 响应。

        :param exc: 请求模型产生的校验异常
        :return: 使用 ``INVALID_REQUEST`` 错误码的失败响应
        """
        message = exc.errors(include_url=False)[0].get("msg", "请求参数无效")
        return failure(str(message), "INVALID_REQUEST")

    def _queue_frontend_event(self, event: str, payload: Any) -> None:
        if event not in _queued_frontend_events:
            return
        with self._frontend_event_lock:
            self._pending_frontend_events.append((event, payload))
            if len(self._pending_frontend_events) > _max_pending_frontend_events:
                self._pending_frontend_events.pop(0)

    def emit_to_frontend(self, event: str, payload: Any) -> None:
        """
        向前端发送事件。

        :param event: 事件名称，如 ``config:updated``
        :param payload: 事件或请求携带的数据
        """
        if self._webview is None:
            self._queue_frontend_event(event, payload)
            return
        webview = self._webview
        serialized = json.dumps(payload, ensure_ascii=False)

        def emit_on_main_thread() -> None:
            try:
                _Emitter.emit_str_to(webview, EventTarget.Any(), event, serialized)
            except (OSError, TypeError, ValueError, RuntimeError):
                self.logger.exception("向前端推送事件失败: %s", event)
                self._queue_frontend_event(event, payload)

        try:
            # 游戏退出和崩溃分析回调运行在工作线程。WebView 发射必须切回 Tauri
            # 主线程，否则事件会被排队在一个已经完成 frontend_ready 的会话中。
            webview.run_on_main_thread(emit_on_main_thread)
        except (OSError, TypeError, ValueError, RuntimeError):
            self.logger.exception("调度前端事件失败: %s", event)
            self._queue_frontend_event(event, payload)

    def emit_popup_to_frontend(self, payload: dict[str, Any]) -> None:
        """
        发送弹窗事件。

        :param payload: 事件或请求携带的数据
        """
        if isinstance(payload, dict):
            self.emit_to_frontend("launcher:popup", payload)

    def emit_error_to_frontend(self, payload: dict[str, Any]) -> None:
        """
        发送错误事件。

        :param payload: 事件或请求携带的数据
        """
        if not isinstance(payload, dict):
            return
        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            return
        normalized = {
            "error_id": str(payload.get("error_id") or uuid4().hex),
            "title": str(payload.get("title") or "启动器发生错误"),
            "message": message.strip(),
        }
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            normalized["detail"] = detail.strip()
        if payload.get("kind") == "game_crash" and isinstance(payload.get("crash"), dict):
            normalized["kind"] = "game_crash"
            normalized["crash"] = payload["crash"]
        with self._frontend_event_lock:
            self._pending_error_presentations[normalized["error_id"]] = normalized
            while len(self._pending_error_presentations) > _max_pending_frontend_events:
                oldest = next(iter(self._pending_error_presentations))
                self._pending_error_presentations.pop(oldest, None)
        self.emit_to_frontend("launcher:error", normalized)

    def focus_window(self) -> bool:
        """
        激活启动器窗口。

        """
        webview = self._webview
        if webview is None:
            return False

        def focus() -> None:
            webview.unminimize()
            webview.show()
            webview.set_focus()

        try:
            webview.run_on_main_thread(focus)
        except (OSError, RuntimeError):
            self.logger.exception("激活启动器窗口失败")
            return False
        return True

    def _flush_pending_frontend_events(self) -> None:
        with self._frontend_event_lock:
            pending_events = self._pending_frontend_events
            self._pending_frontend_events = []
        for event, payload in pending_events:
            self.emit_to_frontend(event, payload)

    def _get_effective_config(self) -> dict[str, Any]:
        config = dict(self.config.get_config())
        launcher_config = dict(config.get("launcher") or {})
        runtime_config = (self.launcher.config or {}).get("launcher") or {}
        launcher_config.update(runtime_config)
        launcher_config["debug"] = bool(self.launcher.debug)
        launcher_config["version"] = self.launcher.launcher_version or ""
        launcher_config["version_type"] = self.launcher.launcher_version_type or "beta"
        config["launcher"] = launcher_config
        return config

    @staticmethod
    def _normalize_authlib_server_url(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        server_url = value.strip()
        if not server_url or " " in server_url:
            return None
        if "://" not in server_url:
            server_url = f"https://{server_url}"
        try:
            parsed = urlsplit(server_url)
        except ValueError:
            return None
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        return server_url

    def _get_authlib_servers(self) -> list[dict[str, str]]:
        authlib_config = self.config.get_config("authlib") or {}
        stored_servers = authlib_config.get("servers") or []
        servers: list[dict[str, str]] = []
        for item in stored_servers:
            raw_url = item.get("url") if isinstance(item, dict) else item
            url = self._normalize_authlib_server_url(raw_url)
            if not url or any(server["url"] == url for server in servers):
                continue
            email = item.get("email") if isinstance(item, dict) else ""
            servers.append({"url": url, "email": email if isinstance(email, str) else ""})
        return servers

    def _remember_authlib_login(self, server_url: str, email: str) -> None:
        servers = [server for server in self._get_authlib_servers() if server["url"] != server_url]
        servers.insert(0, {"url": server_url, "email": email})
        authlib_config = self.config.get_config("authlib") or {}
        authlib_config["servers"] = servers[:20]
        self.config.save_config("authlib", authlib_config)

    def _game_runtime_options(self, body: dict[str, Any]) -> dict[str, Any]:
        config = self._get_effective_config()
        game_config = config.get("game") or {}
        download_config = config.get("download") or {}
        minecraft_paths = game_config.get("minecraft_paths") or []
        first_path = None
        if minecraft_paths:
            first_item = minecraft_paths[0]
            first_path = first_item.get("path") if isinstance(first_item, dict) else first_item
        java_path = body.get("java_path")
        if java_path is None and not game_config.get("java_auto", True):
            java_path = game_config.get("java_path") or None
        return {
            "game_path": body.get("game_path") or game_config.get("last_install_path") or first_path,
            "source": download_config.get("mirror_source") or "official",
            "java_path": java_path,
            "memory": body.get("memory") if body.get("memory") is not None else game_config.get("memory_size", 4096),
            "width": body.get("width") if body.get("width") is not None else game_config.get("game_width", 854),
            "height": body.get("height") if body.get("height") is not None else game_config.get("game_height", 480),
            "jvm_args": body.get("jvm_args") if body.get("jvm_args") is not None else game_config.get("jvm_args", []),
            "game_args": body.get("game_args") or [],
            "version_isolation": bool(body.get("version_isolation", False)),
        }

    async def frontend_ready(self, body: dict[str, Any], webview_window: WebviewWindow) -> dict[str, Any]:
        """
        处理前端就绪。

        :param body: 经过边界校验的 IPC 请求数据
        :param webview_window: 前端 WebView 窗口实例
        """
        self._webview = webview_window
        webview_window.show()
        self._flush_pending_frontend_events()
        self.plugins.on_frontend_ready()
        if bool(self.launcher.debug):
            self.emit_popup_to_frontend(
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
            )
        self.logger.info("前端加载完成，已显示主窗口")
        return {"success": True}
