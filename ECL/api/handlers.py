import asyncio
import base64
import contextlib
import hashlib
import inspect
import json
import re
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import keyring
import psutil
import pyperclip
import requests

from ..common.env import get_runtime_dir
from ..common.logger import get_logger
from ..common.state import AppState
from ..game.Core import get_avatar_data_url as get_avatar_func
from ..mods.manager import ModManager
from ..mods.pack import ModpackManager
from ..mods.search import OnlineModSearch
from ..resources.manager import ResourceManager

logger = get_logger("api")

_IMAGE_MIME_MAP = {
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".bmp": "image/bmp",
}


def make_json_safe(obj: Any) -> Any:
    if isinstance(obj, Path):
        return str(obj)
    elif isinstance(obj, (set, tuple)):
        return [make_json_safe(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: make_json_safe(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [make_json_safe(item) for item in obj]
    elif isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    else:
        return str(obj)


class Api:
    def __init__(self, state: AppState) -> None:
        self._state = state
        self._config_manager = state.config_manager
        self._account_manager = state.account_manager

    def _get_first_game_path(self) -> str:
        config = self._config_manager.get_game_config()
        paths = config.get("minecraft_paths", [])
        if not paths:
            return self._config_manager._get_default_minecraft_path()
        first = paths[0]
        path = first if isinstance(first, str) else first.get("path", self._config_manager._get_default_minecraft_path())
        return str(Path(path).resolve())

    def config_get(self, section: str) -> dict[str, Any]:
        # 获取指定配置分区
        if section == "game":
            return self.get_game_config()

        cfg = self._config_manager.config
        if not cfg or not isinstance(cfg, list) or len(cfg) == 0:
            return {"success": False, "message": "配置为空", "data": None}
        data = cfg[0].get(section)
        if data is None:
            return {"success": False, "message": f"配置分区 '{section}' 不存在", "data": None}
        return {"success": True, "data": data}

    def config_set(self, section: str, data: dict[str, Any]) -> dict[str, Any]:
        # 设置指定配置分区
        from ..api.events import emit_plugin_event

        cfg = self._config_manager.config
        if not cfg or not isinstance(cfg, list) or len(cfg) == 0:
            cfg = self._config_manager._get_default_config()
            self._config_manager.config = cfg
        old_value = cfg[0].get(section)
        cfg[0][section] = data
        try:
            self._config_manager.save(cfg)
        except OSError as e:
            logger.error(f"config_set 保存失败: {e}")
            return {"success": False, "message": str(e)}
        emit_plugin_event("config:changed", {"section": section, "old_value": old_value, "new_value": data})
        return {"success": True, "message": "配置已保存"}

    def config_get_all(self) -> dict[str, Any]:
        # 获取所有配置
        cfg = self._config_manager.config
        if not cfg or not isinstance(cfg, list) or len(cfg) == 0:
            return {"success": False, "message": "配置为空", "data": None}
        return {"success": True, "data": cfg[0]}

    def config_list(self) -> dict[str, Any]:
        # 列出所有配置分区名称
        cfg = self._config_manager.config
        if not cfg or not isinstance(cfg, list) or len(cfg) == 0:
            return {"success": True, "data": []}
        return {"success": True, "data": list(cfg[0].keys())}

    def config_get_many(self, sections: list[str]) -> dict[str, Any]:
        # 批量获取多个配置分区
        cfg = self._config_manager.config
        if not cfg or not isinstance(cfg, list) or len(cfg) == 0:
            return {"success": False, "message": "配置为空", "data": None}
        result = {section: cfg[0].get(section) for section in sections}
        return {"success": True, "data": result}

    def __dir__(self) -> list[str]:
        return [
            "config_get",
            "config_set",
            "config_get_all",
            "config_get_many",
            "config_list",
            "minimize_window",
            "close_window",
            "get_window_position",
            "set_window_position",
            "get_launcher_config",
            "get_background_config",
            "get_background_image",
            "update_background_config",
            "update_background_image",
            "load_image_from_url",
            "fetch_image_data_url",
            "get_avatar_data_url",
            "load_image_from_local",
            "select_local_image",
            "select_file",
            "get_game_config",
            "update_game_config",
            "get_java_list",
            "get_theme_config",
            "update_theme_config",
            "get_download_config",
            "update_download_config",
            "get_locale_config",
            "update_locale_config",
            "select_directory",
            "select_java_executable",
            "scan_versions_in_path",
            "get_minecraft_versions",
            "get_fabric_versions",
            "get_forge_versions",
            "get_neoforge_versions",
            "get_optifine_versions",
            "get_quilt_versions",
            "install_version",
            "uninstall_version",
            "ping",
            "get_user_agreement_status",
            "save_user_agreement",
            "clear_user_agreement",
            "get_accounts",
            "get_current_account",
            "add_offline_account",
            "start_microsoft_login",
            "poll_microsoft_login",
            "complete_microsoft_login",
            "switch_account",
            "remove_account",
            "refresh_account_profile",
            "add_authlib_account",
            "get_authlib_servers",
            "get_game_instances",
            "launch_instance",
            "get_launch_status",
            "stop_instance",
            "set_master_password",
            "get_keyring_info",
            "clear_keyring",
            "plugin_list",
            "plugin_info",
            "plugin_enable",
            "plugin_disable",
            "plugin_unload",
            "plugin_reload",
            "plugin_install",
            "plugin_get_settings",
            "plugin_update_setting",
            "plugin_get_routes",
            "plugin_call_command",
            "plugin_get_slots",
            "search_mods",
            "get_mod_info",
            "get_mod_versions",
            "download_mod",
            "frontend_ready",
        ]

    def ping(self) -> dict[str, Any]:
        return {"success": True, "data": {"status": "ok", "message": "API连接正常"}, "message": "Pong"}

    def frontend_ready(self) -> dict[str, Any]:
        from ..api.events import emit

        # 推送完整配置
        config = self._state.config_manager.config[0]
        emit("config:init", {
            "launcher": config.get("launcher", {}),
            "game": config.get("game", {}),
            "download": config.get("download", {}),
            "ui": config.get("ui", {}),
        })

        # 推送版本提醒
        cfg = config.get("launcher", {})
        version = cfg.get("version", "未知")
        version_type = cfg.get("version_type", "unknown")
        if version_type == "dev":
            emit("launcher:notify", {
                "type": "warning",
                "title": "开发版本提醒",
                "message": f"当前运行的是开发版本 v{version}，可能存在不稳定因素",
            })
        elif version_type == "beta":
            emit("launcher:notify", {
                "type": "info",
                "title": "测试版本提醒",
                "message": f"当前运行的是测试版本 v{version}，可能存在一些问题",
            })

        # 推送主密码需求
        auth = getattr(self._state.account_manager, "_auth", None)
        encryption = getattr(auth, "encryption", None) if auth else None
        if encryption is not None and getattr(encryption, "needs_password", lambda: False)():
            emit("keyring:password_required", {})

        # 推送用户协议检查
        core_dir = self._state.config_manager.config_path.parent / "ECL_Libs"
        agreement_file = core_dir / "user_agreement.json"
        if not agreement_file.exists():
            emit("launcher:agreement_required", {})
        else:
            try:
                with agreement_file.open(encoding="utf-8") as f:
                    data = json.load(f)
                if not data.get("accepted", False):
                    emit("launcher:agreement_required", {})
            except (OSError, ValueError):
                emit("launcher:agreement_required", {})

        # 触发插件前端就绪
        fw = self._state.plugin_framework
        if fw is not None:
            try:
                fw.fire_frontend_ready()
            except (RuntimeError, OSError, ValueError, TypeError) as e:
                logger.error(f"触发前端就绪事件失败: {e}")
        return {"success": True}

    def get_user_agreement_status(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            core_dir = self._state.config_manager.config_path.parent / "ECL_Libs"
            agreement_file = core_dir / "user_agreement.json"
            if agreement_file.exists():
                with agreement_file.open(encoding="utf-8") as f:
                    data = json.load(f)
                return {
                    "success": True,
                    "data": {"accepted": data.get("accepted", False), "uuid": data.get("uuid", "")},
                    "message": "获取用户协议状态成功",
                }
            return {"success": True, "data": {"accepted": False, "uuid": ""}, "message": "用户协议未同意"}
        except (json.JSONDecodeError, OSError, KeyError, ValueError) as e:
            logger.error(f"获取用户协议状态失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def save_user_agreement(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            core_dir = self._state.config_manager.config_path.parent / "ECL_Libs"
            agreement_file = core_dir / "user_agreement.json"
            agreement_file.parent.mkdir(parents=True, exist_ok=True)
            data = kwargs.get("data")
            if data is None and args:
                data = args[0] if isinstance(args[0], dict) else None
            data = data or {"accepted": True, "uuid": str(uuid.uuid4())}
            with agreement_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            from ..api.events import emit_plugin_event

            emit_plugin_event("user:agreed", {"uuid": data.get("uuid", "")})
            return {"success": True, "data": data, "message": "用户协议已保存"}
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as e:
            logger.error(f"保存用户协议失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def clear_user_agreement(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            core_dir = self._state.config_manager.config_path.parent / "ECL_Libs"
            agreement_file = core_dir / "user_agreement.json"
            if agreement_file.exists():
                agreement_file.unlink()
            return {"success": True, "message": "用户协议已清除"}
        except (OSError, PermissionError) as e:
            logger.error(f"清除用户协议失败: {e}")
            return {"success": False, "message": str(e)}

    def minimize_window(self) -> dict[str, Any]:
        return {"success": False, "message": "窗口控制功能待对接（建议通过前端 Tauri API 实现）"}

    def close_window(self) -> dict[str, Any]:
        return {"success": False, "message": "窗口控制功能待对接（建议通过前端 Tauri API 实现）"}

    def get_window_position(self) -> dict[str, Any]:
        return {"success": False, "message": "窗口控制功能待对接（建议通过前端 Tauri API 实现）", "data": None}

    def set_window_position(self, x: int, y: int) -> dict[str, Any]:
        return {"success": False, "message": "窗口控制功能待对接（建议通过前端 Tauri API 实现）", "data": None}

    def get_launcher_config(self) -> dict[str, Any]:
        config = self._config_manager.get_launcher_config()
        return {"success": True, "data": config, "message": "获取成功"}

    def get_background_config(self) -> dict[str, Any]:
        config = self._config_manager.get_background_config()
        return {"success": True, "data": config, "message": "获取成功"}

    def get_background_image(self) -> dict[str, Any]:
        config = self._config_manager.get_background_config()
        path_str = config.get("path", "")

        if not path_str:
            return {"success": False, "message": "未设置背景图", "data": None}

        path = Path(path_str)
        if not path.exists():
            logger.error(f"[get_background_image] 文件不存在: {path}")
            return {"success": False, "message": f"背景图文件不存在: {path_str}", "data": None}

        try:
            image_data = path.read_bytes()
        except (OSError, PermissionError) as e:
            logger.error(f"[get_background_image] 读取文件失败: {e}")
            return {"success": False, "message": f"读取背景图文件失败: {e}", "data": None}

        mime_type = _IMAGE_MIME_MAP.get(path.suffix.lower(), "image/jpeg")
        base64_data = base64.b64encode(image_data).decode("utf-8")

        return {
            "success": True,
            "data": {
                "base64": f"data:{mime_type};base64,{base64_data}",
                "path": str(path).replace("\\", "/"),
                "type": config.get("type", "local"),
            },
            "message": "获取成功",
        }

    def update_background_config(self, background_config: dict[str, Any]) -> dict[str, Any]:
        if background_config.get("type") == "local" and background_config.get("path"):
            path = Path(background_config["path"])
            if path.exists():
                try:
                    background_config["image_base64"] = base64.b64encode(path.read_bytes()).decode("utf-8")
                except (OSError, PermissionError) as e:
                    logger.error(f"读取背景图失败: {e}")
                    return {"success": False, "message": str(e)}

        try:
            self._config_manager.update_background_config(background_config)
        except OSError as e:
            logger.error(f"更新背景图配置失败: {e}")
            return {"success": False, "message": str(e)}

        logger.info(f"背景图配置已更新: {background_config.get('type')}")

        if "blur" in background_config:
            current_theme = self._config_manager.get_theme_config()
            current_theme["blur_amount"] = background_config["blur"]
            self._config_manager.update_theme_config(current_theme)
            logger.info(f"同步背景模糊值到主题配置: {background_config['blur']}")

        return {"success": True, "message": "背景图更新成功"}

    def update_background_image(self, image_type: str, image_path: str) -> dict[str, Any]:
        return self.update_background_config({"type": image_type, "path": image_path, "opacity": 0.8, "blur": 0})

    def load_image_from_url(self, url: str) -> dict[str, Any]:
        try:
            logger.info(f"[load_image_from_url] 开始下载图片: {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            logger.info(f"[load_image_from_url] Content-Type: {content_type}")
            if not content_type.startswith("image/"):
                return {"success": False, "message": "URL不是图片类型", "data": None}

            ext = content_type.split("/")[-1] if "/" in content_type else "jpg"

            app_dir = get_runtime_dir()

            background_dir = app_dir / "ECL_Libs" / "backgrounds"
            background_dir.mkdir(exist_ok=True)
            logger.info(f"[load_image_from_url] 背景图目录: {background_dir}")

            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            file_path = background_dir / f"bg_{url_hash}.{ext}"
            logger.info(f"[load_image_from_url] 保存路径: {file_path}")

            file_path.write_bytes(response.content)

            abs_path = str(file_path.resolve()).replace("\\", "/")
            logger.info(f"[load_image_from_url] 成功: {abs_path} ({len(response.content)} bytes)")

            return {"success": True, "data": {"path": abs_path}, "message": "图片下载成功"}
        except (requests.RequestException, OSError, ValueError) as e:
            logger.error(f"加载网络图片失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def fetch_image_data_url(self, url: str) -> dict[str, Any]:
        try:
            logger.info(f"[fetch_image_data_url] 开始下载图片: {url}")

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "image",
                "Sec-Fetch-Mode": "no-cors",
                "Sec-Fetch-Site": "cross-site",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            }

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    logger.info(f"[fetch_image_data_url] 第 {attempt + 1} 次尝试")
                    response = requests.get(url, timeout=15, headers=headers)
                    response.raise_for_status()

                    content_type = response.headers.get("content-type", "")
                    logger.info(f"[fetch_image_data_url] Content-Type: {content_type}")

                    if not content_type.startswith("image/"):
                        if "text/html" in content_type:
                            logger.warning(
                                f"[fetch_image_data_url] 收到 HTML 响应，可能被 Cloudflare 拦截: {response.text[:200]}..."
                            )
                            if attempt < max_retries - 1:
                                logger.info(f"[fetch_image_data_url] {2**attempt} 秒后重试...")
                                time.sleep(2**attempt)
                                continue
                        return {"success": False, "message": f"URL不是图片类型: {content_type}", "data": None}

                    if len(response.content) < 100:
                        logger.warning(f"[fetch_image_data_url] 图片数据过小: {len(response.content)} bytes")
                        if attempt < max_retries - 1:
                            logger.info(f"[fetch_image_data_url] {2**attempt} 秒后重试...")
                            time.sleep(2**attempt)
                            continue
                        return {"success": False, "message": "图片数据不完整", "data": None}

                    data_url = f"data:{content_type};base64,{base64.b64encode(response.content).decode('utf-8')}"
                    logger.info(f"[fetch_image_data_url] 成功获取图片 ({len(response.content)} bytes)")
                    return {"success": True, "message": "图片代理获取成功", "data": {"dataUrl": data_url}}

                except requests.exceptions.HTTPError as http_err:
                    status_code = http_err.response.status_code if http_err.response else None
                    error_msg = str(http_err)
                    logger.warning(f"[fetch_image_data_url] HTTP 错误 {status_code}: {error_msg}")

                    is_5xx_error = False
                    if status_code and 500 <= status_code < 600:
                        is_5xx_error = True
                    elif status_code is None and ("5" in error_msg and "Server Error" in error_msg):
                        match = re.search(r"(\d{3})\s+Server Error", error_msg)
                        if match and 500 <= int(match.group(1)) < 600:
                            is_5xx_error = True

                    if is_5xx_error and attempt < max_retries - 1:
                        logger.info(f"[fetch_image_data_url] 服务器错误，{2**attempt} 秒后重试...")
                        time.sleep(2**attempt)
                        continue

                    return {"success": False, "message": f"HTTP 错误 {status_code}: {error_msg}", "data": None}

                except requests.exceptions.RequestException as req_err:
                    logger.warning(f"[fetch_image_data_url] 请求异常: {req_err}")
                    if attempt < max_retries - 1:
                        logger.info(f"[fetch_image_data_url] {2**attempt} 秒后重试...")
                        time.sleep(2**attempt)
                        continue
                    return {"success": False, "message": f"网络请求失败: {req_err!s}", "data": None}

            return {"success": False, "message": f"重试 {max_retries} 次后仍失败", "data": None}

        except (ValueError, OSError, requests.RequestException) as e:
            logger.error(f"代理获取图片失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def get_avatar_data_url(
        self,
        uuid: str,
        type_name: str = "Mojang",
        custom_server: str | None = None,
        size: int = 64,
        use_default_skin: bool = False,
        avatar_type: str = "head",
    ) -> dict[str, Any]:
        try:
            data_url = get_avatar_func(uuid, type_name, custom_server, size, use_default_skin, avatar_type)
            return {"success": True, "message": "头像生成成功", "data": {"dataUrl": data_url}}
        except ImportError as e:
            logger.error(f"[get_avatar_data_url] PIL 库未安装: {e}")
            return {"success": False, "message": "PIL (Pillow) 库未安装，无法处理头像", "data": None}
        except (OSError, ValueError, RuntimeError) as e:
            logger.error(f"[get_avatar_data_url] 生成头像失败: {e}")
            return {"success": False, "message": f"头像生成失败: {e!s}", "data": None}

    def load_image_from_local(self, path: str) -> dict[str, Any]:
        path_obj = Path(path)
        if not path_obj.exists():
            return {"success": False, "message": f"文件不存在: {path}", "data": None}

        valid_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
        if path_obj.suffix.lower() not in valid_extensions:
            return {"success": False, "message": f"不支持的图片格式: {path_obj.suffix}", "data": None}

        try:
            file_bytes = path_obj.read_bytes()
        except OSError as e:
            logger.error(f"读取图片文件失败: {e}")
            return {"success": False, "message": str(e), "data": None}

        base64_data = base64.b64encode(file_bytes).decode("utf-8")
        mime = _IMAGE_MIME_MAP.get(path_obj.suffix.lower(), "image/png")
        data_url = f"data:{mime};base64,{base64_data}"

        return {
            "success": True,
            "data": {"path": str(path_obj.absolute()), "base64": data_url},
            "message": "图片加载成功",
        }

    def _pick_file(self, title: str, filetypes: list[tuple[str, str]] | None = None) -> dict[str, Any]:
        from pytauri_plugins.dialog import DialogExt

        from ..adapters.adapter import get_app_handle_obj

        app_handle = get_app_handle_obj()
        if app_handle is None:
            return {"success": False, "message": "AppHandle 未初始化", "data": None}
        kwargs: dict[str, Any] = {"set_title": title}
        if filetypes:
            for name, pattern in filetypes:
                if name == "All files" or pattern == "*.*":
                    continue
                exts = []
                for ext in pattern.split(";"):
                    ext = ext.strip()
                    if not ext or ext == "*.*" or ext == "*":
                        continue
                    if ext.startswith("*."):
                        ext = ext[2:]
                    if ext:
                        exts.append(ext)
                if exts:
                    kwargs["add_filter"] = (name, exts)
                    break
        try:
            builder = DialogExt.file(app_handle)
            result = builder.blocking_pick_file(**kwargs)
        except (RuntimeError, OSError, ValueError) as e:
            logger.error(f"文件对话框失败: {e}")
            return {"success": False, "message": str(e), "data": None}
        if result is None:
            return {"success": False, "message": "用户取消选择", "data": None}
        return {"success": True, "data": {"path": str(result)}, "message": "选择成功"}

    def select_local_image(self) -> dict[str, Any]:
        result = self._pick_file(
            "选择图片",
            [("Image files", "*.jpg;*.jpeg;*.png;*.gif;*.webp"), ("All files", "*.*")],
        )
        if result["success"]:
            return self.load_image_from_local(result["data"]["path"])
        return result

    def select_file(self) -> dict[str, Any]:
        """选择文件（通用，用于导入 Mod 等）"""
        return self._pick_file(
            "选择文件",
            [("JAR files", "*.jar"), ("ZIP files", "*.zip"), ("All files", "*.*")],
        )

    def get_game_config(self) -> dict[str, Any]:
        config = self._config_manager.get_game_config()

        if "minecraft_paths" not in config:
            if "minecraft_path" in config and isinstance(config["minecraft_path"], str):
                config["minecraft_paths"] = [
                    {"name": "默认路径", "path": config.pop("minecraft_path"), "protected": True}
                ]
            else:
                default_path = self._config_manager._get_default_minecraft_path()
                config["minecraft_paths"] = [{"name": "默认路径", "path": default_path, "protected": True}]

        formatted_paths = []
        default_path = self._config_manager._get_default_minecraft_path()
        for i, p in enumerate(config["minecraft_paths"]):
            if isinstance(p, dict):
                path_obj = {"name": p.get("name", f"路径{i + 1}"), "path": p.get("path", "")}
            else:
                path_obj = {"name": f"路径{i + 1}", "path": p}

            if path_obj["path"] == default_path:
                path_obj["name"] = "默认路径"

            formatted_paths.append(path_obj)

        config["minecraft_paths"] = formatted_paths

        return {"success": True, "data": config, "message": "获取成功"}

    def update_game_config(self, game_config: dict[str, Any]) -> dict[str, Any]:
        if "minecraft_paths" in game_config:
            paths = game_config["minecraft_paths"]
            default_path = self._config_manager._get_default_minecraft_path()
            has_default = any(
                (p.get("path", "") if isinstance(p, dict) else p) == default_path
                for p in paths
            )
            if not has_default:
                logger.warning("检测到默认路径被删除，自动恢复")
                paths.insert(0, {"name": "默认路径", "path": default_path, "protected": True})

        try:
            self._config_manager.update_game_config(game_config)
        except OSError as e:
            logger.error(f"更新游戏配置失败: {e}")
            return {"success": False, "message": str(e)}
        return {"success": True, "message": "游戏配置更新成功"}

    def get_java_list(self) -> dict[str, Any]:
        java_dicts = self._state.get_java_dicts()
        if not java_dicts:
            return {"success": True, "data": [], "message": "未找到Java安装"}
        return {"success": True, "data": java_dicts, "message": f"找到 {len(java_dicts)} 个Java安装"}

    def get_theme_config(self) -> dict[str, Any]:
        config = self._config_manager.get_theme_config()
        return {"success": True, "data": config, "message": "获取成功"}

    def update_theme_config(self, theme_config: dict[str, Any]) -> dict[str, Any]:
        self._config_manager.update_theme_config(theme_config)
        return {"success": True, "message": "主题配置更新成功"}

    def get_download_config(self) -> dict[str, Any]:
        config = self._config_manager.get_download_config()
        return {"success": True, "data": config, "message": "获取成功"}

    def update_download_config(self, download_config: dict[str, Any]) -> dict[str, Any]:
        self._config_manager.update_download_config(download_config)
        return {"success": True, "message": "下载配置更新成功"}

    def get_locale_config(self) -> dict[str, Any]:
        config = self._config_manager.get_locale_config()
        return {"success": True, "data": config, "message": "获取成功"}

    def update_locale_config(self, locale: str) -> dict[str, Any]:
        try:
            self._config_manager.update_locale_config(locale)
        except OSError as e:
            logger.error(f"更新语言配置失败: {e}")
            return {"success": False, "message": str(e)}
        return {"success": True, "message": "语言配置更新成功"}

    def select_directory(self) -> dict[str, Any]:
        from pytauri_plugins.dialog import DialogExt

        from ..adapters.adapter import get_app_handle_obj

        app_handle = get_app_handle_obj()
        if app_handle is None:
            return {"success": False, "message": "AppHandle 未初始化", "data": None}
        try:
            builder = DialogExt.file(app_handle)
            result = builder.blocking_pick_folder(set_title="选择目录")
        except (RuntimeError, OSError, ValueError) as e:
            logger.error(f"目录对话框失败: {e}")
            return {"success": False, "message": str(e), "data": None}
        if result is None:
            return {"success": False, "message": "用户取消选择", "data": None}
        return {"success": True, "data": {"path": str(result)}, "message": "选择成功"}

    def select_java_executable(self) -> dict[str, Any]:
        result = self._pick_file(
            "选择 Java 可执行文件",
            [("Java Executable", "*.exe;java"), ("All files", "*.*")],
        )
        if result.get("success") and result.get("data", {}).get("path"):
            from ..api.events import emit_plugin_event

            emit_plugin_event("java:selected", {"path": result["data"]["path"]})
        return result

    def scan_versions_in_path(self, path: str | list[str] | list[dict[str, str]]) -> dict[str, Any]:
        try:
            paths = path if isinstance(path, list) else [path]
            # 路径去重
            raw_paths = [p.get("path", "") if isinstance(p, dict) else p for p in paths]
            unique_paths = list(dict.fromkeys(raw_paths))
            scan_results = []
            seen_ids = set()
            for p in unique_paths:
                versions_dir = Path(p) / "versions"
                if not versions_dir.is_dir():
                    continue
                for vjson in versions_dir.glob("*/*.json"):
                    try:
                        folder_name = vjson.parent.name
                        data = json.loads(vjson.read_text("utf-8"))
                        inherits_from = data.get("inheritsFrom")
                        json_id = data.get("id", folder_name)
                        vanilla_version = data.get("vanillaVersion")  # 合并后的 JSON 标记

                        # 判断 mod loader 类型
                        primary_loader = "vanilla"
                        has_forge = has_neoforge = has_fabric = has_quilt = False
                        jar_name_lower = json_id.lower()
                        if "forge" in jar_name_lower:
                            primary_loader = "forge"
                            has_forge = True
                        elif "neoforge" in jar_name_lower:
                            primary_loader = "neoforge"
                            has_neoforge = True
                        elif "fabric" in jar_name_lower:
                            primary_loader = "fabric"
                            has_fabric = True
                        elif "quilt" in jar_name_lower:
                            primary_loader = "quilt"
                            has_quilt = True
                        elif inherits_from:
                            inh_lower = inherits_from.lower()
                            if "forge" in inh_lower:
                                primary_loader = "forge"
                                has_forge = True
                            elif "neoforge" in inh_lower:
                                primary_loader = "neoforge"
                                has_neoforge = True
                            elif "fabric" in inh_lower:
                                primary_loader = "fabric"
                                has_fabric = True
                            elif "quilt" in inh_lower:
                                primary_loader = "quilt"
                                has_quilt = True

                        if primary_loader != "vanilla":
                            if inherits_from:
                                # 有 inheritsFrom：检查继承的原版 JAR
                                vanilla_jar = versions_dir / inherits_from / (inherits_from + ".jar")
                                is_broken = not vanilla_jar.exists()
                            else:
                                # 合并后的 JSON（无 inheritsFrom）：JAR 在自身文件夹内
                                jar_path = vjson.parent / (folder_name + ".jar")
                                is_broken = not jar_path.exists()
                        else:
                            # 原版：检查自身 JAR
                            jar_path = vjson.parent / (folder_name + ".jar")
                            is_broken = not jar_path.exists()

                        if json_id in seen_ids:
                            continue
                        seen_ids.add(json_id)
                        scan_results.append(
                            {
                                "id": json_id,
                                "versionId": json_id,
                                "displayName": data.get("displayName", json_id),
                                "primaryLoader": primary_loader,
                                "vanillaName": inherits_from or vanilla_version or json_id,
                                "hasForge": has_forge,
                                "hasNeoForge": has_neoforge,
                                "hasFabric": has_fabric,
                                "hasQuilt": has_quilt,
                                "isBroken": is_broken,
                                "jsonPath": str(vjson),
                            }
                        )
                    except (OSError, ValueError):
                        continue
            from ..api.events import emit_plugin_event

            emit_plugin_event(
                "version:scanned", {"count": len(scan_results), "versions": [v["id"] for v in scan_results]}
            )

            return {"success": True, "data": scan_results}
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as e:
            logger.error(f"扫描版本失败: {e}")
            return {"success": False, "message": str(e), "data": []}

    def get_minecraft_versions(self, filter_type: str | None = None) -> dict[str, Any]:
        try:
            result = self._state.get_games.get_minecraft_versions()
            if result is None:
                return {"success": False, "message": "获取版本列表失败", "data": None}

            # 扁平化为前端期望的数组格式 {id, type, releaseTime}
            # 注意: GetGames 返回的是 Mojang API 原始数据，字段名为小写
            versions = []
            type_map = {
                "Release": "release",
                "Snapshot": "snapshot",
                "Beta": "old_beta",
                "Alpha": "old_alpha",
                "FoolDays": "april_fools",
            }
            for key, mapped_type in type_map.items():
                for v in result.get(key, []):
                    vid = v.get("id")
                    if not vid:
                        continue
                    versions.append(
                        {
                            "id": vid,
                            "type": mapped_type,
                            "releaseTime": v.get("releaseTime"),
                        }
                    )

            if filter_type and filter_type != "all":
                versions = [v for v in versions if v["type"] == filter_type]

            return {"success": True, "data": versions}
        except (requests.RequestException, KeyError, TypeError, ValueError) as e:
            logger.error(f"获取版本列表失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def get_fabric_versions(self, game_version: str | None = None) -> dict[str, Any]:
        if not game_version:
            return {"success": True, "data": {"all": [], "stable": [], "unstable": []}}
        try:
            # 若缓存命中且版本号匹配，直接返回
            cached = self._state.get_games._cached_fabric_versions
            if cached and cached.get("_game_version") == game_version:
                return {
                    "success": True,
                    "data": {
                        "all": cached.get("All", []),
                        "stable": cached.get("Stable", []),
                        "unstable": cached.get("NotStable", []),
                    },
                }
            result = self._state.get_games.get_fabric_versions(game_version)
            if result is None:
                # 可能是版本号不被 Fabric 支持（如远古版本），返回空列表不算失败
                return {"success": True, "data": {"all": [], "stable": [], "unstable": []}}
            data = {
                "all": result.get("All", []),
                "stable": result.get("Stable", []),
                "unstable": result.get("NotStable", []),
            }
            return {"success": True, "data": data}
        except (requests.RequestException, KeyError, TypeError, ValueError) as e:
            logger.error(f"获取 Fabric 版本列表失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def get_forge_versions(self, game_version: str | None = None) -> dict[str, Any]:
        """获取指定 Minecraft 版本对应的 Forge 加载器版本列表。"""
        if not game_version:
            return {"success": True, "data": {"all": [], "stable": [], "unstable": []}}
        try:
            cached = self._state.get_games._cached_forge_versions
            if cached and cached.get("_game_version") == game_version:
                return {
                    "success": True,
                    "data": {
                        "all": cached.get("All", []),
                        "stable": cached.get("Stable", []),
                        "unstable": cached.get("NotStable", []),
                    },
                }
            result = self._state.get_games.get_forge_versions(game_version)
            if result is None:
                return {"success": True, "data": {"all": [], "stable": [], "unstable": []}}
            # 标记缓存对应的游戏版本
            result["_game_version"] = game_version
            data = {
                "all": result.get("All", []),
                "stable": result.get("Stable", []),
                "unstable": result.get("NotStable", []),
            }
            return {"success": True, "data": data}
        except (requests.RequestException, KeyError, TypeError, ValueError) as e:
            logger.error(f"获取 Forge 版本列表失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def get_neoforge_versions(self, game_version: str | None = None) -> dict[str, Any]:
        """获取指定 Minecraft 版本对应的 NeoForge 加载器版本列表。"""
        if not game_version:
            return {"success": True, "data": {"all": [], "stable": [], "unstable": []}}
        try:
            cached = self._state.get_games._cached_neoforge_versions
            if cached and cached.get("_game_version") == game_version:
                return {
                    "success": True,
                    "data": {
                        "all": cached.get("All", []),
                        "stable": cached.get("Stable", []),
                        "unstable": cached.get("NotStable", []),
                    },
                }
            result = self._state.get_games.get_neoforge_versions(game_version)
            if result is None:
                return {"success": True, "data": {"all": [], "stable": [], "unstable": []}}
            result["_game_version"] = game_version
            data = {
                "all": result.get("All", []),
                "stable": result.get("Stable", []),
                "unstable": result.get("NotStable", []),
            }
            return {"success": True, "data": data}
        except (requests.RequestException, KeyError, TypeError, ValueError) as e:
            logger.error(f"获取 NeoForge 版本列表失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def get_optifine_versions(self, game_version: str | None = None) -> dict[str, Any]:
        """获取指定 Minecraft 版本对应的 OptiFine 版本列表。"""
        if not game_version:
            return {"success": True, "data": {"all": [], "stable": [], "unstable": []}}
        try:
            cached = self._state.get_games._cached_optifine_versions
            if cached and cached.get("_game_version") == game_version:
                return {
                    "success": True,
                    "data": {
                        "all": cached.get("All", []),
                        "stable": cached.get("Stable", []),
                        "unstable": cached.get("NotStable", []),
                    },
                }
            result = self._state.get_games.get_optifine_versions(game_version)
            if result is None:
                return {"success": True, "data": {"all": [], "stable": [], "unstable": []}}
            result["_game_version"] = game_version
            data = {
                "all": result.get("All", []),
                "stable": result.get("Stable", []),
                "unstable": result.get("NotStable", []),
            }
            return {"success": True, "data": data}
        except (requests.RequestException, KeyError, TypeError, ValueError) as e:
            logger.error(f"获取 OptiFine 版本列表失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def get_quilt_versions(self, game_version: str | None = None) -> dict[str, Any]:
        """获取指定 Minecraft 版本对应的 Quilt 加载器版本列表。"""
        if not game_version:
            return {"success": True, "data": {"all": [], "stable": [], "unstable": []}}
        try:
            cached = self._state.get_games._cached_quilt_versions
            if cached and cached.get("_game_version") == game_version:
                return {
                    "success": True,
                    "data": {
                        "all": cached.get("All", []),
                        "stable": cached.get("Stable", []),
                        "unstable": cached.get("NotStable", []),
                    },
                }
            result = self._state.get_games.get_quilt_versions(game_version)
            if result is None:
                return {"success": True, "data": {"all": [], "stable": [], "unstable": []}}
            result["_game_version"] = game_version
            data = {
                "all": result.get("All", []),
                "stable": result.get("Stable", []),
                "unstable": result.get("NotStable", []),
            }
            return {"success": True, "data": data}
        except (requests.RequestException, KeyError, TypeError, ValueError) as e:
            logger.error(f"获取 Quilt 版本列表失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    async def install_version(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        version_id = params.get("version_id", "")
        version_name = params.get("version_name", version_id)
        loader_type = params.get("loader_type", "vanilla")
        task_id = params.get("task_id", "")
        fabric_version = params.get("fabric_version")
        forge_version = params.get("forge_version")
        neoforge_version = params.get("neoforge_version")
        optifine_version = params.get("optifine_version")
        optifine_type = params.get("optifine_type", "")
        optifine_patch = params.get("optifine_patch", "")
        quilt_version = params.get("quilt_version")
        game_path = params.get("game_path")
        download_threads = params.get("download_threads", 32)

        logger.info(
            f"[install] params: version_id={version_id}, loader={loader_type}, "
            f"fabric={fabric_version}, forge={forge_version}, neoforge={neoforge_version}, "
            f"quilt={quilt_version}, name={version_name}, path={game_path}"
        )

        if not version_id:
            return {"success": False, "message": "缺少 version_id 参数"}

        if not game_path:
            game_path = self._get_first_game_path()

        try:
            from ..api.events import emit, emit_plugin_event

            # 设置当前安装任务 ID，下载回调会携带到进度事件中
            if task_id:
                self._state._current_install_task["task_id"] = task_id

            def _emit_progress(phase, done=0, total=1, message="", subtask=""):
                payload = {"phase": phase, "done": done, "total": total, "message": message}
                if task_id:
                    payload["task_id"] = task_id
                if subtask:
                    payload["subtask"] = subtask
                emit("game:install_progress", payload)

            # 插件事件：下载开始
            emit_plugin_event("download:start", {"task_id": version_id, "total_size": 0})

            if loader_type == "fabric" and fabric_version:
                logger.info(f"[install] → download_fabric({version_id}, {fabric_version})")
                _emit_progress("install", 0, 2, f"安装 Fabric {fabric_version} for {version_id}", "download_json")
                ok = await asyncio.to_thread(
                    self._state.get_games.download_fabric,
                    game_path=game_path,
                    game_version_id=version_id,
                    fabric_version=fabric_version,
                    save_version_name=version_name,
                    download_max_thread=download_threads,
                )
            elif loader_type == "forge" and forge_version:
                logger.info(f"[install] → download_forge({version_id}, {forge_version})")
                _emit_progress("install", 0, 2, f"安装 Forge {forge_version} for {version_id}", "download_json")
                ok = await asyncio.to_thread(
                    self._state.get_games.download_forge,
                    game_path=game_path,
                    game_version_id=version_id,
                    forge_version=forge_version,
                    save_version_name=version_name,
                    download_max_thread=download_threads,
                )
            elif loader_type == "neoforge" and neoforge_version:
                logger.info(f"[install] → download_neoforge({version_id}, {neoforge_version})")
                _emit_progress("install", 0, 2, f"安装 NeoForge {neoforge_version} for {version_id}", "download_json")
                ok = await asyncio.to_thread(
                    self._state.get_games.download_neoforge,
                    game_path=game_path,
                    game_version_id=version_id,
                    neoforge_version=neoforge_version,
                    save_version_name=version_name,
                    download_max_thread=download_threads,
                )
            elif loader_type == "optifine" and optifine_version:
                logger.info(f"[install] → download_optifine({version_id}, {optifine_version})")
                _emit_progress("install", 0, 2, f"安装 OptiFine {optifine_version} for {version_id}", "download_json")
                ok = await asyncio.to_thread(
                    self._state.get_games.download_optifine,
                    game_path=game_path,
                    game_version_id=version_id,
                    optifine_version=optifine_version,
                    optifine_type=optifine_type,
                    optifine_patch=optifine_patch,
                    save_version_name=version_name,
                    download_max_thread=download_threads,
                )
            elif loader_type == "quilt" and quilt_version:
                logger.info(f"[install] → download_quilt({version_id}, {quilt_version})")
                _emit_progress("install", 0, 2, f"安装 Quilt {quilt_version} for {version_id}", "download_json")
                ok = await asyncio.to_thread(
                    self._state.get_games.download_quilt,
                    game_path=game_path,
                    game_version_id=version_id,
                    quilt_version=quilt_version,
                    save_version_name=version_name,
                    download_max_thread=download_threads,
                )
            else:
                logger.info(f"[install] → download_minecraft vanilla ({version_id}), no loader version matched")
                _emit_progress("install", 0, 1, f"下载原版 {version_id}", "download_json")
                ok = await asyncio.to_thread(
                    self._state.get_games.download_minecraft,
                    game_path=game_path,
                    version_id=version_id,
                    save_version_name=version_name,
                    download_max_thread=download_threads,
                )

            logger.info(f"[install] result: ok={ok}")
            if ok:
                _emit_progress("done", 1, 1, "安装完成")
                emit_plugin_event("download:complete", {"task_id": version_id})
                emit_plugin_event("version:installed", {"version_id": version_id, "loader_type": loader_type})
                return {"success": True, "message": f"版本 {version_id} 安装成功"}
            _emit_progress("error", 0, 1, f"版本 {version_id} 安装失败")
            emit_plugin_event("download:error", {"task_id": version_id, "error": "安装失败"})
            return {"success": False, "message": f"版本 {version_id} 安装失败"}
        except (OSError, ValueError, RuntimeError, asyncio.CancelledError) as e:
            logger.error(f"安装版本失败: {e}")
            if task_id:
                emit("game:install_progress", {"phase": "error", "task_id": task_id, "message": str(e)})
            emit_plugin_event("download:error", {"task_id": version_id, "error": str(e)})
            return {"success": False, "message": str(e)}

    def uninstall_version(self, version_id: str, game_path: str | None = None) -> dict[str, Any]:
        from shutil import rmtree

        from ..api.events import emit_plugin_event

        if not game_path:
            game_path = self._get_first_game_path()

        game_path = Path(game_path)
        version_dir = game_path / "versions" / version_id

        if not version_dir.exists():
            return {"success": False, "message": "版本不存在"}

        try:
            rmtree(version_dir)
        except OSError as e:
            logger.error(f"卸载版本失败: {e}")
            return {"success": False, "message": str(e)}
        logger.info(f"版本 {version_id} 已卸载")
        emit_plugin_event("version:uninstalled", {"version_id": version_id})

        return {"success": True, "message": f"版本 {version_id} 已卸载"}

    def get_accounts(self) -> dict[str, Any]:
        accounts = self._account_manager.get_all_accounts()
        current = self._account_manager.get_current_account()
        return {
            "success": True,
            "data": {"accounts": accounts, "current": current},
            "message": f"获取到 {len(accounts)} 个账户",
        }

    def get_current_account(self) -> dict[str, Any]:
        current = self._account_manager.get_current_account()
        return {"success": True, "data": current, "message": "获取当前账户成功" if current else "未选择账户"}

    def add_offline_account(self, username: str) -> dict[str, Any]:
        from ..api.events import emit_plugin_event

        try:
            result = self._account_manager.add_offline_account(username)
        except (ValueError, RuntimeError) as e:
            logger.error(f"添加离线账户失败: {e}")
            return {"success": False, "message": str(e)}
        emit_plugin_event("account:login", {"account_type": "offline", "player_name": username})
        return {"success": True, "data": make_json_safe(result), "message": result.get("message", "添加成功")}

    def start_microsoft_login(self) -> dict[str, Any]:
        try:
            result = self._account_manager.start_microsoft_login()
        except (ValueError, RuntimeError) as e:
            logger.error(f"启动微软登录失败: {e}")
            return {"success": False, "message": str(e)}

        if result.get("needs_client_id"):
            return {
                "success": True,
                "data": {"needs_client_id": True},
                "message": "需要配置 Microsoft 登录 Client ID",
            }

        if result.get("status") == "pending":
            verification_uri = result.get("verificationUri", "")
            user_code = result.get("userCode", "")

            if user_code:
                try:
                    pyperclip.copy(user_code)
                    logger.info(f"授权码已自动复制: {user_code}")
                except (RuntimeError, OSError) as copy_err:
                    logger.warning(f"自动复制授权码失败: {copy_err}")

            if verification_uri:
                try:
                    import webbrowser

                    webbrowser.open(verification_uri)
                    logger.info(f"已自动打开浏览器: {verification_uri}")
                except (OSError, RuntimeError) as open_err:
                    logger.warning(f"自动打开浏览器失败: {open_err}")

        return {"success": True, "data": make_json_safe(result), "message": result.get("message", "请完成授权")}

    def poll_microsoft_login(self) -> dict[str, Any]:
        try:
            result = self._account_manager.poll_microsoft_login()
        except (ValueError, RuntimeError) as e:
            logger.error(f"轮询微软登录状态失败: {e}")
            return {"success": False, "message": str(e)}

        if result.get("status") == "ready":
            logger.info("微软登录完成")

        return make_json_safe(result)

    def complete_microsoft_login(self) -> dict[str, Any]:
        from ..api.events import emit_plugin_event

        try:
            result = self._account_manager.complete_microsoft_login()
        except (ValueError, RuntimeError) as e:
            logger.error(f"完成微软登录失败: {e}")
            return {"success": False, "message": str(e)}
        if result.get("success"):
            account = result.get("account", {})
            emit_plugin_event(
                "account:login",
                {
                    "account_type": "microsoft",
                    "player_name": account.get("alias", ""),
                    "uuid": account.get("uuid", ""),
                },
            )
        return {"success": True, "data": make_json_safe(result), "message": result.get("message", "登录成功")}

    def switch_account(self, account_id: str) -> dict[str, Any]:
        from ..api.events import emit_plugin_event

        try:
            result = self._account_manager.switch_account(account_id)
        except (ValueError, RuntimeError) as e:
            logger.error(f"切换账户失败: {e}")
            return {"success": False, "message": str(e)}
        old = self._account_manager.get_current_account()
        new = self._account_manager.get_current_account()
        emit_plugin_event(
            "account:switch",
            {
                "from_type": old.get("type", "") if old else "",
                "to_type": new.get("type", "") if new else "",
                "player_name": new.get("alias", "") if new else "",
            },
        )
        return {"success": True, "data": make_json_safe(result), "message": result.get("message", "切换成功")}

    def remove_account(self, account_id: str) -> dict[str, Any]:
        from ..api.events import emit_plugin_event

        account = self._account_manager.get_account_by_id(account_id)
        try:
            result = self._account_manager.remove_account(account_id)
        except (ValueError, RuntimeError) as e:
            logger.error(f"移除账户失败: {e}")
            return {"success": False, "message": str(e)}
        emit_plugin_event(
            "account:logout", {"account_type": account.get("type", "") if account else "", "account_id": account_id}
        )
        return {"success": True, "data": make_json_safe(result), "message": result.get("message", "移除成功")}

    def refresh_account_profile(self, account_id: str) -> dict[str, Any]:
        from ..api.events import emit_plugin_event

        try:
            result = self._account_manager.refresh_account_profile(account_id)
        except (ValueError, RuntimeError) as e:
            logger.error(f"刷新账户档案失败: {e}")
            return {"success": False, "message": str(e)}
        account = self._account_manager.get_account_by_id(account_id)
        emit_plugin_event(
            "account:profile_refreshed",
            {
                "account_type": account.get("type", "") if account else "",
                "player_name": account.get("alias", "") if account else "",
            },
        )
        return {"success": True, "data": make_json_safe(result), "message": result.get("message", "刷新成功")}

    def add_authlib_account(self, server_url: str, email: str, password: str) -> dict[str, Any]:
        """添加外置登录（Authlib-Injector）账户。"""
        from ..api.events import emit_plugin_event

        try:
            result = self._account_manager.add_authlib_account(server_url, email, password)
        except (ValueError, RuntimeError) as e:
            logger.error(f"添加外置登录账户失败: {e}")
            return {"success": False, "message": str(e)}
        if not result.get("success"):
            return {"success": False, "message": result.get("message", "添加外置登录账户失败")}
        emit_plugin_event("account:login", {"account_type": "authlib", "server_url": server_url, "email": email})
        return {"success": True, "data": make_json_safe(result), "message": result.get("message", "添加成功")}

    def get_authlib_servers(self) -> dict[str, Any]:
        """返回预设的 Authlib-Injector 外置登录服务器列表。"""
        servers = [
            {"name": "LittleSkin", "url": "https://littleskin.cn/api/yggdrasil", "description": "LittleSkin 皮肤站"},
            {"name": "Blessing Skin", "url": "", "description": "自建 Blessing Skin 皮肤站（请自行填写地址）"},
        ]
        return {"success": True, "data": servers}

    def get_game_instances(self) -> dict[str, Any]:
        launcher_core = getattr(self._state, "launcher_core", None)
        if launcher_core is None:
            return {"success": False, "message": "启动器核心未初始化", "data": []}
        im = getattr(launcher_core, "instances_manager", None)
        if im is None:
            return {"success": False, "message": "实例管理器未初始化", "data": []}
        running_instances = im.get_instances_info()

        instances = []
        for inst in running_instances:
            proc = inst.get("Instance")
            is_running = proc.poll() is None if proc else False
            instances.append(
                {
                    "id": inst.get("ID"),
                    "name": inst.get("Name", "未知实例"),
                    "version": inst.get("Name", ""),
                    "isRunning": is_running,
                    "type": inst.get("Type", "MinecraftClient"),
                    "startTime": getattr(proc, "_start_time", None),
                }
            )

        return {"success": True, "data": instances, "message": f"获取到 {len(instances)} 个运行中的进程"}

    def set_master_password(self, password: str) -> dict[str, Any]:
        if len(password) < 8:
            return {"success": False, "message": "密码长度至少8位"}
        try:
            result = self._state.account_manager.set_master_password(password)
        except ValueError as e:
            return {"success": False, "message": str(e)}
        if result:
            return {"success": True, "message": "主密码设置成功"}
        return {"success": False, "message": "设置主密码失败"}

    def get_keyring_info(self) -> dict[str, Any]:
        auth = getattr(self._state.account_manager, "_auth", None)
        encryption = getattr(auth, "encryption", None) if auth else None
        if encryption is None:
            return {"success": True, "data": {"initialized": False, "needs_password": False}}
        try:
            info = encryption.keyring_manager.get_backend_info()
            needs_password = encryption.needs_password()
        except (OSError, ValueError) as e:
            return {"success": False, "message": str(e), "data": None}
        return {"success": True, "data": {"initialized": True, "needs_password": needs_password, **info}}

    def clear_keyring(self) -> dict[str, Any]:
        auth = getattr(self._state.account_manager, "_auth", None)
        if auth is None:
            return {"success": False, "message": "账户系统未初始化"}
        encryption = getattr(auth, "encryption", None)
        if encryption is None:
            return {"success": False, "message": "加密系统未初始化"}

        # 删除密钥环中的加密密钥
        with contextlib.suppress(RuntimeError, OSError, ValueError):
            keyring.delete_password(encryption.service_name, "encryption_key")

        # 删除本地 salt 文件和账户文件
        salt_file = getattr(encryption, "salt_file", None)
        accounts_file = getattr(auth, "accounts_file", None)

        removed = []
        if salt_file is not None and salt_file.exists():
            salt_file.unlink()
            removed.append("salt")
        if accounts_file is not None and accounts_file.exists():
            accounts_file.unlink()
            removed.append("accounts")

        # 清理内存状态
        encryption.fernet = None
        encryption._needs_password = True
        auth.accounts = {}
        auth.current_account = None
        auth._initialized = False

        logger.info(f"密钥环已清理，移除: {removed}")
        return {"success": True, "message": "密钥环已清理", "data": {"removed": removed}}

    async def launch_instance(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        from ..api.events import emit, emit_plugin_event

        params = params or {}
        try:
            version_id = params.get("version_id")
            if not version_id:
                return {"success": False, "message": "缺少 version_id 参数"}

            java_path = params.get("java_path")
            if not java_path:
                javas = self._state.get_java_dicts()
                if not javas:
                    return {"success": False, "message": "未找到 Java 环境"}
                java_path = javas[0]["path"]

            game_path = params.get("game_path")
            if not game_path:
                game_path = self._get_first_game_path()

            # 获取账户信息
            current = self._state.account_manager.get_current_account()
            if not current:
                return {"success": False, "message": "请先选择账户"}

            player_name = current.get("alias", "Player")
            user_type = current.get("type", "legacy")
            auth_uuid = current.get("uuid", "")
            access_token = self._state.account_manager.get_current_account_token() or "None"

            # Authlib 外置登录参数
            authlib_injector_path = None
            authlib_server = None
            if current.get("type") == "authlib":
                am = self._state.account_manager
                inj_manager = am.get_authlib_injector_manager()
                authlib_injector_path = str(inj_manager.get_path())
                authlib_server = current.get("auth_server", "")

            # 插件事件：游戏启动前（可取消）
            pre_payload = {
                "version_id": version_id,
                "player_name": player_name,
                "user_type": user_type,
                "options": params,
            }
            pre_results = emit_plugin_event("game:pre_launch", pre_payload)
            if any(r is False for r in pre_results):
                emit("game:launch_progress", {"phase": "error", "message": "启动被插件阻止"})
                return {"success": False, "message": "启动被插件阻止"}

            # 重置取消标志
            self._state.launcher_core.reset_cancel()

            # 推送启动进度：准备阶段
            emit("game:launch_progress", {"phase": "preparing", "message": f"正在准备启动 {version_id}..."})

            # 启动游戏（在子线程中执行），同时轮询进度事件队列
            from ..common.state import drain_progress_events

            # 计算内存分配
            game_config = self._config_manager.get_game_config()
            if params.get("memory"):
                max_use_ram = int(params["memory"])
            elif game_config.get("memory_auto"):
                available_memory = psutil.virtual_memory().available / 1048576
                max_use_ram = int(available_memory * 0.75) if available_memory < 8192 else 8192
            else:
                max_use_ram = int(game_config.get("memory_size", 4096))

            async def _launch_async():
                await asyncio.to_thread(
                    self._state.launcher_core.launch_minecraft,
                    java_path=java_path,
                    game_path=game_path,
                    version_name=version_id,
                    max_use_ram=max_use_ram,
                    player_name=player_name,
                    user_type=user_type,
                    auth_uuid=auth_uuid,
                    access_token=access_token,
                    window_width=params.get("width", 854),
                    window_height=params.get("height", 480),
                    custom_jvm_params=params.get("jvm_args"),
                    download_max_thread=params.get("download_threads", 32),
                    authlib_injector_path=authlib_injector_path,
                    authlib_server=authlib_server,
                )

            launch_task = asyncio.create_task(_launch_async())

            # 轮询进度事件队列，每 50ms 消费一次
            while not launch_task.done():
                drain_progress_events()
                await asyncio.sleep(0.05)

            # 消费剩余事件
            drain_progress_events()
            await launch_task

            # 检查是否被取消
            if self._state.launcher_core.is_canceled():
                emit("game:launch_progress", {"phase": "error", "message": "启动已取消"})
                return {"success": False, "message": "启动已取消"}

            # 推送启动完成
            emit("game:launch_progress", {"phase": "launched", "message": f"游戏 {version_id} 已启动"})
            # 插件事件：游戏已启动
            emit_plugin_event("game:launch_start", {"version_id": version_id, "player_name": player_name})
            return {"success": True, "message": f"游戏 {version_id} 启动中"}
        except (ValueError, FileNotFoundError, OSError, RuntimeError, asyncio.CancelledError) as e:
            logger.error(f"启动游戏失败: {e}")
            emit("game:launch_progress", {"phase": "error", "message": str(e)})
            # 插件事件：启动失败
            emit_plugin_event(
                "game:exit", {"version_id": params.get("version_id", ""), "exit_code": -1, "reason": str(e)}
            )
            return {"success": False, "message": str(e)}

    # TODO: 实现启动进度查询功能
    def get_launch_status(self, task_id: str) -> dict[str, Any]:
        return {"success": False, "message": "启动进度查询功能待对接", "data": None}

    def stop_instance(self, instance_id: str) -> dict[str, Any]:
        from ..api.events import emit_plugin_event

        launcher_core = getattr(self._state, "launcher_core", None)
        if launcher_core is None:
            return {"success": False, "message": "启动器核心未初始化"}
        im = getattr(launcher_core, "instances_manager", None)
        if im is None:
            return {"success": False, "message": "实例管理器未初始化"}
        running_instances = im.get_instances_info()
        if not any(inst["ID"] == instance_id for inst in running_instances):
            return {"success": False, "message": "实例未在运行"}

        try:
            im.stop_instance(instance_id, terminate=True)
        except (OSError, RuntimeError) as e:
            logger.error(f"停止实例失败: {e}")
            return {"success": False, "message": str(e)}
        emit_plugin_event("game:exit", {"instance_id": instance_id, "exit_code": -1, "reason": "stopped"})
        return {"success": True, "message": "实例已停止"}

    def cancel_launch(self) -> dict[str, Any]:
        # 取消当前启动流程，终止所有运行中的游戏实例。
        logger.info("[cancel_launch] 收到前端取消请求")
        launcher_core = getattr(self._state, "launcher_core", None)
        if launcher_core is None:
            return {"success": False, "message": "启动器核心未初始化"}
        try:
            launcher_core.cancel_launch()
        except (RuntimeError, OSError) as e:
            logger.error(f"[cancel_launch] 取消失败: {e}")
            return {"success": False, "message": str(e)}
        logger.info("[cancel_launch] 取消标志已设置，下载器已停止，实例已终止")
        return {"success": True, "message": "启动已取消"}

    def _plugin_action(self, plugin_name: str, action: str, fw_method: Callable, **kwargs) -> dict[str, Any]:
        # 通用插件操作方法：enable/disable/unload/reload 等。
        fw = self._state.plugin_framework
        if fw is None:
            return {"success": False, "message": "插件框架未启用"}
        try:
            if action == "reload":
                logger.info(f"[plugin-reload] 开始重载插件: {plugin_name}, cascade={kwargs.get('cascade', False)}")
            result = fw_method(fw, **kwargs)
            if action == "reload":
                logger.info(
                    f"[plugin-reload] 重载结果: {plugin_name} -> success={result.get('success')}, message={result.get('message', '')}"
                )
            from ..api.events import emit

            emit("plugin:status_changed", {"name": plugin_name, "action": action, "result": result})
            return result
        except (RuntimeError, OSError, ValueError, TypeError) as e:
            logger.error(f"{action} 插件 {plugin_name} 失败: {e}")
            return {"success": False, "message": str(e)}

    def plugin_list(self) -> dict[str, Any]:
        fw = self._state.plugin_framework
        if fw is None:
            return {"success": True, "data": [], "message": "插件框架未启用"}
        try:
            plugins = fw.scan_plugins()
            return {"success": True, "data": plugins, "message": f"共 {len(plugins)} 个插件"}
        except (OSError, RuntimeError, ValueError) as e:
            logger.error(f"获取插件列表失败: {e}")
            return {"success": False, "message": str(e), "data": []}

    def plugin_info(self, plugin_name: str) -> dict[str, Any]:
        fw = self._state.plugin_framework
        if fw is None:
            return {"success": False, "message": "插件框架未启用"}
        try:
            plugin = fw.get_plugin(plugin_name)
            if not plugin:
                return {"success": False, "message": f"插件 {plugin_name} 不存在"}
            data = fw.get_plugin_info_dict(plugin)
            data["provided_events"] = plugin.get_provided_events()
            data["subscribed_events"] = plugin.get_subscribed_events()
            return {"success": True, "data": data}
        except (AttributeError, OSError, RuntimeError) as e:
            logger.error(f"获取插件信息失败: {e}")
            return {"success": False, "message": str(e)}

    def plugin_enable(self, plugin_name: str) -> dict[str, Any]:
        return self._plugin_action(plugin_name, "enable", lambda fw: fw.enable_plugin(plugin_name))

    def plugin_disable(self, plugin_name: str, force: bool = False) -> dict[str, Any]:
        return self._plugin_action(plugin_name, "disable", lambda fw: fw.disable_plugin(plugin_name, force=force))

    def plugin_unload(self, plugin_name: str) -> dict[str, Any]:
        return self._plugin_action(plugin_name, "unload", lambda fw: fw.unload_plugin(plugin_name))

    def plugin_reload(self, plugin_name: str, cascade: bool = False) -> dict[str, Any]:
        return self._plugin_action(
            plugin_name, "reload", lambda fw: fw.reload_plugin(plugin_name, cascade=cascade)
        )

    def plugin_install(self, plugin_path: str) -> dict[str, Any]:
        import shutil
        import zipfile

        fw = self._state.plugin_framework
        if fw is None:
            return {"success": False, "message": "插件框架未启用"}
        try:
            source = Path(plugin_path)
            if not source.exists():
                return {"success": False, "message": f"路径不存在: {plugin_path}"}

            if source.is_dir():
                manifest = source / "plugin.json"
                if not manifest.exists():
                    return {"success": False, "message": "所选目录中未找到 plugin.json"}
                with manifest.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                plugin_name = data.get("name")
                if not plugin_name:
                    return {"success": False, "message": "plugin.json 中缺少 name 字段"}

                target_dir = fw._plugins_dir / plugin_name
                if target_dir.exists():
                    return {"success": False, "message": f"插件 {plugin_name} 已存在，请先卸载"}

                shutil.copytree(source, target_dir)
                result = fw.load_plugin(plugin_name)
                if result.get("success"):
                    from ..api.events import emit

                    emit("plugin:installed", {"name": plugin_name})
                return result
            else:
                with zipfile.ZipFile(source, "r") as zf:
                    names = zf.namelist()
                    json_entry = next((n for n in names if n.endswith("plugin.json")), None)
                    if not json_entry:
                        return {"success": False, "message": "压缩包中未找到 plugin.json"}
                    with zf.open(json_entry) as f:
                        data = json.load(f)
                    plugin_name = data.get("name")
                    if not plugin_name:
                        return {"success": False, "message": "plugin.json 中缺少 name 字段"}

                target_dir = fw._plugins_dir / plugin_name
                if target_dir.exists():
                    return {"success": False, "message": f"插件 {plugin_name} 已存在，请先卸载"}

                with zipfile.ZipFile(source, "r") as zf:
                    target_dir_resolved = Path(target_dir).resolve()
                    for member in zf.namelist():
                        member_path = (Path(target_dir) / member).resolve()
                        if not str(member_path).startswith(str(target_dir_resolved)):
                            return {"success": False, "message": f"压缩包包含不安全的路径: {member}"}
                    zf.extractall(target_dir)

                result = fw.load_plugin(plugin_name)
                if result.get("success"):
                    from ..api.events import emit

                    emit("plugin:installed", {"name": plugin_name})
                return result
        except (zipfile.BadZipFile, json.JSONDecodeError, OSError, KeyError, ValueError) as e:
            logger.error(f"安装插件失败: {e}")
            return {"success": False, "message": str(e)}

    def plugin_get_settings(self, plugin_name: str) -> dict[str, Any]:
        fw = self._state.plugin_framework
        if fw is None:
            return {"success": False, "message": "插件框架未启用"}
        data = fw._plugin_settings.get(plugin_name, {"schema": {}, "values": {}})
        return {"success": True, "data": data}

    def plugin_update_setting(self, plugin_name: str, key: str, value: Any) -> dict[str, Any]:
        fw = self._state.plugin_framework
        if fw is None:
            return {"success": False, "message": "插件框架未启用"}
        fw._update_plugin_setting(plugin_name, key, value)
        return {"success": True, "message": "设置已更新"}

    def plugin_get_routes(self) -> dict[str, Any]:
        fw = self._state.plugin_framework
        if fw is None:
            return {"success": True, "data": []}
        return {"success": True, "data": fw.get_routes()}

    def plugin_call_command(self, command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        fw = self._state.plugin_framework
        if fw is None:
            return {"success": False, "message": "插件框架未启用"}
        return fw.call_command(command, **(params or {}))

    def plugin_get_slots(self) -> dict[str, Any]:
        fw = self._state.plugin_framework
        if fw is None:
            return {"success": True, "data": {}}
        return {"success": True, "data": fw.get_html_slots()}

    # ── ModManager 委托方法 ──

    def get_mods(self, game_path: str | None = None) -> dict[str, Any]:
        path = game_path or self._get_first_game_path()
        return {"success": True, "data": ModManager.get_mods(path)}

    def toggle_mod(self, game_path: str | None = None, filename: str = "") -> dict[str, Any]:
        path = game_path or self._get_first_game_path()
        return ModManager.toggle_mod(path, filename)

    def add_mod(self, game_path: str | None = None, source_path: str = "") -> dict[str, Any]:
        path = game_path or self._get_first_game_path()
        return ModManager.add_mod(path, source_path)

    def remove_mod(self, game_path: str | None = None, filename: str = "") -> dict[str, Any]:
        path = game_path or self._get_first_game_path()
        return ModManager.remove_mod(path, filename)

    def open_mods_folder(self, game_path: str | None = None) -> dict[str, Any]:
        path = game_path or self._get_first_game_path()
        return ModManager.open_mods_folder(path)

    # ── ModpackManager 委托方法 ──

    def detect_modpack_type(self, file_path: str = "") -> dict[str, Any]:
        return ModpackManager.detect_modpack_type(file_path)

    def import_modpack(
        self, file_path: str = "", game_path: str = "", version_name: str = "", download_threads: int = 32
    ) -> dict[str, Any]:
        path = game_path or self._get_first_game_path()
        return ModpackManager.import_modpack(file_path, path, version_name, download_threads)

    def export_modpack(
        self,
        game_path: str = "",
        output_path: str = "",
        format: str = "curseforge",
        name: str = "",
        version: str = "",
        author: str = "",
    ) -> dict[str, Any]:
        path = game_path or self._get_first_game_path()
        return ModpackManager.export_modpack(path, output_path, format, name, version, author)

    # ── ResourceManager 委托方法 ──

    def list_resourcepacks(self, game_path: str | None = None) -> dict[str, Any]:
        path = game_path or self._get_first_game_path()
        return {"success": True, "data": ResourceManager.list_resourcepacks(path)}

    def list_shaderpacks(self, game_path: str | None = None) -> dict[str, Any]:
        path = game_path or self._get_first_game_path()
        return {"success": True, "data": ResourceManager.list_shaderpacks(path)}

    def list_saves(self, game_path: str | None = None) -> dict[str, Any]:
        path = game_path or self._get_first_game_path()
        return {"success": True, "data": ResourceManager.list_saves(path)}

    def remove_resourcepack(self, game_path: str | None = None, filename: str = "") -> dict[str, Any]:
        path = game_path or self._get_first_game_path()
        return ResourceManager.remove_resourcepack(path, filename)

    def remove_shaderpack(self, game_path: str | None = None, filename: str = "") -> dict[str, Any]:
        path = game_path or self._get_first_game_path()
        return ResourceManager.remove_shaderpack(path, filename)

    def delete_save(self, game_path: str | None = None, save_name: str = "") -> dict[str, Any]:
        path = game_path or self._get_first_game_path()
        return ResourceManager.delete_save(path, save_name)

    def open_resourcepacks_folder(self, game_path: str | None = None) -> dict[str, Any]:
        path = game_path or self._get_first_game_path()
        return ResourceManager.open_resourcepacks_folder(path)

    def open_shaderpacks_folder(self, game_path: str | None = None) -> dict[str, Any]:
        path = game_path or self._get_first_game_path()
        return ResourceManager.open_shaderpacks_folder(path)

    def open_saves_folder(self, game_path: str | None = None) -> dict[str, Any]:
        path = game_path or self._get_first_game_path()
        return ResourceManager.open_saves_folder(path)

    async def exec_action(self, payload: dict | None = None) -> dict[str, Any]:
        # 通用命令分发器，供前端 exec_action 调用。
        # 前端传入形如 { name: str, params: any } 的对象，本方法负责将 name 映射到具体的 Api 方法并调用。
        # 为兼容旧前端命令，本方法对常见命令名做映射，并实现简单的文件系统辅助方法。
        try:
            if not payload or not isinstance(payload, dict):
                return {"success": False, "message": "缺少操作名称或参数格式错误"}

            name = payload.get("name")
            params = payload.get("params", {})

            # 简单映射：前端命令名 -> Api 类中实际方法名
            mapping = {
                "ping": "ping",
                "java_scan": "get_java_list",
                "java_list": "get_java_list",
                "minecraft_versions": "get_minecraft_versions",
                "fabric_versions": "get_fabric_versions",
                "forge_versions": "get_forge_versions",
                "neoforge_versions": "get_neoforge_versions",
                "optifine_versions": "get_optifine_versions",
                "quilt_versions": "get_quilt_versions",
                "scan_versions": "scan_versions_in_path",
                "install_version": "install_version",
                "uninstall_version": "uninstall_version",
                "accounts_list": "get_accounts",
                "accounts_current": "get_current_account",
                "accounts_add_offline": "add_offline_account",
                "accounts_start_microsoft_login": "start_microsoft_login",
                "accounts_poll_microsoft_login": "poll_microsoft_login",
                "accounts_complete_microsoft_login": "complete_microsoft_login",
                "accounts_switch": "switch_account",
                "accounts_remove": "remove_account",
                "accounts_refresh_profile": "refresh_account_profile",
                "accounts_add_authlib": "add_authlib_account",
                "authlib_servers": "get_authlib_servers",
                "user_agreement_get": "get_user_agreement_status",
                "user_agreement_save": "save_user_agreement",
                "user_agreement_clear": "clear_user_agreement",
                "image_fetch_data_url": "fetch_image_data_url",
                "image_save_url": "load_image_from_url",
                "image_read_file": "load_image_from_local",
                "select_directory": "select_directory",
                "select_java": "select_java_executable",
                "select_image": "select_local_image",
                "select_file": "select_file",
                "avatar_data_url": "get_avatar_data_url",
                "instances_list": "get_game_instances",
                "launch_instance": "launch_instance",
                "cancel_launch": "cancel_launch",
                "instance_stop": "stop_instance",
                "launcher_info": "get_launcher_config",
                "set_master_password": "set_master_password",
                "get_keyring_info": "get_keyring_info",
                "clear_keyring": "clear_keyring",
                "frontend_ready": "frontend_ready",
                "search_mods": "search_mods",
                "get_mod_info": "get_mod_info",
                "get_mod_versions": "get_mod_versions",
                "download_mod": "download_mod",
                "get_mods": "get_mods",
                "toggle_mod": "toggle_mod",
                "add_mod": "add_mod",
                "remove_mod": "remove_mod",
                "open_mods_folder": "open_mods_folder",
                "detect_modpack_type": "detect_modpack_type",
                "import_modpack": "import_modpack",
                "export_modpack": "export_modpack",
                "list_resourcepacks": "list_resourcepacks",
                "list_shaderpacks": "list_shaderpacks",
                "list_saves": "list_saves",
                "remove_resourcepack": "remove_resourcepack",
                "remove_shaderpack": "remove_shaderpack",
                "delete_save": "delete_save",
                "open_resourcepacks_folder": "open_resourcepacks_folder",
                "open_shaderpacks_folder": "open_shaderpacks_folder",
                "open_saves_folder": "open_saves_folder",
            }

            # 文件系统与路径相关命令单独实现
            if name == "fs_read_dir":
                path = params.get("path") if isinstance(params, dict) else params
                p = Path(path)
                if not p.exists():
                    return {"success": False, "message": "路径不存在", "data": []}
                items = []
                for it in p.iterdir():
                    try:
                        stat = it.stat()
                        items.append(
                            {
                                "name": it.name,
                                "is_dir": it.is_dir(),
                                "size": stat.st_size,
                                "mtime": int(stat.st_mtime),
                            }
                        )
                    except (OSError, PermissionError):
                        items.append({"name": it.name, "is_dir": it.is_dir(), "size": 0, "mtime": 0})
                return {"success": True, "data": items}

            if name == "fs_read_file":
                path = params.get("path") if isinstance(params, dict) else params
                mode = (params.get("mode") if isinstance(params, dict) else None) or "text"
                p = Path(path)
                if not p.exists():
                    return {"success": False, "message": "文件不存在", "data": None}
                try:
                    if mode == "base64":
                        content = base64.b64encode(p.read_bytes()).decode("utf-8")
                        return {"success": True, "data": {"content": content, "size": p.stat().st_size}}
                    else:
                        text = p.read_text(encoding="utf-8")
                        return {"success": True, "data": {"content": text, "size": p.stat().st_size}}
                except (OSError, UnicodeDecodeError, PermissionError) as e:
                    logger.error(f"读取文件失败: {e}")
                    return {"success": False, "message": str(e), "data": None}

            if name == "fs_exists":
                path = params.get("path") if isinstance(params, dict) else params
                p = Path(path)
                return {"success": True, "data": {"exists": p.exists(), "is_dir": p.is_dir(), "is_file": p.is_file()}}

            if name == "file_resolve":
                path = params.get("path") if isinstance(params, dict) else params
                p = Path(path)
                if not p.exists():
                    return {"success": False, "message": "路径不存在", "data": None}
                return {"success": True, "data": {"path": str(p.resolve())}}

            # 映射到 Api 中的真实方法名
            target = mapping.get(name, name)

            if not hasattr(self, target):
                return {"success": False, "message": f"未知操作: {name}"}

            func = getattr(self, target)
            if not callable(func):
                return {"success": False, "message": f"目标不是可调用的方法: {target}"}

            # 调用目标方法，尝试多种参数传递方式以兼容不同签名
            try:
                if isinstance(params, dict):
                    result = func(**params)
                elif isinstance(params, (list, tuple)):
                    result = func(*params)
                else:
                    result = func(params)
                return await result if inspect.iscoroutine(result) else result
            except TypeError:
                try:
                    result = func(params)
                    return await result if inspect.iscoroutine(result) else result
                except (RuntimeError, OSError, ValueError, TypeError) as e:
                    return {"success": False, "message": f"调用失败: {e}"}
            except (RuntimeError, OSError, ValueError) as e:
                return {"success": False, "message": f"调用失败: {e}"}

        except (RuntimeError, OSError, ValueError, TypeError) as e:
            logger.error(f"exec_action 调用失败: {e}")
            return {"success": False, "message": str(e)}

    def _get_cf_api_key(self) -> str:
        # 从配置中获取 CurseForge API Key
        cfg = self._config_manager.config
        if cfg and isinstance(cfg, list) and len(cfg) > 0:
            return cfg[0].get("curseforge_api_key", "")
        return ""

    def search_mods(
        self,
        query: str = "",
        loader: str = "",
        version: str = "",
        limit: int = 20,
        offset: int = 0,
        source: str = "both",
    ) -> dict[str, Any]:
        cf_api_key = self._get_cf_api_key()
        return OnlineModSearch.search_mods(query, loader, version, limit, offset, source, cf_api_key)

    def get_mod_info(self, project_id: str = "", source: str = "") -> dict[str, Any]:
        cf_api_key = self._get_cf_api_key()
        return OnlineModSearch.get_mod_info(project_id, source, cf_api_key)

    def get_mod_versions(
        self, project_id: str = "", source: str = "", loader: str = "", game_version: str = ""
    ) -> list[dict[str, Any]]:
        cf_api_key = self._get_cf_api_key()
        return OnlineModSearch.get_mod_versions(project_id, source, loader, game_version, cf_api_key)

    def download_mod(
        self, project_id: str = "", version_id: str = "", source: str = "", game_path: str = "", filename: str = ""
    ) -> dict[str, Any]:
        cf_api_key = self._get_cf_api_key()
        return OnlineModSearch.download_mod(project_id, version_id, source, game_path, filename, cf_api_key)
