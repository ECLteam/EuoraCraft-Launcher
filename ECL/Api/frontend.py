import base64
import json
import webbrowser
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from PIL import Image

from pytauri_plugins.dialog import DialogExt

from anyio import to_thread
from pytauri import EventTarget
from pytauri.ffi import Emitter as _Emitter
from pytauri.ipc import WebviewWindow

from ECL.Events import EventBus
from ECL.Infrastructure import get_logger
from ECL.Infrastructure.maintenance import schedule_debug_maintenance
from ECL.Services import AccountError, AvatarError, GameServiceError, VersionScanError


class FrontendApi:
    """EuoraCraft Launcher 前端 IPC API"""

    _QUEUED_FRONTEND_EVENTS = frozenset({"launcher:error", "launcher:popup"})
    _MAX_PENDING_FRONTEND_EVENTS = 50
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
        self.app_path: Path = self.launcher.app_path  # 启动器运行目录
        self.data_path: Path = self.launcher.data_path
        self._webview: WebviewWindow | None = None  # 前端就绪后赋值，用于主动推送事件
        self._pending_frontend_events: list[tuple[str, Any]] = []
        self._initialized = True

    def _queue_frontend_event(self, event: str, payload: Any) -> None:
        if event not in self._QUEUED_FRONTEND_EVENTS:
            return
        self._pending_frontend_events.append((event, payload))
        if len(self._pending_frontend_events) > self._MAX_PENDING_FRONTEND_EVENTS:
            self._pending_frontend_events.pop(0)

    def emit_to_frontend(self, event: str, payload: Any) -> None:
        """
        主动向 Web 前端推送事件
        :param event: 事件名称，前端通过 backend.on(event, cb) 监听
        :param payload: 事件负载数据
        """
        if self._webview is None:
            self._queue_frontend_event(event, payload)
            return
        try:
            # WebviewWindow 是 Rust-backed 对象，需通过 Emitter 的 emit_str_to 推送
            # EventTarget.Any() 表示推送到所有监听该事件的窗口
            _Emitter.emit_str_to(self._webview, EventTarget.Any(), event, json.dumps(payload, ensure_ascii=False))
        except (OSError, TypeError, ValueError, RuntimeError):
            self.logger.exception("向前端推送事件失败: %s", event)
            self._queue_frontend_event(event, payload)

    def emit_popup_to_frontend(self, payload: dict[str, Any]) -> None:
        """推送普通全局弹窗；cacheable 仅表示允许用户选择“不再显示”。"""
        if not isinstance(payload, dict):
            return
        self.emit_to_frontend("launcher:popup", payload)

    def emit_error_to_frontend(self, payload: dict[str, Any]) -> None:
        """推送需要用户感知的后端错误。"""
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

    def _flush_pending_frontend_events(self) -> None:
        pending_events = self._pending_frontend_events
        self._pending_frontend_events = []
        for event, payload in pending_events:
            self.emit_to_frontend(event, payload)

    def _get_effective_config(self) -> dict[str, Any]:
        """
        获取包含运行时信息的前端配置
        :return: 合并后的完整配置
        """
        config = self.config.get_config()
        launcher_config = config.get("launcher") or {}

        launcher = self.launcher
        runtime_config = (launcher.config or {}).get("launcher") or {}
        launcher_config.update(runtime_config)
        launcher_config["debug"] = bool(launcher.debug)
        launcher_config["version"] = launcher.launcher_version or ""
        launcher_config["version_type"] = launcher.launcher_version_type or "beta"

        config["launcher"] = launcher_config
        return config

    @staticmethod
    def _normalize_authlib_server_url(value: Any) -> str | None:
        if not isinstance(value, str):
            return None

        server_url = value.strip().rstrip("/")
        if not server_url or " " in server_url:
            return None

        try:
            parsed = urlsplit(server_url)
        except ValueError:
            return None
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        return server_url

    def _get_authlib_server_urls(self) -> list[str]:
        authlib_config = self.config.get_config("authlib") or {}
        stored_servers = authlib_config.get("servers") or []

        server_urls: list[str] = []
        for item in stored_servers:
            raw_url = item.get("url") if isinstance(item, dict) else item
            url = self._normalize_authlib_server_url(raw_url)
            if url and url not in server_urls:
                server_urls.append(url)
        return server_urls

    def _remember_authlib_server_url(self, server_url: str) -> bool:
        server_urls = self._get_authlib_server_urls()
        if server_url in server_urls:
            server_urls.remove(server_url)
        server_urls.insert(0, server_url)
        server_urls = server_urls[:20]

        authlib_config = self.config.get_config("authlib") or {}
        authlib_config["servers"] = server_urls
        return self.config.save_config("authlib", authlib_config)

    @staticmethod
    def _account_error_response(exc: Exception) -> dict[str, Any]:
        error_code = exc.error_code if isinstance(exc, AccountError) else "ACCOUNT_OPERATION_FAILED"
        return {"success": False, "message": str(exc), "errorCode": error_code}

    @staticmethod
    def _game_error_response(exc: Exception, fallback_code: str = "GAME_OPERATION_FAILED") -> dict[str, Any]:
        error_code = exc.error_code if isinstance(exc, GameServiceError) else fallback_code
        return {"success": False, "message": str(exc), "errorCode": error_code}

    def _game_runtime_options(self, body: dict[str, Any]) -> dict[str, Any]:
        config = self._get_effective_config()
        game_config = config.get("game") or {}
        download_config = config.get("download") or {}
        minecraft_paths = game_config.get("minecraft_paths") or []
        first_path = None
        if minecraft_paths:
            first_item = minecraft_paths[0]
            first_path = first_item.get("path") if isinstance(first_item, dict) else first_item
        return {
            "game_path": body.get("game_path") or game_config.get("last_install_path") or first_path,
            "source": download_config.get("mirror_source") or "official",
            "java_path": body.get("java_path") or game_config.get("java_path") or None,
            "memory": body.get("memory") if body.get("memory") is not None else game_config.get("memory_size", 4096),
            "width": body.get("width") if body.get("width") is not None else game_config.get("game_width", 854),
            "height": body.get("height") if body.get("height") is not None else game_config.get("game_height", 480),
            "jvm_args": body.get("jvm_args") if body.get("jvm_args") is not None else game_config.get("jvm_args", []),
            "game_args": body.get("game_args") or [],
            "version_isolation": bool(body.get("version_isolation", False)),
            "download_threads": (
                body.get("download_threads")
                if body.get("download_threads") is not None
                else download_config.get("download_threads", 16)
            ),
        }

    async def frontend_ready(self, body: dict[str, Any], webview_window: WebviewWindow) -> dict[str, Any]:
        """
        接收前端加载完成通知并显示主窗口
        :param body: 前端传递的请求参数
        :param webview_window: 当前 Tauri Webview 窗口
        :return: 窗口显示结果
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

    async def ping(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        检查前后端 IPC 连接状态
        :param body: 前端传递的请求参数
        :return: 临时连接状态
        """
        return {"success": True, "data": {"status": "ok", "message": "正常"}}

    # 配置

    async def config_get(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取指定配置分区
        :param body: 包含 section 的请求参数
        :return: 指定分区的配置数据
        """
        section = body.get("section")
        if not isinstance(section, str) or not section.strip():
            return {
                "success": False,
                "message": "配置分区名称不能为空",
                "errorCode": "INVALID_CONFIG_SECTION",
            }
        return {"success": True, "data": self._get_effective_config().get(section)}

    async def config_set(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        保存指定配置分区
        :param body: 包含 section 和 data 的请求参数
        :return: 配置保存结果
        """
        section = body.get("section")
        if not isinstance(section, str) or not section.strip():
            return {
                "success": False,
                "message": "配置分区名称不能为空",
                "errorCode": "INVALID_CONFIG_SECTION",
            }
        if "data" not in body:
            return {
                "success": False,
                "message": "缺少需要保存的配置数据",
                "errorCode": "MISSING_CONFIG_DATA",
            }

        if not self.config.save_config(section, body["data"]):
            return {
                "success": False,
                "message": "保存配置失败",
                "errorCode": "CONFIG_SAVE_FAILED",
            }
        return {"success": True}

    async def config_list(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取全部配置分区名称
        :param body: 前端传递的请求参数
        :return: 配置分区名称列表
        """
        return {"success": True, "data": self.config.list_sections()}

    async def config_get_all(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取全部配置数据
        :param body: 前端传递的请求参数
        :return: 完整配置数据
        """
        return {"success": True, "data": self._get_effective_config()}

    async def config_get_many(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        批量获取指定配置分区
        :param body: 包含 sections 的请求参数
        :return: 配置分区映射
        """
        sections = body.get("sections")
        if not isinstance(sections, list) or not all(
            isinstance(section, str) and section.strip() for section in sections
        ):
            return {
                "success": False,
                "message": "配置分区列表格式无效",
                "errorCode": "INVALID_CONFIG_SECTIONS",
            }
        config = self._get_effective_config()
        return {"success": True, "data": {section: config.get(section) for section in dict.fromkeys(sections)}}

    # Java

    async def java_scan(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        扫描本机 Java 安装
        :param body: 前端传递的请求参数
        :return: 临时 Java 安装列表
        """
        java_installations: list[dict[str, Any]] = []
        return {"success": True, "data": java_installations}

    async def java_list(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取已记录的 Java 安装
        :param body: 前端传递的请求参数
        :return: 临时 Java 安装列表
        """
        java_installations: list[dict[str, Any]] = []
        return {"success": True, "data": java_installations}

    # 游戏版本

    async def minecraft_versions(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取 Minecraft 版本列表
        :param body: 包含 filter_type 的请求参数
        :return: 临时 Minecraft 版本列表
        """
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        try:
            source = (self._get_effective_config().get("download") or {}).get("mirror_source")
            version_list = await to_thread.run_sync(
                self.game.minecraft_versions,
                body.get("filter_type"),
                source,
            )
            return {"success": True, "data": version_list}
        except Exception as exc:
            self.logger.exception("获取 Minecraft 版本列表失败")
            return self._game_error_response(exc, "VERSION_CATALOG_FAILED")

    async def minecraft_versions_classified(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取分类后的 Minecraft 版本列表
        :param body: 前端传递的请求参数
        :return: 临时分类版本数据
        """
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        try:
            source = (self._get_effective_config().get("download") or {}).get("mirror_source")
            version_catalog = await to_thread.run_sync(self.game.minecraft_versions_classified, source)
            return {"success": True, "data": version_catalog}
        except Exception as exc:
            self.logger.exception("获取 Minecraft 分类版本列表失败")
            return self._game_error_response(exc, "VERSION_CATALOG_FAILED")

    async def fabric_versions(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取指定游戏版本可用的 Fabric 版本
        :param body: 包含 game_version 的请求参数
        :return: 临时 Fabric 版本列表
        """
        return await self._loader_versions_response("fabric", body)

    async def forge_versions(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取指定游戏版本可用的 Forge 版本
        :param body: 包含 game_version 的请求参数
        :return: 临时 Forge 版本列表
        """
        return await self._loader_versions_response("forge", body)

    async def neoforge_versions(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取指定游戏版本可用的 NeoForge 版本
        :param body: 包含 game_version 的请求参数
        :return: 临时 NeoForge 版本列表
        """
        return await self._loader_versions_response("neoforge", body)

    async def optifine_versions(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取指定游戏版本可用的 OptiFine 版本
        :param body: 包含 game_version 的请求参数
        :return: 临时 OptiFine 版本列表
        """
        return {
            "success": False,
            "message": "当前 Game Core 尚未实现 OptiFine",
            "errorCode": "UNSUPPORTED_LOADER",
        }

    async def quilt_versions(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取指定游戏版本可用的 Quilt 版本
        :param body: 包含 game_version 的请求参数
        :return: 临时 Quilt 版本列表
        """
        return await self._loader_versions_response("quilt", body)

    async def _loader_versions_response(self, loader: str, body: dict[str, Any]) -> dict[str, Any]:
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        try:
            source = (self._get_effective_config().get("download") or {}).get("mirror_source")
            loader_versions = await to_thread.run_sync(
                self.game.loader_versions,
                loader,
                body.get("game_version"),
                source,
            )
            return {"success": True, "data": loader_versions}
        except Exception as exc:
            self.logger.exception("获取 %s 版本列表失败", loader)
            return self._game_error_response(exc, "LOADER_VERSIONS_FAILED")

    async def scan_versions(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        扫描本地 Minecraft 游戏版本
        :param body: 包含 path 的请求参数
        :return: 临时本地版本列表
        """
        requested_paths = body.get("path")
        if requested_paths is None:
            minecraft_paths = (self._get_effective_config().get("game") or {}).get("minecraft_paths") or []
            requested_paths = [
                item.get("path") if isinstance(item, dict) else item
                for item in minecraft_paths
            ]
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        try:
            scanned_versions = await to_thread.run_sync(self.game.scan_versions, requested_paths)
            return {"success": True, "data": scanned_versions}
        except VersionScanError as exc:
            return {
                "success": False,
                "message": str(exc),
                "errorCode": exc.error_code,
            }
        except Exception as exc:
            self.logger.exception("扫描本地 Minecraft 版本失败")
            return {
                "success": False,
                "message": f"扫描本地版本失败: {exc}",
                "errorCode": "VERSION_SCAN_FAILED",
            }

    async def install_version(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        安装 Minecraft 游戏版本
        :param body: 包含版本和加载器选项的请求参数
        :return: 后台安装任务是否成功创建
        """
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        options = self._game_runtime_options(body)
        try:
            self.game.start_install(
                body,
                game_path=options["game_path"],
                source=options["source"],
                java_path=options["java_path"],
                download_threads=options["download_threads"],
            )
            return {"success": True, "data": None}
        except Exception as exc:
            return self._game_error_response(exc, "VERSION_INSTALL_FAILED")

    async def uninstall_version(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        卸载 Minecraft 游戏版本
        :param body: 包含 version_id 和 game_path 的请求参数
        :return: 临时卸载结果
        """
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        options = self._game_runtime_options(body)
        try:
            await to_thread.run_sync(
                self.game.uninstall_version,
                body.get("version_id"),
                options["game_path"],
            )
            return {"success": True, "data": None}
        except Exception as exc:
            return self._game_error_response(exc, "VERSION_UNINSTALL_FAILED")

    # 账户

    async def accounts_list(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取全部 Minecraft 账户
        :param body: 前端传递的请求参数
        :return: 临时账户列表和当前账户
        """
        return {"success": True, "data": self.accounts.list_accounts()}

    async def accounts_current(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取当前 Minecraft 账户
        :param body: 前端传递的请求参数
        :return: 临时当前账户
        """
        return {"success": True, "data": self.accounts.current_account()}

    async def accounts_add_offline(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        添加离线账户
        :param body: 包含 username 和可选 uuid 的请求参数
        :return: 临时离线账户数据
        """
        try:
            account_data = self.accounts.add_offline(body.get("username"), body.get("uuid"))
            return {"success": True, "data": account_data}
        except Exception as exc:
            return self._account_error_response(exc)

    async def accounts_add_authlib(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        添加 Authlib Injector 账户
        :param body: 包含服务器地址和登录凭据的请求参数
        :return: 临时 Authlib 账户数据
        """
        return {
            "success": False,
            "message": "外置登录暂未开发",
            "errorCode": "AUTHLIB_NOT_IMPLEMENTED",
        }

    async def accounts_start_microsoft_login(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        开始 Microsoft 设备代码登录
        :param body: 前端传递的请求参数
        :return: 临时 Microsoft 登录数据
        """
        try:
            login_data = await to_thread.run_sync(self.accounts.start_microsoft_login)
            return {"success": True, "data": login_data}
        except Exception as exc:
            return self._account_error_response(exc)

    async def accounts_microsoft_login_config(self, body: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "data": self.accounts.microsoft_login_config()}

    async def accounts_poll_microsoft_login(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        轮询 Microsoft 登录状态
        :param body: 前端传递的请求参数
        :return: 临时 Microsoft 登录状态
        """
        return {"success": True, "data": self.accounts.poll_microsoft_login()}

    async def accounts_cancel_microsoft_login(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        取消 Microsoft 设备代码登录
        :param body: 前端传递的请求参数
        :return: 是否取消了进行中的登录
        """
        return {"success": True, "data": {"cancelled": self.accounts.cancel_microsoft_login()}}

    async def accounts_complete_microsoft_login(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        完成 Microsoft 账户登录
        :param body: 前端传递的请求参数
        :return: 临时 Microsoft 登录结果
        """
        try:
            login_result = self.accounts.complete_microsoft_login()
            return {"success": True, "data": login_result}
        except Exception as exc:
            return self._account_error_response(exc)

    async def accounts_switch(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        切换当前 Minecraft 账户
        :param body: 包含 account_id 的请求参数
        :return: 临时账户切换结果
        """
        try:
            self.accounts.switch_account(body.get("account_id"))
            return {"success": True}
        except Exception as exc:
            return self._account_error_response(exc)

    async def accounts_remove(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        移除 Minecraft 账户
        :param body: 包含 account_id 的请求参数
        :return: 临时账户移除结果
        """
        try:
            self.accounts.remove_account(body.get("account_id"))
            return {"success": True}
        except Exception as exc:
            return self._account_error_response(exc)

    async def accounts_refresh_profile(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        刷新 Minecraft 账户资料
        :param body: 包含 account_id 的请求参数
        :return: 临时资料刷新结果
        """
        try:
            refresh_result = await to_thread.run_sync(
                self.accounts.refresh_account,
                body.get("account_id"),
            )
            return {"success": True, "data": refresh_result}
        except Exception as exc:
            return self._account_error_response(exc)

    async def authlib_servers(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取已保存的 Authlib 认证服务器
        :param body: 前端传递的请求参数
        :return: Authlib 服务器列表
        """
        authlib_server_list = []
        for server_url in self._get_authlib_server_urls():
            hostname = urlsplit(server_url).hostname or server_url
            authlib_server_list.append(
                {
                    "name": hostname,
                    "url": server_url,
                    "description": server_url,
                }
            )
        return {"success": True, "data": authlib_server_list}

    # 用户协议

    async def user_agreement_get(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取用户协议接受状态
        :param body: 前端传递的请求参数
        :return: 临时用户协议数据
        """
        agreement_data = {"accepted": False, "uuid": ""}
        return {"success": True, "data": agreement_data}

    async def user_agreement_save(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        保存用户协议接受状态
        :param body: 包含 accepted 和 uuid 的请求参数
        :return: 临时用户协议数据
        """
        agreement_data = {"accepted": False, "uuid": ""}
        return {"success": True, "data": agreement_data}

    async def user_agreement_clear(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        清除用户协议接受状态
        :param body: 前端传递的请求参数
        :return: 临时清除结果
        """
        clear_result = None
        return {"success": True, "data": clear_result}

    # 图片

    async def image_fetch_data_url(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取网络图片的 Data URL
        :param body: 包含 url 的请求参数
        :return: 临时图片数据
        """
        image_data = {"dataUrl": "", "base64": ""}
        return {"success": True, "data": image_data}

    async def image_save_url(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        保存网络图片到本地
        :param body: 包含 url 的请求参数
        :return: 临时图片保存路径
        """
        save_result = {"path": ""}
        return {"success": True, "data": save_result}

    @staticmethod
    def _normalize_file_path(path: str) -> str:
        """统一 file:// URL 和普通路径为本地绝对路径。"""
        if path.startswith("file://"):
            parsed = urlsplit(path)
            return unquote(parsed.path)
        return path

    async def image_read_file(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        读取本地图片并转换为 Data URL 和 base64，自动压缩过大的图片避免 IPC 传输失败
        :param body: 包含 path 的请求参数
        :return: 图片数据，包含 dataUrl 和 base64
        """
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
            mime_map = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".bmp": "image/bmp",
                ".webp": "image/webp",
            }
            mime = mime_map.get(ext, "image/png")

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

        try:
            result = await to_thread.run_sync(_read)
        except Exception as exc:
            self.logger.exception("读取图片时发生异常: %s", path)
            return {"success": False, "message": f"读取图片失败: {exc}", "errorCode": "IMAGE_READ_ERROR"}

        if result is None:
            return {"success": False, "message": "图片文件不存在", "errorCode": "FILE_NOT_FOUND"}

        data_url = f"data:{result['mime']};base64,{result['b64']}"
        return {"success": True, "data": {"dataUrl": data_url, "base64": result["b64"]}}

    async def avatar_data_url(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取 Minecraft 头像 Data URL
        :param body: 包含头像渲染选项的请求参数
        :return: PNG 格式头像数据
        """
        try:
            avatar_data = await to_thread.run_sync(
                self.avatars.render_avatar,
                body.get("uuid"),
                body.get("size", 64),
                bool(body.get("use_default_skin", False)),
            )
            return {"success": True, "data": avatar_data}
        except Exception as exc:
            error_code = exc.error_code if isinstance(exc, AvatarError) else "AVATAR_RENDER_FAILED"
            return {"success": False, "message": str(exc), "errorCode": error_code}

    # 文件选择

    async def select_directory(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        打开目录选择对话框
        :param body: 前端传递的请求参数
        :return: 目录选择结果
        """
        if self._webview is None:
            return {"success": True, "data": {"path": ""}}

        def _pick():
            dialog = DialogExt.file(self._webview)
            return dialog.blocking_pick_folder(set_title="选择游戏目录")

        try:
            file_path = await to_thread.run_sync(_pick)
        except Exception as exc:
            self.logger.exception("打开目录选择对话框失败")
            return {"success": False, "message": f"选择目录失败: {exc}", "errorCode": "SELECT_DIRECTORY_ERROR"}

        path = self._normalize_file_path(str(file_path)) if file_path else ""
        self.logger.info("目录选择结果: %s", path)
        return {"success": True, "data": {"path": path}}

    async def select_java(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        打开 Java 可执行文件选择对话框
        :param body: 前端传递的请求参数
        :return: Java 路径选择结果
        """
        if self._webview is None:
            return {"success": True, "data": {"path": ""}}

        def _pick():
            dialog = DialogExt.file(self._webview)
            return dialog.blocking_pick_file(set_title="选择 Java 可执行文件")

        try:
            file_path = await to_thread.run_sync(_pick)
        except Exception as exc:
            self.logger.exception("打开 Java 选择对话框失败")
            return {"success": False, "message": f"选择 Java 失败: {exc}", "errorCode": "SELECT_JAVA_ERROR"}

        path = self._normalize_file_path(str(file_path)) if file_path else ""
        self.logger.info("Java 选择结果: %s", path)
        return {"success": True, "data": {"path": path}}

    async def select_image(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        打开图片选择对话框
        :param body: 前端传递的请求参数
        :return: 图片选择结果，包含 path 和 base64
        """
        if self._webview is None:
            return {"success": True, "data": {"path": "", "base64": ""}}

        def _pick():
            dialog = DialogExt.file(self._webview)
            return dialog.blocking_pick_file(
                add_filter=("图片文件", ["png", "jpg", "jpeg", "gif", "bmp", "webp"]),
                set_title="选择背景图片",
            )

        try:
            file_path = await to_thread.run_sync(_pick)
        except Exception as exc:
            self.logger.exception("打开图片选择对话框失败")
            return {"success": False, "message": f"选择图片失败: {exc}", "errorCode": "SELECT_IMAGE_ERROR"}

        path = self._normalize_file_path(str(file_path)) if file_path else ""
        self.logger.info("图片选择结果: %s", path)
        return {"success": True, "data": {"path": path, "base64": ""}}

    async def select_file(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        打开文件选择对话框
        :param body: 前端传递的请求参数
        :return: 文件选择结果
        """
        if self._webview is None:
            return {"success": True, "data": {"path": ""}}

        def _pick():
            dialog = DialogExt.file(self._webview)
            return dialog.blocking_pick_file(set_title="选择文件")

        try:
            file_path = await to_thread.run_sync(_pick)
        except Exception as exc:
            self.logger.exception("打开文件选择对话框失败")
            return {"success": False, "message": f"选择文件失败: {exc}", "errorCode": "SELECT_FILE_ERROR"}

        path = self._normalize_file_path(str(file_path)) if file_path else ""
        self.logger.info("文件选择结果: %s", path)
        return {"success": True, "data": {"path": path}}

    async def open_folder(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        在系统文件管理器中打开目录
        :param body: 包含 path 的请求参数
        :return: 临时目录打开结果
        """
        open_result = None
        return {"success": True, "data": open_result}

    async def open_url(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        使用系统默认浏览器打开外部 URL
        :param body: 包含 url 的请求参数
        :return: 打开结果
        """
        url = body.get("url")
        if not isinstance(url, str) or not url.strip():
            return {
                "success": False,
                "message": "URL 不能为空",
                "errorCode": "INVALID_URL",
            }
        try:
            opened = webbrowser.open(url.strip())
            self.logger.info(f"已在默认浏览器中打开: {url}")
            return {"success": True, "data": opened}
        except Exception as e:
            self.logger.error(f"打开 URL 失败: {url} - {e}")
            return {
                "success": False,
                "message": f"打开 URL 失败: {e}",
                "errorCode": "OPEN_URL_FAILED",
            }

    # 游戏实例

    async def instances_list(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取正在管理的游戏实例
        :param body: 前端传递的请求参数
        :return: 临时游戏实例列表
        """
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        return {"success": True, "data": self.game.list_instances()}

    async def launch_instance(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        启动 Minecraft 游戏实例
        :param body: 包含游戏版本和启动选项的请求参数
        :return: 临时实例启动结果
        """
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        options = self._game_runtime_options(body)
        try:
            await self.game.launch_instance(body, **options)
            return {"success": True, "data": None}
        except Exception as exc:
            return self._game_error_response(exc, "GAME_LAUNCH_FAILED")

    async def cancel_launch(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        取消当前游戏启动任务
        :param body: 前端传递的请求参数
        :return: 临时取消结果
        """
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        cancelled = self.game.cancel_launch()
        if not cancelled:
            return {"success": False, "message": "当前没有可取消的启动任务", "errorCode": "NO_ACTIVE_LAUNCH"}
        return {"success": True, "data": None}

    async def instance_stop(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        停止指定游戏实例
        :param body: 包含 instance_id 的请求参数
        :return: 临时实例停止结果
        """
        if self.game is None:
            return {"success": False, "message": "游戏服务未初始化", "errorCode": "GAME_SERVICE_UNAVAILABLE"}
        try:
            await to_thread.run_sync(self.game.stop_instance, body.get("instance_id"))
            return {"success": True, "data": None}
        except Exception as exc:
            return self._game_error_response(exc, "INSTANCE_STOP_FAILED")

    async def export_logs(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        导出启动器日志
        :param body: 包含可选 output_path 的请求参数
        :return: 临时日志导出路径
        """
        export_result = {"path": ""}
        return {"success": True, "data": export_result}

    # 插件

    async def plugin_list(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取已安装插件列表
        :param body: 前端传递的请求参数
        :return: 插件列表
        """
        return {"success": True, "data": self.plugins.list_plugins()}

    async def plugin_info(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取指定插件信息
        :param body: 包含 plugin_name 的请求参数
        :return: 插件信息
        """
        plugin_name = body.get("plugin_name")
        plugin = self.plugins.get_plugin(plugin_name)
        if plugin is None:
            return {"success": False, "message": f"插件不存在: {plugin_name}", "errorCode": "PLUGIN_NOT_FOUND"}
        return {"success": True, "data": plugin.metadata}

    async def plugin_enable(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        启用指定插件
        :param body: 包含 plugin_name 的请求参数
        :return: 启用结果
        """
        plugin_name = body.get("plugin_name")
        if not self.plugins._enable(plugin_name):
            return {"success": False, "message": f"启用插件失败: {plugin_name}", "errorCode": "PLUGIN_ENABLE_FAILED"}
        return {"success": True}

    async def plugin_disable(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        禁用指定插件
        :param body: 包含 plugin_name 和 force 的请求参数
        :return: 禁用结果
        """
        plugin_name = body.get("plugin_name")
        if not self.plugins.disable(plugin_name):
            return {"success": False, "message": f"禁用插件失败: {plugin_name}", "errorCode": "PLUGIN_DISABLE_FAILED"}
        return {"success": True}

    async def plugin_unload(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        卸载指定插件运行实例
        :param body: 包含 plugin_name 的请求参数
        :return: 卸载结果
        """
        plugin_name = body.get("plugin_name")
        if not self.plugins.unload(plugin_name):
            return {"success": False, "message": f"卸载插件失败: {plugin_name}", "errorCode": "PLUGIN_UNLOAD_FAILED"}
        return {"success": True}

    async def plugin_reload(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        重新加载指定插件
        :param body: 包含 plugin_name 和 cascade 的请求参数
        :return: 重载结果
        """
        plugin_name = body.get("plugin_name")
        if not self.plugins.reload(plugin_name):
            return {"success": False, "message": f"重载插件失败: {plugin_name}", "errorCode": "PLUGIN_RELOAD_FAILED"}
        return {"success": True}

    async def plugin_install(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        从本地路径安装插件
        :param body: 包含 plugin_path 的请求参数
        :return: 安装结果
        """
        plugin_path = body.get("plugin_path")
        if not self.plugins.install(plugin_path):
            return {"success": False, "message": "安装插件失败", "errorCode": "PLUGIN_INSTALL_FAILED"}
        return {"success": True}

    async def plugin_get_routes(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取插件注册的前端路由
        :param body: 包含可选 plugin_id 的请求参数
        :return: 插件路由列表
        """
        return {"success": True, "data": self.plugins.get_routes()}

    async def plugin_get_slots(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取插件注册的 HTML 插槽
        :param body: 前端传递的请求参数
        :return: 插件插槽映射
        """
        return {"success": True, "data": self.plugins.get_slots()}

    async def plugin_get_vue_slots(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取插件注册的 Vue 组件插槽
        :param body: 前端传递的请求参数
        :return: slot_id → [{plugin, component_name, template, script, style}, ...]
        """
        return {"success": True, "data": self.plugins.get_vue_slots()}

    async def plugin_get_vue_components(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取所有插件注册的 Vue 组件定义
        :param body: 前端传递的请求参数
        :return: component_name → {plugin, template, script, style}
        """
        return {"success": True, "data": self.plugins.get_vue_components()}

    async def plugin_call_command(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        调用插件提供的命令
        :param body: 包含 command 和 params 的请求参数
        :return: 插件命令结果
        """
        command = body.get("command")
        result = self.plugins.call_command(command, body.get("params", {}))
        return {"success": True, "data": result}

    async def plugin_get_settings(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取指定插件的设置结构和值
        :param body: 包含 plugin_name 的请求参数
        :return: 插件设置数据
        """
        plugin_name = body.get("plugin_name")
        return {"success": True, "data": self.plugins.get_settings(plugin_name)}

    async def plugin_update_setting(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        更新指定插件的设置项
        :param body: 包含 plugin_name、key 和 value 的请求参数
        :return: 设置更新结果
        """
        plugin_name = body.get("plugin_name")
        key = body.get("key")
        if not self.plugins.update_setting(plugin_name, key, body.get("value")):
            return {"success": False, "message": "更新设置失败", "errorCode": "SETTING_UPDATE_FAILED"}
        return {"success": True}

    # Mod 管理

    async def get_mods(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取指定游戏目录中的 Mod
        :param body: 包含可选 game_path 的请求参数
        :return: 临时 Mod 列表
        """
        mod_list: list[dict[str, Any]] = []
        return {"success": True, "data": mod_list}

    async def toggle_mod(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        切换指定 Mod 的启用状态
        :param body: 包含 game_path 和 filename 的请求参数
        :return: 临时 Mod 状态
        """
        mod_state = {"enabled": False}
        return {"success": True, "data": mod_state}

    async def add_mod(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        添加 Mod 到指定游戏目录
        :param body: 包含 game_path 和 source_path 的请求参数
        :return: 临时 Mod 添加结果
        """
        add_result = {"filename": ""}
        return {"success": True, "data": add_result}

    async def remove_mod(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        从指定游戏目录移除 Mod
        :param body: 包含 game_path 和 filename 的请求参数
        :return: 临时 Mod 移除结果
        """
        remove_result = None
        return {"success": True, "data": remove_result}

    async def open_mods_folder(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        打开指定游戏目录的 Mods 文件夹
        :param body: 包含 game_path 的请求参数
        :return: 临时 Mods 文件夹路径
        """
        folder_data = {"path": ""}
        return {"success": True, "data": folder_data}

    # 整合包与游戏资源

    async def detect_modpack_type(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        检测整合包文件类型
        :param body: 包含 file_path 的请求参数
        :return: 临时整合包类型信息
        """
        modpack_data = {"type": ""}
        return {"success": True, "data": modpack_data}

    async def import_modpack(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        导入 Minecraft 整合包
        :param body: 包含整合包路径和安装选项的请求参数
        :return: 临时整合包导入结果
        """
        import_result = None
        return {"success": True, "data": import_result}

    async def export_modpack(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        导出 Minecraft 整合包
        :param body: 包含游戏路径和导出选项的请求参数
        :return: 临时整合包导出结果
        """
        export_result = None
        return {"success": True, "data": export_result}

    async def list_resourcepacks(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取指定游戏目录中的资源包
        :param body: 包含可选 game_path 的请求参数
        :return: 临时资源包列表
        """
        resourcepack_list: list[dict[str, Any]] = []
        return {"success": True, "data": resourcepack_list}

    async def list_shaderpacks(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取指定游戏目录中的光影包
        :param body: 包含可选 game_path 的请求参数
        :return: 临时光影包列表
        """
        shaderpack_list: list[dict[str, Any]] = []
        return {"success": True, "data": shaderpack_list}

    async def list_saves(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取指定游戏目录中的存档
        :param body: 包含可选 game_path 的请求参数
        :return: 临时游戏存档列表
        """
        save_list: list[dict[str, Any]] = []
        return {"success": True, "data": save_list}

    async def remove_resourcepack(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        移除指定资源包
        :param body: 包含 game_path 和 filename 的请求参数
        :return: 临时资源包移除结果
        """
        remove_result = None
        return {"success": True, "data": remove_result}

    async def remove_shaderpack(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        移除指定光影包
        :param body: 包含 game_path 和 filename 的请求参数
        :return: 临时光影包移除结果
        """
        remove_result = None
        return {"success": True, "data": remove_result}

    async def delete_save(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        删除指定 Minecraft 存档
        :param body: 包含 game_path 和 save_name 的请求参数
        :return: 临时存档删除结果
        """
        delete_result = None
        return {"success": True, "data": delete_result}

    async def open_resourcepacks_folder(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        打开指定游戏目录的资源包文件夹
        :param body: 包含 game_path 的请求参数
        :return: 临时文件夹打开结果
        """
        open_result = None
        return {"success": True, "data": open_result}

    async def open_shaderpacks_folder(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        打开指定游戏目录的光影包文件夹
        :param body: 包含 game_path 的请求参数
        :return: 临时文件夹打开结果
        """
        open_result = None
        return {"success": True, "data": open_result}

    async def open_saves_folder(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        打开指定游戏目录的存档文件夹
        :param body: 包含 game_path 的请求参数
        :return: 临时文件夹打开结果
        """
        open_result = None
        return {"success": True, "data": open_result}

    # 在线 Mod 搜索

    async def search_mods(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        搜索在线 Mod
        :param body: 包含搜索词、来源和筛选条件的请求参数
        :return: 临时 Mod 搜索结果
        """
        search_results: list[dict[str, Any]] = []
        return {"success": True, "data": search_results}

    async def get_mod_info(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取在线 Mod 详细信息
        :param body: 包含 mod_id 和 source 的请求参数
        :return: 临时 Mod 详细信息
        """
        mod_data: dict[str, Any] = {}
        return {"success": True, "data": mod_data}

    async def get_mod_versions(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取在线 Mod 的可用版本
        :param body: 包含 Mod 标识和筛选条件的请求参数
        :return: 临时 Mod 版本列表
        """
        mod_versions: list[dict[str, Any]] = []
        return {"success": True, "data": mod_versions}

    async def download_mod(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        下载在线 Mod
        :param body: 包含 Mod 版本和游戏路径的请求参数
        :return: 临时 Mod 下载结果
        """
        download_result = None
        return {"success": True, "data": download_result}

    # 启动器信息

    async def launcher_info(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取启动器版本信息
        :param body: 前端传递的请求参数
        :return: 临时启动器信息
        """
        launcher_config = self._get_effective_config().get("launcher") or {}
        launcher_data = {
            "version": launcher_config.get("version", ""),
            "version_type": launcher_config.get("version_type", "release"),
            "debug": bool(launcher_config.get("debug", False)),
        }
        return {"success": True, "data": launcher_data}

    async def info_card_get(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取游戏页信息卡数据
        :param body: 前端传递的请求参数
        :return: 后端首页信息服务中的提示和公告
        """
        data = await to_thread.run_sync(self.info_card.get_info_card)
        return {"success": True, "data": data}

    def _schedule_debug_maintenance(self, action: str) -> dict[str, Any]:
        if not bool(self.launcher.debug):
            return {
                "success": False,
                "message": "此操作仅在启动器调试模式下可用",
                "errorCode": "DEBUG_MODE_REQUIRED",
            }
        try:
            result = schedule_debug_maintenance(self.data_path, action)
        except (OSError, TypeError, ValueError) as exc:
            self.logger.exception("安排调试维护操作失败: %s", action)
            return {
                "success": False,
                "message": f"安排维护操作失败: {exc}",
                "errorCode": "DEBUG_MAINTENANCE_FAILED",
            }
        return {"success": True, "data": result}

    async def debug_reset_launcher_data(self, body: dict[str, Any]) -> dict[str, Any]:
        """安排在下次启动时还原启动器数据。"""
        return self._schedule_debug_maintenance("reset_launcher_data")

    async def debug_clear_plugins(self, body: dict[str, Any]) -> dict[str, Any]:
        """安排在下次启动时清理用户插件与插件配置。"""
        return self._schedule_debug_maintenance("clear_plugins")

    async def list_sections(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取启动器可用分区名称
        :param body: 前端传递的请求参数
        :return: 临时分区名称列表
        """
        section_names: list[str] = []
        return {"success": True, "data": section_names}

    # 文件系统

    async def fs_read_dir(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        读取指定目录内容
        :param body: 包含 path 的请求参数
        :return: 临时目录条目列表
        """
        directory_entries: list[dict[str, Any]] = []
        return {"success": True, "data": directory_entries}

    async def fs_read_file(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        读取指定文件内容
        :param body: 包含 path 和可选 mode 的请求参数
        :return: 临时文件内容
        """
        file_data = {"content": "", "size": 0}
        return {"success": True, "data": file_data}

    async def fs_exists(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        检查指定路径是否存在
        :param body: 包含 path 的请求参数
        :return: 临时路径状态
        """
        path_data = {"exists": False, "is_dir": False, "is_file": False}
        return {"success": True, "data": path_data}

    async def file_resolve(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        规整并解析指定文件路径
        :param body: 包含 path 的请求参数
        :return: 临时路径解析结果
        """
        path_data = {"path": ""}
        return {"success": True, "data": path_data}
