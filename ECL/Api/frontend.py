import base64
import functools
import json
import os
import subprocess
import sys
import webbrowser
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import httpx
import psutil
from anyio import to_thread
from PIL import Image
from pytauri import EventTarget
from pytauri.ffi import Emitter as _Emitter
from pytauri.ipc import WebviewWindow
from pytauri_plugins.dialog import DialogExt

from ECL.Api.contracts import ApiResponse, failure, success
from ECL.Events import EventBus
from ECL.Infrastructure import get_logger
from ECL.Plugin.framework import PluginCommandError
from ECL.Services.accounts import AccountError
from ECL.Services.avatars import AvatarError
from ECL.Services.game import GameServiceError
from ECL.Services.maintenance import DebugMaintenanceError, schedule_debug_maintenance

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
_IPC_ERRORS = (
    AccountError,
    AvatarError,
    GameServiceError,
    DebugMaintenanceError,
    httpx.HTTPError,
    OSError,
    ValueError,
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
    image_bytes: bytes, ext: str, max_size: tuple[int, int] | None = (1920, 1080)
) -> tuple[str, str]:
    with Image.open(BytesIO(image_bytes)) as img:
        if max_size:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
        if ext in (".jpg", ".jpeg") and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        mime = _ext_to_mime.get(ext, "image/jpeg")
        buffer = BytesIO()
        if ext == ".png":
            img.save(buffer, format="PNG", optimize=True)
        elif ext == ".webp":
            img.save(buffer, format="WEBP", quality=85)
        else:
            img.save(buffer, format="JPEG", quality=85)
        b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
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


def _make_error_response(exc: Exception, fallback_code: str) -> ApiResponse:
    error_code = getattr(exc, "error_code", fallback_code)
    message = str(exc).strip() or type(exc).__name__
    return failure(message, error_code)


def _ipc_handler(fallback_code: str = "INTERNAL_ERROR"):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            try:
                return await func(self, *args, **kwargs)
            except _IPC_ERRORS as exc:
                self.logger.exception("%s 执行失败", func.__name__)
                return _make_error_response(exc, fallback_code)

        return wrapper

    return decorator


class FrontendApi:
    """EuoraCraft Launcher 前端 IPC API"""

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.logger = get_logger("FrontendApi")
        bus = EventBus()
        self.launcher = bus["launcher"]
        self.config = bus["config"]
        self.accounts = bus["accounts"]
        self.avatars = bus["avatars"]
        self.info_card = bus["info_card"]
        self.game = bus.get("game")
        self.plugins = bus["plugins"]
        self.app_path: Path = self.launcher.app_path
        self.data_path: Path = self.launcher.data_path
        self._webview: WebviewWindow | None = None
        self._pending_frontend_events: list[tuple[str, Any]] = []
        self._initialized = True

    def _queue_frontend_event(self, event: str, payload: Any) -> None:
        if event not in _queued_frontend_events:
            return
        self._pending_frontend_events.append((event, payload))
        if len(self._pending_frontend_events) > _max_pending_frontend_events:
            self._pending_frontend_events.pop(0)

    def emit_to_frontend(self, event: str, payload: Any) -> None:
        """向前端发送事件。"""
        if self._webview is None:
            self._queue_frontend_event(event, payload)
            return
        try:
            _Emitter.emit_str_to(self._webview, EventTarget.Any(), event, json.dumps(payload, ensure_ascii=False))
        except (OSError, TypeError, ValueError, RuntimeError):
            self.logger.exception("向前端推送事件失败: %s", event)
            self._queue_frontend_event(event, payload)

    def emit_popup_to_frontend(self, payload: dict[str, Any]) -> None:
        """发送弹窗事件。"""
        if isinstance(payload, dict):
            self.emit_to_frontend("launcher:popup", payload)

    def emit_error_to_frontend(self, payload: dict[str, Any]) -> None:
        """发送错误事件。"""
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
        self.emit_to_frontend("launcher:error", normalized)

    def focus_window(self) -> bool:
        """激活启动器窗口。"""
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
        """处理前端就绪。"""
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

    # 启动器

    async def ping(self, body: dict[str, Any]) -> dict[str, Any]:
        """检查连接。"""
        return {"success": True, "data": {"status": "ok", "message": "正常"}}

    @_ipc_handler("SYSTEM_MEMORY_FAILED")
    async def system_memory(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取内存信息。"""
        mem = psutil.virtual_memory()
        to_mb = 1 / (1024 * 1024)
        return {
            "success": True,
            "data": {
                "totalMb": round(mem.total * to_mb),
                "usedMb": round(mem.used * to_mb),
                "freeMb": round(mem.available * to_mb),
                "percentUsed": mem.percent,
            },
        }

    @_ipc_handler("JAVA_SCAN_FAILED")
    async def java_scan(self, body: dict[str, Any]) -> dict[str, Any]:
        """扫描可用 Java。"""
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        game_config = self._get_effective_config().get("game") or {}
        selected_java = game_config.get("java_path")
        user_paths = [selected_java] if isinstance(selected_java, str) and selected_java.strip() else []
        installations = await to_thread.run_sync(self.game.scan_java, user_paths)
        return {"success": True, "data": installations}

    # 配置

    async def config_get(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取配置。"""
        section = body.get("section")
        if not isinstance(section, str) or not section.strip():
            return {"success": False, "message": "配置分区名称不能为空", "errorCode": "INVALID_CONFIG_SECTION"}
        return {"success": True, "data": self._get_effective_config().get(section)}

    async def config_set(self, body: dict[str, Any]) -> dict[str, Any]:
        """保存配置。"""
        section = body.get("section")
        if not isinstance(section, str) or not section.strip():
            return {"success": False, "message": "配置分区名称不能为空", "errorCode": "INVALID_CONFIG_SECTION"}
        if "data" not in body:
            return {"success": False, "message": "缺少需要保存的配置数据", "errorCode": "MISSING_CONFIG_DATA"}
        self.config.save_config(section, body["data"])
        return {"success": True}

    async def config_list(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取配置分区。"""
        return {"success": True, "data": self.config.list_sections()}

    async def config_get_all(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取全部配置。"""
        return {"success": True, "data": self._get_effective_config()}

    async def config_get_many(self, body: dict[str, Any]) -> dict[str, Any]:
        """批量获取配置。"""
        sections = body.get("sections")
        if not isinstance(sections, list) or not all(
            isinstance(section, str) and section.strip() for section in sections
        ):
            return {"success": False, "message": "配置分区列表格式无效", "errorCode": "INVALID_CONFIG_SECTIONS"}
        config = self._get_effective_config()
        return {"success": True, "data": {section: config.get(section) for section in dict.fromkeys(sections)}}

    # 游戏版本

    @_ipc_handler("VERSION_CATALOG_FAILED")
    async def minecraft_versions(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取 Minecraft 版本。"""
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        source = (self._get_effective_config().get("download") or {}).get("mirror_source")
        version_list = await to_thread.run_sync(self.game.minecraft_versions, body.get("filter_type"), source)
        return {"success": True, "data": version_list}

    @_ipc_handler("VERSION_CATALOG_FAILED")
    async def minecraft_versions_classified(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取分类后的 Minecraft 版本。"""
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        source = (self._get_effective_config().get("download") or {}).get("mirror_source")
        version_catalog = await to_thread.run_sync(self.game.minecraft_versions_classified, source)
        return {"success": True, "data": version_catalog}

    async def fabric_versions(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取 Fabric 版本。"""
        return await self._loader_versions_response("fabric", body)

    async def forge_versions(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取 Forge 版本。"""
        return await self._loader_versions_response("forge", body)

    async def neoforge_versions(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取 NeoForge 版本。"""
        return await self._loader_versions_response("neoforge", body)

    async def optifine_versions(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取 OptiFine 版本。"""
        return {"success": False, "message": "当前 Game Core 尚未实现 OptiFine", "errorCode": "UNSUPPORTED_LOADER"}

    async def quilt_versions(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取 Quilt 版本。"""
        return await self._loader_versions_response("quilt", body)

    @_ipc_handler("LOADER_VERSIONS_FAILED")
    async def _loader_versions_response(self, loader: str, body: dict[str, Any]) -> dict[str, Any]:
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        source = (self._get_effective_config().get("download") or {}).get("mirror_source")
        loader_versions = await to_thread.run_sync(self.game.loader_versions, loader, body.get("game_version"), source)
        return {"success": True, "data": loader_versions}

    @_ipc_handler("VERSION_SCAN_FAILED")
    async def scan_versions(self, body: dict[str, Any]) -> dict[str, Any]:
        """扫描本地版本。"""
        requested_paths = body.get("path")
        if requested_paths is None:
            minecraft_paths = (self._get_effective_config().get("game") or {}).get("minecraft_paths") or []
            requested_paths = [item.get("path") if isinstance(item, dict) else item for item in minecraft_paths]
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        if body.get("force"):
            scanned_versions = await to_thread.run_sync(lambda: self.game.scan_versions(requested_paths, force=True))
        else:
            scanned_versions = await to_thread.run_sync(self.game.scan_versions, requested_paths)
        return {"success": True, "data": scanned_versions}

    @_ipc_handler("VERSION_INSTALL_FAILED")
    async def install_version(self, body: dict[str, Any]) -> dict[str, Any]:
        """安装游戏版本。"""
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        options = self._game_runtime_options(body)
        install = self.game.install_version(
            body,
            game_path=options["game_path"],
            source=options["source"],
            java_path=options["java_path"],
        )
        return {"success": True, "data": install}

    @_ipc_handler("VERSION_UNINSTALL_FAILED")
    async def uninstall_version(self, body: dict[str, Any]) -> dict[str, Any]:
        """卸载游戏版本。"""
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        options = self._game_runtime_options(body)
        await to_thread.run_sync(self.game.uninstall_version, body.get("version_id"), options["game_path"])
        return {"success": True, "data": None}

    # 账户

    async def accounts_list(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取账户列表。"""
        return {"success": True, "data": self.accounts.list_accounts()}

    async def accounts_current(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取当前账户。"""
        return {"success": True, "data": self.accounts.current_account()}

    @_ipc_handler("ACCOUNT_OPERATION_FAILED")
    async def accounts_add_offline(self, body: dict[str, Any]) -> dict[str, Any]:
        """添加离线账户。"""
        account_data = self.accounts.add_offline(body.get("username"), body.get("uuid"))
        return {"success": True, "data": account_data}

    @_ipc_handler("AUTHLIB_LOGIN_FAILED")
    async def accounts_add_authlib(self, body: dict[str, Any]) -> dict[str, Any]:
        """添加外置登录账户。"""
        server_url = self._normalize_authlib_server_url(body.get("server_url"))
        if server_url is None:
            return {"success": False, "message": "外置登录服务器地址无效", "errorCode": "INVALID_AUTHLIB_SERVER"}
        email = body.get("email")
        if not isinstance(email, str) or not email.strip():
            return {"success": False, "message": "外置登录邮箱不能为空", "errorCode": "INVALID_AUTHLIB_USERNAME"}
        email = email.strip()
        account = await to_thread.run_sync(
            self.accounts.add_authlib,
            server_url,
            email,
            body.get("password"),
        )
        self._remember_authlib_login(account.get("auth_server") or server_url, email)
        return {"success": True, "data": account}

    @_ipc_handler("AUTHLIB_PROFILE_SELECT_FAILED")
    async def accounts_select_authlib_profile(self, body: dict[str, Any]) -> dict[str, Any]:
        """为多角色外置账户选择本次登录使用的单个角色。"""
        account = await to_thread.run_sync(
            self.accounts.select_authlib_profile,
            body.get("account_id"),
            body.get("profile_id"),
        )
        return {"success": True, "data": account}

    @_ipc_handler("AUTHLIB_SERVER_RESOLVE_FAILED")
    async def authlib_resolve_server(self, body: dict[str, Any]) -> dict[str, Any]:
        """解析外置登录网站实际使用的 API 地址。"""
        server_url = self._normalize_authlib_server_url(body.get("server_url"))
        if server_url is None:
            return {"success": False, "message": "外置登录服务器地址无效", "errorCode": "INVALID_AUTHLIB_SERVER"}
        resolved_url = await to_thread.run_sync(self.accounts.resolve_authlib_server, server_url)
        return {"success": True, "data": resolved_url}

    @_ipc_handler("ACCOUNT_OPERATION_FAILED")
    async def accounts_start_microsoft_login(self, body: dict[str, Any]) -> dict[str, Any]:
        """开始微软登录。"""
        login_data = await to_thread.run_sync(self.accounts.start_microsoft_login)
        return {"success": True, "data": login_data}

    async def accounts_microsoft_login_config(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取微软登录配置。"""
        return {"success": True, "data": self.accounts.microsoft_login_config()}

    async def accounts_poll_microsoft_login(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取微软登录状态。"""
        return {"success": True, "data": self.accounts.poll_microsoft_login()}

    async def accounts_cancel_microsoft_login(self, body: dict[str, Any]) -> dict[str, Any]:
        """取消微软登录。"""
        return {"success": True, "data": {"cancelled": self.accounts.cancel_microsoft_login()}}

    @_ipc_handler("ACCOUNT_OPERATION_FAILED")
    async def accounts_complete_microsoft_login(self, body: dict[str, Any]) -> dict[str, Any]:
        """完成微软登录。"""
        login_result = self.accounts.complete_microsoft_login()
        return {"success": True, "data": login_result}

    @_ipc_handler("ACCOUNT_OPERATION_FAILED")
    async def accounts_switch(self, body: dict[str, Any]) -> dict[str, Any]:
        """切换账户。"""
        self.accounts.switch_account(body.get("account_id"))
        return {"success": True}

    @_ipc_handler("ACCOUNT_OPERATION_FAILED")
    async def accounts_remove(self, body: dict[str, Any]) -> dict[str, Any]:
        """删除账户。"""
        self.accounts.remove_account(body.get("account_id"))
        return {"success": True}

    @_ipc_handler("ACCOUNT_OPERATION_FAILED")
    async def accounts_refresh_profile(self, body: dict[str, Any]) -> dict[str, Any]:
        """刷新账户信息。"""
        refresh_result = await to_thread.run_sync(self.accounts.refresh_account, body.get("account_id"))
        return {"success": True, "data": refresh_result}

    async def authlib_servers(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取外置登录服务器。"""
        authlib_server_list = []
        for server in self._get_authlib_servers():
            server_url = server["url"]
            hostname = urlsplit(server_url).hostname or server_url
            authlib_server_list.append(
                {"name": hostname, "url": server_url, "email": server["email"], "description": server_url}
            )
        return {"success": True, "data": authlib_server_list}

    # 图片和文件选择

    @_ipc_handler("IMAGE_SAVE_URL_ERROR")
    async def image_save_url(self, body: dict[str, Any]) -> dict[str, Any]:
        """下载背景图片。"""
        url = _normalize_image_url(body.get("url"))
        if url is None:
            return {"success": False, "message": "无效的图片 URL", "errorCode": "INVALID_IMAGE_URL"}

        image_bytes, response = await _download_remote_image(url)
        ext = _guess_image_extension(response, url)
        data_url, b64 = await to_thread.run_sync(_encode_image_bytes, image_bytes, ext)
        self.logger.info("远程背景图已加载到内存: %s, ext=%s, base64_len=%d", url, ext, len(b64))
        return {"success": True, "data": {"dataUrl": data_url, "base64": b64, "url": url}}

    @_ipc_handler("IMAGE_SAVE_AS_ERROR")
    async def image_save_as(self, body: dict[str, Any]) -> dict[str, Any]:
        """保存背景图片。"""
        data_url = body.get("data_url") or body.get("dataUrl") or ""
        url = body.get("url") or ""
        path = body.get("path") or ""

        image_bytes: bytes | None = None
        default_name = "background.png"

        if isinstance(data_url, str) and data_url.startswith("data:"):
            try:
                header, b64 = data_url.split(",", 1)
                image_bytes = base64.b64decode(b64)
                mime = header.split(";")[0].split(":")[1] if ":" in header else "image/png"
                ext = _mime_to_ext.get(mime, ".png")
                default_name = f"background{ext}"
            except (ValueError, base64.binascii.Error) as exc:
                return {"success": False, "message": f"无法解析图片数据: {exc}", "errorCode": "INVALID_IMAGE_DATA"}
        elif isinstance(url, str) and url.lower().startswith(("http://", "https://")):
            image_bytes, response = await _download_remote_image(url)
            ext = _guess_image_extension(response, url)
            default_name = f"background{ext}"
        elif isinstance(path, str) and path:
            file_path = Path(self._normalize_file_path(path))
            if not await to_thread.run_sync(file_path.is_file):
                return {"success": False, "message": "图片文件不存在", "errorCode": "FILE_NOT_FOUND"}
            image_bytes = await to_thread.run_sync(file_path.read_bytes)
            ext = file_path.suffix.lower() or ".png"
            default_name = file_path.name or f"background{ext}"
        else:
            return {"success": False, "message": "缺少要保存的图片数据", "errorCode": "MISSING_IMAGE_SOURCE"}

        if image_bytes is None:
            return {"success": False, "message": "无法获取图片数据", "errorCode": "IMAGE_DATA_UNAVAILABLE"}
        if self._webview is None:
            return {"success": False, "message": "窗口尚未就绪", "errorCode": "WEBVIEW_NOT_READY"}

        picked = await to_thread.run_sync(
            lambda: DialogExt.file(self._webview).blocking_save_file(
                add_filter=("图片", list(_image_mime_map.keys())),
                set_file_name=default_name,
                set_title="保存背景图",
            )
        )
        if not picked:
            return {"success": False, "message": "未选择保存路径", "errorCode": "SAVE_CANCELLED"}

        save_path = Path(str(picked))

        def _write() -> str:
            save_path.write_bytes(image_bytes)
            return str(save_path)

        saved = await to_thread.run_sync(_write)
        self.logger.info("背景图已保存: %s", saved)
        return {"success": True, "data": {"path": saved}}

    @staticmethod
    def _normalize_file_path(path: str) -> str:
        if path.startswith("file://"):
            parsed = urlsplit(path)
            return unquote(parsed.path)
        return path

    @_ipc_handler("IMAGE_READ_ERROR")
    async def image_read_file(self, body: dict[str, Any]) -> dict[str, Any]:
        """读取图片。"""
        raw_path = body.get("path", "")
        if not raw_path:
            return {"success": False, "message": "路径不能为空", "errorCode": "INVALID_PATH"}

        path = self._normalize_file_path(raw_path)
        self.logger.info("读取本地图片: %s", path)

        def _read():
            file_path = Path(path)
            if not file_path.is_file():
                self.logger.warning("图片文件不存在: %s", file_path)
                return None
            ext = file_path.suffix.lower()
            mime = _image_mime_map.get(ext, "image/png")
            with Image.open(file_path) as img:
                img = img.convert("RGB") if img.mode in ("RGBA", "P") and mime == "image/jpeg" else img
                max_size = (1920, 1080)
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                buffer = BytesIO()
                if mime == "image/png":
                    img.save(buffer, format="PNG", optimize=True)
                elif mime == "image/webp":
                    img.save(buffer, format="WEBP", quality=85)
                else:
                    img.save(buffer, format="JPEG", quality=85)
                b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
            self.logger.info("图片读取成功: %s, mime=%s, base64_len=%d", file_path, mime, len(b64))
            return {"b64": b64, "mime": mime}

        result = await to_thread.run_sync(_read)
        if result is None:
            return {"success": False, "message": "图片文件不存在", "errorCode": "FILE_NOT_FOUND"}
        data_url = f"data:{result['mime']};base64,{result['b64']}"
        return {"success": True, "data": {"dataUrl": data_url, "base64": result["b64"]}}

    @_ipc_handler("IMAGE_LIST_FILES_ERROR")
    async def image_list_files(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取图片列表。"""
        raw_path = body.get("path", "")
        if not raw_path:
            return {"success": False, "message": "路径不能为空", "errorCode": "INVALID_PATH"}

        path = self._normalize_file_path(raw_path)
        self.logger.info("读取背景图片目录: %s", path)

        def _list():
            target = Path(path)
            if not target.is_dir():
                self.logger.warning("目录不存在或不是文件夹: %s", target)
                return []
            return sorted(str(p) for p in target.iterdir() if p.is_file() and p.suffix.lower() in _image_mime_map)

        files = await to_thread.run_sync(_list)
        self.logger.info("目录图片文件数量: %d", len(files))
        return {"success": True, "data": {"files": files}}

    @_ipc_handler("AVATAR_RENDER_FAILED")
    async def avatar_data_url(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取账户头像。"""
        avatar_data = await to_thread.run_sync(
            self.avatars.render_avatar,
            body.get("uuid"),
            body.get("size", 64),
            bool(body.get("use_default_skin", False)),
            body.get("type_name"),
            body.get("account_id"),
        )
        return {"success": True, "data": avatar_data}

    async def _pick_path(self, pick_folder: bool, title: str, extensions: list[str] | None = None) -> str:
        if self._webview is None:
            return ""

        def _pick():
            dialog = DialogExt.file(self._webview)
            if pick_folder:
                return dialog.blocking_pick_folder(set_title=title)
            if extensions:
                return dialog.blocking_pick_file(add_filter=("文件", extensions), set_title=title)
            return dialog.blocking_pick_file(set_title=title)

        file_path = await to_thread.run_sync(_pick)
        return self._normalize_file_path(str(file_path)) if file_path else ""

    @_ipc_handler("SELECT_DIRECTORY_ERROR")
    async def select_directory(self, body: dict[str, Any]) -> dict[str, Any]:
        """选择目录。"""
        path = await self._pick_path(True, "选择游戏目录")
        self.logger.info("目录选择结果: %s", path)
        return {"success": True, "data": {"path": path}}

    @_ipc_handler("SELECT_JAVA_ERROR")
    async def select_java(self, body: dict[str, Any]) -> dict[str, Any]:
        """选择 Java。"""
        path = await self._pick_path(False, "选择 Java 可执行文件")
        self.logger.info("Java 选择结果: %s", path)
        return {"success": True, "data": {"path": path}}

    @_ipc_handler("SELECT_IMAGE_ERROR")
    async def select_image(self, body: dict[str, Any]) -> dict[str, Any]:
        """选择图片。"""
        path = await self._pick_path(False, "选择背景图片", ["png", "jpg", "jpeg", "gif", "bmp", "webp"])
        self.logger.info("图片选择结果: %s", path)
        return {"success": True, "data": {"path": path, "base64": ""}}

    @_ipc_handler("SELECT_FILE_ERROR")
    async def select_file(self, body: dict[str, Any]) -> dict[str, Any]:
        """选择文件。"""
        path = await self._pick_path(False, "选择文件")
        self.logger.info("文件选择结果: %s", path)
        return {"success": True, "data": {"path": path}}

    @_ipc_handler("OPEN_FOLDER_FAILED")
    async def open_folder(self, body: dict[str, Any]) -> dict[str, Any]:
        """打开目录。"""
        path = body.get("path")
        if not isinstance(path, str) or not path.strip():
            return {"success": False, "message": "路径不能为空", "errorCode": "INVALID_PATH"}
        await to_thread.run_sync(_open_folder, path)
        self.logger.info("已打开文件夹: %s", path)
        return {"success": True, "data": None}

    @_ipc_handler("OPEN_URL_FAILED")
    async def open_url(self, body: dict[str, Any]) -> dict[str, Any]:
        """打开链接。"""
        url = body.get("url")
        if not isinstance(url, str) or not url.strip():
            return {"success": False, "message": "URL 不能为空", "errorCode": "INVALID_URL"}
        opened = webbrowser.open(url.strip())
        self.logger.info("已在默认浏览器中打开: %s", url)
        return {"success": True, "data": opened}

    # 游戏实例

    async def instances_list(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取游戏实例。"""
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        return {"success": True, "data": self.game.list_instances()}

    @_ipc_handler("GAME_LAUNCH_FAILED")
    async def launch_instance(self, body: dict[str, Any]) -> dict[str, Any]:
        """启动游戏实例。"""
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        options = self._game_runtime_options(body)
        instance = await self.game.launch_instance(body, **options)
        return {"success": True, "data": instance}

    async def cancel_launch(self, body: dict[str, Any]) -> dict[str, Any]:
        """取消游戏启动。"""
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        cancelled = self.game.cancel_launch()
        if not cancelled:
            return {"success": False, "message": "当前没有可取消的启动任务", "errorCode": "NO_ACTIVE_LAUNCH"}
        return {"success": True, "data": None}

    @_ipc_handler("INSTANCE_STOP_FAILED")
    async def instance_stop(self, body: dict[str, Any]) -> dict[str, Any]:
        """停止游戏实例。"""
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        await to_thread.run_sync(self.game.stop_instance, body.get("instance_id"))
        return {"success": True, "data": None}

    # 插件

    async def plugin_list(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取插件列表。"""
        return {"success": True, "data": self.plugins.list_plugins()}

    async def plugin_info(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取插件信息。"""
        plugin_name = body.get("plugin_name")
        plugin = self.plugins.get_plugin(plugin_name)
        if plugin is None:
            return {"success": False, "message": f"插件不存在: {plugin_name}", "errorCode": "PLUGIN_NOT_FOUND"}
        return {"success": True, "data": plugin.metadata}

    async def plugin_enable(self, body: dict[str, Any]) -> dict[str, Any]:
        """启用插件。"""
        plugin_name = body.get("plugin_name")
        result = self.plugins.enable(plugin_name)
        if not result.success:
            return failure(result.message or f"启用插件失败: {plugin_name}", "PLUGIN_ENABLE_FAILED")
        return {"success": True}

    async def plugin_disable(self, body: dict[str, Any]) -> dict[str, Any]:
        """禁用插件。"""
        plugin_name = body.get("plugin_name")
        result = self.plugins.disable(plugin_name)
        if not result.success:
            return failure(result.message or f"禁用插件失败: {plugin_name}", "PLUGIN_DISABLE_FAILED")
        return {"success": True}

    async def plugin_unload(self, body: dict[str, Any]) -> dict[str, Any]:
        """卸载插件。"""
        plugin_name = body.get("plugin_name")
        result = self.plugins.unload(plugin_name)
        if not result.success:
            return failure(result.message or f"卸载插件失败: {plugin_name}", "PLUGIN_UNLOAD_FAILED")
        return {"success": True}

    async def plugin_reload(self, body: dict[str, Any]) -> dict[str, Any]:
        """重新加载插件。"""
        plugin_name = body.get("plugin_name")
        result = self.plugins.reload(plugin_name)
        if not result.success:
            return failure(result.message or f"重载插件失败: {plugin_name}", "PLUGIN_RELOAD_FAILED")
        return {"success": True}

    async def plugin_install(self, body: dict[str, Any]) -> dict[str, Any]:
        """安装插件。"""
        plugin_path = body.get("plugin_path")
        result = self.plugins.install(plugin_path)
        if not result.success:
            return failure(result.message or "安装插件失败", "PLUGIN_INSTALL_FAILED")
        return {"success": True}

    async def plugin_get_routes(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取插件路由。"""
        return {"success": True, "data": self.plugins.get_routes()}

    async def plugin_get_slots(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取插件插槽。"""
        return {"success": True, "data": self.plugins.get_slots()}

    async def plugin_get_vue_slots(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取插件 Vue 插槽。"""
        return {"success": True, "data": self.plugins.get_vue_slots()}

    async def plugin_get_vue_components(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取插件 Vue 组件。"""
        return {"success": True, "data": self.plugins.get_vue_components()}

    async def plugin_call_command(self, body: dict[str, Any]) -> dict[str, Any]:
        """调用插件命令。"""
        command = body.get("command")
        try:
            result = self.plugins.call_command(command, body.get("params", {}))
        except PluginCommandError as exc:
            return {"success": False, "message": str(exc), "errorCode": "PLUGIN_COMMAND_FAILED"}
        return {"success": True, "data": result}

    async def plugin_get_settings(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取插件设置。"""
        plugin_name = body.get("plugin_name")
        return {"success": True, "data": self.plugins.get_settings(plugin_name)}

    async def plugin_update_setting(self, body: dict[str, Any]) -> dict[str, Any]:
        """更新插件设置。"""
        plugin_name = body.get("plugin_name")
        key = body.get("key")
        result = self.plugins.update_setting(plugin_name, key, body.get("value"))
        if not result.success:
            return failure(result.message or "更新设置失败", "SETTING_UPDATE_FAILED")
        return {"success": True}

    async def plugin_notify_sidebar_state(self, body: dict[str, Any]) -> dict[str, Any]:
        """通知插件侧栏的折叠状态。"""
        collapsed = body.get("collapsed")
        if not isinstance(collapsed, bool):
            return failure("侧栏状态必须是布尔值", "INVALID_SIDEBAR_STATE")
        self.plugins.set_sidebar_state(collapsed)
        return {"success": True}

    # 关于和调试

    async def launcher_info(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取启动器信息。"""
        launcher_config = self._get_effective_config().get("launcher") or {}
        return {
            "success": True,
            "data": {
                "version": launcher_config.get("version", ""),
                "version_type": launcher_config.get("version_type", "release"),
                "debug": bool(launcher_config.get("debug", False)),
            },
        }

    async def info_card_get(self, body: dict[str, Any]) -> dict[str, Any]:
        """获取信息卡片。"""
        data = await to_thread.run_sync(self.info_card.get_info_card)
        return {"success": True, "data": data}

    def _schedule_debug_maintenance(self, action: str) -> dict[str, Any]:
        if not bool(self.launcher.debug):
            return {"success": False, "message": "此操作仅在启动器调试模式下可用", "errorCode": "DEBUG_MODE_REQUIRED"}
        result = schedule_debug_maintenance(self.data_path, action)
        return success(
            {
                "action": result.action,
                "restart_required": result.restart_required,
                "targets": list(result.targets),
                "backup_root": str(result.backup_root),
            }
        )

    @_ipc_handler("DEBUG_MAINTENANCE_FAILED")
    async def debug_reset_launcher_data(self, body: dict[str, Any]) -> dict[str, Any]:
        """重置启动器数据。"""
        return self._schedule_debug_maintenance("reset_launcher_data")

    @_ipc_handler("DEBUG_MAINTENANCE_FAILED")
    async def debug_clear_plugins(self, body: dict[str, Any]) -> dict[str, Any]:
        """清理插件数据。"""
        return self._schedule_debug_maintenance("clear_plugins")
