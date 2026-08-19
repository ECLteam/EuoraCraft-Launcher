import asyncio
import base64
import functools
import json
import os
import subprocess
import sys
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
from ECL.api.models import (
    DebugProcessSpawnRequest,
    FrontendLogRequest,
    ProcessInputRequest,
    ProcessStopRequest,
)
from ECL.application import ApplicationContext
from ECL.game import AuthException, NetException
from ECL.services.accounts import AccountError
from ECL.services.game import GameServiceError
from ECL.services.maintenance import DebugMaintenanceError
from ECL.services.wardrobe import WardrobeError
from ECL.utils import atomic_write_text, get_logger
from ECL.utils.config import default_config
from ECL.utils.logging import get_frontend_log_history

_queued_frontend_events = frozenset(
    {
        "launcher:error",
        "launcher:popup",
        "launcher:log",
        "game:instances_changed",
        "process:instance_log",
        "process:instances_changed",
    }
)
_max_pending_frontend_events = 50

_image_mime_map = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}

_mime_to_ext = {mime: ext for ext, mime in _image_mime_map.items()}
_mime_to_ext["image/jpeg"] = ".jpg"

_MAX_REMOTE_IMAGE_SIZE = 50 * 1024 * 1024
_REMOTE_IMAGE_TIMEOUT = 15.0
_REMOTE_IMAGE_CHUNK_BYTES = 64 * 1024

# 图片读取结果内存缓存（LRU）：避免重复读盘与 Base64 编码。缓存键包含文件
# 最后修改时间与大小，文件变化后自然失效，与先前的显式键行为一致。
_image_cache_max = 32

# 游戏运行时参数表：调用方 body 显式值优先，缺失时回退到游戏配置的对应键。
_RUNTIME_OPTION_FIELDS = (
    # (结果字段, body 键, 配置取值函数)
    ("memory", "memory", lambda c: c.get("memory_size", default_config["game"]["memory_size"])),
    ("width", "width", lambda c: c.get("game_width", default_config["game"]["game_width"])),
    ("height", "height", lambda c: c.get("game_height", default_config["game"]["game_height"])),
    ("jvm_args", "jvm_args", lambda c: c.get("jvm_args", [])),
)


@functools.lru_cache(maxsize=_image_cache_max)
def _read_image_data_url(file_path: Path, mtime_ns: int, size: int) -> tuple[str, str, int]:
    """
    读取图片并编码为 Data URL（LRU 缓存），返回 Data URL、MIME 与 Base64 长度。

    :param file_path: 图片文件路径
    :param mtime_ns: 文件最后修改时间（纳秒），参与缓存键
    :param size: 文件大小（字节），参与缓存键
    :return: ``(data_url, mime, base64_len)`` 三元组
    """
    ext = file_path.suffix.lower() or ".png"
    data_url, b64 = _encode_image_bytes(file_path.read_bytes(), ext)
    return data_url, _image_mime_map.get(ext, "image/jpeg"), len(b64)


_IPC_ERRORS = (
    AccountError,
    WardrobeError,
    GameServiceError,
    DebugMaintenanceError,
    AuthException,
    NetException,
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

# 弹窗展现面向用户的友好文案，原始技术细节另有 detail 字段承载，避免直接暴露给用户。
_MODAL_ERROR_MESSAGES = {
    "ACCOUNT_SAVE_FAILED": "账号数据保存失败，请重试。若问题持续，请导出日志以便排查。",
    "ECL_CONFIG_WRITE_FAILED": "配置保存失败，请重试。若问题持续，请导出日志以便排查。",
    "MOD_COPY_FAILED": "模组文件复制失败，请重试。若问题持续，请导出日志以便排查。",
    "VERSION_UNINSTALL_FAILED": "版本卸载失败，请检查文件是否被占用后再重试。",
    "WARDROBE_FILE_READ_FAILED": "衣柜数据读取失败，请重试。若问题持续，请导出日志以便排查。",
    "WARDROBE_METADATA_INVALID": "衣柜数据格式异常，请重试。若问题持续，请导出日志以便排查。",
}

_FILE_ERROR_MESSAGE = "启动器执行本地文件操作时遇到问题，请关闭后重试。若问题持续，请导出日志以便排查。"


def _is_http_url(url: str, *, scheme_lower: bool = False) -> bool:
    """
    校验 URL 是否为带主机的 HTTP(S) 地址。

    :param url: 待校验的完整 URL
    :param scheme_lower: 是否将协议比较小写化后再判断
    :return: 合法时返回 ``True``
    """
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    scheme = parsed.scheme.lower() if scheme_lower else parsed.scheme
    return scheme in ("http", "https") and bool(parsed.hostname)


def _normalize_image_url(value: Any) -> str | None:
    """规整远程图片地址，校验 HTTP(S) 协议与主机并去除首尾标点。"""
    if not isinstance(value, str):
        return None
    url = value.strip().rstrip(",.;:\n\r")
    if not url:
        return None
    return url if _is_http_url(url, scheme_lower=True) else None


def _extract_filename_from_header(header: str | None) -> str | None:
    """从 Content-Disposition 响应头解析文件名，兼容 filename* 与 filename 两种格式。"""
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
    """按响应头文件名、Content-Type 与 URL 后缀推断图片扩展名，未知时回退为 .jpg。"""
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
    """使用独立客户端流式下载远程图片，并限制响应大小。"""
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
        async for chunk in response.aiter_bytes(_REMOTE_IMAGE_CHUNK_BYTES):
            data.extend(chunk)
            if len(data) > _MAX_REMOTE_IMAGE_SIZE:
                raise ValueError("远程图片超过最大大小限制")
        return bytes(data), response


def _encode_image_bytes(
    image_bytes: bytes,
    ext: str,
) -> tuple[str, str]:
    """将图片字节按扩展名编码为 Data URL 与 Base64 数据。"""
    mime = _image_mime_map.get(ext, "image/jpeg")
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}", b64


def _open_folder(path: str) -> None:
    """使用操作系统默认方式在文件管理器中打开指定路径。"""
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
    """根据异常与错误码构造失败响应，严重错误附带弹窗元数据并上报事件。"""
    error_code = getattr(exc, "error_code", fallback_code)
    raw_message = str(exc).strip() or type(exc).__name__
    is_unexpected_file_error = isinstance(exc, OSError) and not isinstance(exc, FileNotFoundError)
    if error_code in _MODAL_ERROR_CODES or is_unexpected_file_error:
        error_id = uuid4().hex
        title = "启动器无法完成本地数据操作"
        message = _FILE_ERROR_MESSAGE if is_unexpected_file_error else _MODAL_ERROR_MESSAGES.get(error_code, _FILE_ERROR_MESSAGE)
        payload = {"error_id": error_id, "title": title, "message": message, "detail": raw_message}
        if events is not None:
            events.emit("launcher:error", payload)
        return failure(message, error_code, presentation="modal", error_id=error_id, title=title, detail=raw_message)
    return failure(raw_message, error_code)


def _make_unexpected_error_response(state: Any, operation: str, exc: Exception) -> ApiResponse:
    """为未预期异常构造严重错误响应，记录堆栈并上报错误事件。

    异常原文以 detail 字段随弹窗呈现，便于用户直接看到后端失败原因。
    """
    error_id = uuid4().hex
    message = "启动器执行操作时发生内部错误，请导出日志以便排查"
    title = "启动器发生内部错误"
    raw_message = str(exc).strip() or type(exc).__name__
    state.logger.exception("%s 发生未预期异常，错误编号: %s", operation, error_id)
    state.events.emit("launcher:error", {"error_id": error_id, "title": title, "message": message, "detail": raw_message})
    return failure(
        message,
        "INTERNAL_ERROR",
        presentation="modal",
        error_id=error_id,
        title=title,
        detail=raw_message,
    )


def _make_timeout_response(state: Any, operation: str) -> ApiResponse:
    """为操作超时构造失败响应，提示用户检查网络。"""
    state.logger.warning("%s 操作超时，已取消", operation)
    return failure("操作超时，请检查网络后重试", "OPERATION_TIMEOUT")


async def _guarded_call(state: Any, operation: str, fallback_code: str, awaitable: Any, timeout: float | None = None) -> Any:
    """
    统一的 IPC 异常边界：捕获已知错误与未知异常并转换为响应。

    :param state: 拥有日志与应用事件总线的前端 API 门面
    :param operation: 当前操作的名称，用于日志与错误编号
    :param fallback_code: 已知错误映射失败时的兜底错误码
    :param awaitable: 已构建的协程对象
    :param timeout: 可选的总操作超时秒数，超时后取消任务
    :return: ``ApiResponse``
    """
    try:
        if timeout is not None:
            return await asyncio.wait_for(awaitable, timeout)
        return await awaitable
    except TimeoutError:
        return _make_timeout_response(state, operation)
    except _IPC_ERRORS as exc:
        if isinstance(exc, httpx.HTTPError):
            state.logger.warning("%s 远程请求失败: %s", operation, exc)
        else:
            state.logger.exception("%s 执行失败", operation)
        return _make_error_response(exc, fallback_code, state.events)
    except Exception as exc:
        return _make_unexpected_error_response(state, operation, exc)


def guard_ipc_handler(state: Any, operation: str, handler: Any, timeout: float | None = None) -> Any:
    """
    为正式 IPC 命令补齐统一的异常边界与严重错误呈现元数据。

    :param state: 拥有日志与应用事件总线的前端 API 门面
    :param operation: 注册到 PyTauri 的稳定命令名
    :param handler: 原始异步命令处理器
    :param timeout: 可选的总操作超时秒数，超时后取消任务
    :return: 捕获所有异常并返回 ``ApiResponse`` 的异步处理器
    """
    @functools.wraps(handler)
    async def guarded(*args: Any, **kwargs: Any) -> ApiResponse:
        return await _guarded_call(state, operation, "INTERNAL_ERROR", handler(*args, **kwargs), timeout)

    return guarded


def _ipc_handler(fallback_code: str = "INTERNAL_ERROR", timeout: float | None = None):
    """装饰器，为 IPC 命令处理器补齐统一异常边界与错误呈现元数据。"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            return await _guarded_call(self, func.__name__, fallback_code, func(self, *args, **kwargs), timeout)

        return wrapper

    return decorator


def _validate_body(model: Any, body: dict[str, Any]) -> tuple[Any, ApiResponse | None]:
    """
    将 IPC 请求体校验为 Pydantic 模型，失败时返回稳定的校验错误响应。

    :param model: 请求模型类型
    :param body: IPC 请求数据
    :return: ``(模型实例或 None, 校验失败响应或 None)``
    """
    try:
        return model.model_validate(body), None
    except ValidationError as exc:
        return None, _FrontendState._invalid_request(exc)


class _FrontendState:
    """前端 IPC 处理器的共享状态门面，聚合日志、应用事件与各服务句柄。"""

    def __init__(self, context: ApplicationContext):
        """收集应用上下文中的日志、事件与各服务句柄。"""
        self.logger = get_logger("FrontendApi")
        self.events = context.events
        self.launcher = context.state
        self.config = context.config
        self.accounts = context.accounts
        self.wardrobe = context.wardrobe
        self.http = context.http
        self.info_card = context.info_card
        self.connector = context.connector
        self.game = context.game
        self.plugins = context.plugins
        self.processes = context.processes
        self.app_path: Path = self.launcher.app_path
        self.data_path: Path = self.launcher.data_path
        self._webview: WebviewWindow | None = None
        self._pending_frontend_events: list[tuple[str, Any]] = []
        self._pending_error_presentations: dict[str, dict[str, Any]] = {}
        self._frontend_event_lock = RLock()
        self.is_dev_mode_tips = False
        self.is_dev_mode_no_client_id_tips = False
        self.is_dev_mode_no_curseforge_key_tips =False

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
        """将需排队的前端事件追加到待发送缓冲，超过上限时丢弃最早的事件。"""
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
            # 前端窗口已关闭时停止发送，避免关闭期间反复报错
            self._webview = None
            self.logger.warning("前端已关闭，停止推送事件: %s", event)

    def emit_popup_to_frontend(self, payload: dict[str, Any]) -> None:
        """
        向前端发送弹窗事件。

        :param payload: 待呈现的弹窗内容
        """
        if isinstance(payload, dict):
            self.emit_to_frontend("launcher:popup", payload)

    def emit_error_to_frontend(self, payload: dict[str, Any]) -> None:
        """
        规范化严重错误并向前端推送，同时为其保留待确认呈现的内存副本。

        :param payload: 包含错误信息的原始数据
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
        """在前端主线程激活并置顶启动器窗口。"""
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
        """将排队的前端事件全部转发给已就绪的 WebView。"""
        with self._frontend_event_lock:
            pending_events = self._pending_frontend_events
            self._pending_frontend_events = []
        for event, payload in pending_events:
            self.emit_to_frontend(event, payload)

    def _get_effective_config(self) -> dict[str, Any]:
        """合并持久化配置与运行时覆盖，构造前端可见的有效配置。"""
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
        """规整外置登录服务器地址，缺少协议时补全为 HTTPS。"""
        if not isinstance(value, str):
            return None
        server_url = value.strip()
        if not server_url or " " in server_url:
            return None
        if "://" not in server_url:
            server_url = f"https://{server_url}"
        return server_url if _is_http_url(server_url) else None

    @property
    def _authlib_servers_file(self) -> Path:
        return Path.home() / ".ECL" / "accounts" / "authlib" / "servers.json"

    def _load_authlib_servers(self) -> list[dict[str, str]]:
        """从磁盘读取外置登录服务器历史。"""
        file = self._authlib_servers_file
        try:
            if file.is_file():
                raw = json.loads(file.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    return [
                        {"url": str(item.get("url") or ""), "email": str(item.get("email") or "")}
                        for item in raw
                        if isinstance(item, dict)
                    ]
        except (OSError, ValueError, TypeError):
            self.logger.warning("读取外置登录服务器历史失败，使用空列表: %s", file)
        return []

    def _save_authlib_servers(self, servers: list[dict[str, str]]) -> None:
        """原子写入外置登录服务器历史。"""
        file = self._authlib_servers_file
        file.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(file, json.dumps(servers, ensure_ascii=False, indent=2))

    def _get_authlib_servers(self) -> list[dict[str, str]]:
        """规整并去重外置登录服务器历史。"""
        servers: list[dict[str, str]] = []
        for item in self._load_authlib_servers():
            url = self._normalize_authlib_server_url(item.get("url"))
            if not url or any(server["url"] == url for server in servers):
                continue
            email = item.get("email") if isinstance(item, dict) else ""
            servers.append({"url": url, "email": email if isinstance(email, str) else ""})
        return servers

    def _remember_authlib_login(self, server_url: str, email: str) -> None:
        """将一次成功登录的外置服务器置于历史队首并保存。"""
        servers = [server for server in self._get_authlib_servers() if server["url"] != server_url]
        servers.insert(0, {"url": server_url, "email": email})
        self._save_authlib_servers(servers[:20])

    async def frontend_log(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        记录前端通过 IPC 上报的运行日志，供统一归档排查。

        前端 console 输出会被拦截后转发到这里，写入与后端一致的文件日志。

        :param body: 符合 ``FrontendLogRequest`` 的日志数据
        :return: 空的成功响应
        """
        request, invalid = _validate_body(FrontendLogRequest, body)
        if invalid is not None:
            return invalid
        message = request.message
        if request.detail:
            message = f"{message}\n{request.detail}"
        if request.logger:
            message = f"[{request.logger}] {message}"
        log_level = request.level.value
        if log_level == "warn":
            log_level = "warning"
        log_method = getattr(self.logger, log_level)
        log_method("[Frontend] %s", message)
        return {"success": True}

    async def logs_get_history(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        返回最近缓存的启动器日志，供前端日志终端打开时补全历史。

        :param body: 空请求数据
        :return: 包含 ``logs`` 列表的成功响应
        """
        return {"success": True, "data": {"logs": get_frontend_log_history()}}

    async def process_instances(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        返回注册表内登记的子进程实例列表。

        :param body: 必须为空的请求对象
        :return: 包含 ``instances`` 列表的成功响应
        """
        if body:
            return failure("process_instances 不接受请求参数", "INVALID_REQUEST")
        return {"success": True, "data": {"instances": self.processes.list()}}

    @_ipc_handler("PROCESS_INPUT_FAILED")
    async def process_input(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        向指定子进程实例写入一行标准输入。

        :param body: 符合 ``ProcessInputRequest`` 的请求数据
        :return: 是否成功写入的标准输入标识
        """
        request, invalid = _validate_body(ProcessInputRequest, body)
        if invalid is not None:
            return invalid
        return {"success": True, "data": {"sent": self.processes.send_stdin(request.instance_id, request.data)}}

    @_ipc_handler("PROCESS_STOP_FAILED")
    async def process_stop(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        停止指定子进程实例。

        :param body: 符合 ``ProcessStopRequest`` 的请求数据
        :return: 进程是否已结束的成功响应
        """
        request, invalid = _validate_body(ProcessStopRequest, body)
        if invalid is not None:
            return invalid
        return {"success": True, "data": {"stopped": self.processes.stop(request.instance_id)}}

    async def debug_process_spawn(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        在调试模式下启动一个子进程实例，供开发自测实例终端。

        :param body: 符合 ``DebugProcessSpawnRequest`` 的请求数据
        :return: 包含 ``instanceId`` 的成功响应
        """
        if not self.launcher.debug:
            return failure("调试命令仅在调试模式下可用", "INVALID_STATE")
        request, invalid = _validate_body(DebugProcessSpawnRequest, body)
        if invalid is not None:
            return invalid
        try:
            instance_id = self.processes.spawn(
                request.name,
                request.type,
                request.args,
                cwd=request.cwd,
                stdin=request.stdin,
            )
        except ValueError as exc:
            return failure(str(exc), "INVALID_REQUEST")
        return {"success": True, "data": {"instanceId": instance_id}}

    def _game_runtime_options(self, body: dict[str, Any]) -> dict[str, Any]:
        """汇总启动游戏所需的运行时参数，优先使用调用方显式指定的值。"""
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
        options: dict[str, Any] = {
            "game_path": body.get("game_path") or game_config.get("last_install_path") or first_path,
            "source": download_config.get("mirror_source") or "official",
            "java_path": java_path,
        }
        for field, body_key, config_lookup in _RUNTIME_OPTION_FIELDS:
            value = body.get(body_key)
            if value is None:
                value = config_lookup(game_config)
            options[field] = value
        options["game_args"] = body.get("game_args") or []
        options["version_isolation"] = bool(body.get("version_isolation", False))
        return options

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
        if bool(self.launcher.debug) and (self.is_dev_mode_tips is False):
            self.is_dev_mode_tips = True
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
        if (not self.game.curseforge_available()) and (self.is_dev_mode_no_curseforge_key_tips is False):
            self.is_dev_mode_no_curseforge_key_tips = True
            self.emit_popup_to_frontend(
                {
                    "id": "curseforge-key-required",
                    "title": "CurseForge API Key 未配置",
                    "content": (
                        "在线模组搜索的 **CurseForge** 来源需要配置 API Key，未配置时该来源会被禁用。\n\n"
                        "请在启动器根目录的 `.env` 文件中添加 `CURSEFORGE_API_KEY=你的密钥`，"
                        "或设置同名系统环境变量后重启启动器。"
                    ),
                    "level": "warning",
                    "dismissible": True,
                    "cacheable": True,
                }
            )
        if (not self.accounts.microsoft_login_config().get("available")) and (self.is_dev_mode_no_client_id_tips is False):
            self.is_dev_mode_no_client_id_tips = True
            self.emit_popup_to_frontend(
                {
                    "id": "microsoft-client-id-required",
                    "title": "Microsoft client_id 未配置",
                    "content": (
                        "正版（Microsoft）登录需要配置 **client_id**，未配置时无法使用正版登录。\n\n"
                        "请在启动器根目录的 `.env` 文件中添加 `MICROSOFT_CLIENT_ID=你的应用ID`，"
                        "或设置同名系统环境变量后重启启动器。"
                    ),
                    "level": "warning",
                    "dismissible": True,
                    "cacheable": True,
                }
            )
        self.logger.info("前端加载完成")
        return {"success": True}
