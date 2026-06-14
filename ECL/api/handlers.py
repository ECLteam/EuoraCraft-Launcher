import base64
import ctypes
import json
import os
import sys
import uuid
from ctypes import wintypes
from pathlib import Path
from tkinter import Tk, filedialog
from typing import Any

import requests

from ..common.logger import get_logger
from ..common.state import AppState
from ..game.Core import get_avatar_data_url as get_avatar_func


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


logger = get_logger("api")


def _get_project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def get_resource_path(relative_path: str) -> str:
    p = Path(getattr(sys, "_MEIPASS", Path.cwd())) / relative_path
    return str(p.resolve())


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

    def __dir__(self) -> list[str]:
        return [
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
            "get_game_config",
            "update_game_config",
            "get_java_list",
            "get_theme_config",
            "update_theme_config",
            "get_download_config",
            "update_download_config",
            "get_mouse_effect_config",
            "update_mouse_effect_config",
            "get_locale_config",
            "update_locale_config",
            "select_directory",
            "select_java_executable",
            "scan_versions_in_path",
            "get_minecraft_versions",
            "get_fabric_versions",
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
            "get_game_instances",
            "launch_instance",
            "get_launch_status",
            "stop_instance",
        ]

    def ping(self) -> dict[str, Any]:
        return {"success": True, "data": {"status": "ok", "message": "API连接正常"}, "message": "Pong"}

    def get_user_agreement_status(self) -> dict[str, Any]:
        try:
            agreement_file = _get_project_root() / "ECL_Libs" / "user_agreement.json"
            if agreement_file.exists():
                with agreement_file.open(encoding="utf-8") as f:
                    data = json.load(f)
                return {
                    "success": True,
                    "data": {"accepted": data.get("accepted", False), "uuid": data.get("uuid", "")},
                    "message": "获取用户协议状态成功",
                }
            return {"success": True, "data": {"accepted": False, "uuid": ""}, "message": "用户协议未同意"}
        except Exception as e:
            logger.error(f"获取用户协议状态失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def save_user_agreement(self) -> dict[str, Any]:
        try:
            agreement_file = _get_project_root() / "ECL_Libs" / "user_agreement.json"
            agreement_file.parent.mkdir(parents=True, exist_ok=True)
            data = {"accepted": True, "uuid": str(uuid.uuid4())}
            with agreement_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return {"success": True, "data": data, "message": "用户协议已保存"}
        except Exception as e:
            logger.error(f"保存用户协议失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def clear_user_agreement(self) -> dict[str, Any]:
        try:
            agreement_file = _get_project_root() / "ECL_Libs" / "user_agreement.json"
            if agreement_file.exists():
                agreement_file.unlink()
            return {"success": True, "message": "用户协议已清除"}
        except Exception as e:
            logger.error(f"清除用户协议失败: {e}")
            return {"success": False, "message": str(e)}

    def minimize_window(self) -> dict[str, Any]:
        try:
            import webview

            if webview.windows:
                webview.windows[0].minimize()
                return {"success": True, "message": "窗口已最小化"}
            return {"success": False, "message": "窗口未找到"}
        except Exception as e:
            logger.error(f"最小化窗口失败: {e}")
            return {"success": False, "message": str(e)}

    def close_window(self) -> dict[str, Any]:
        try:
            import webview

            if webview.windows:
                webview.windows[0].destroy()
                return {"success": True, "message": "窗口已关闭"}
            return {"success": False, "message": "窗口未找到"}
        except Exception as e:
            logger.error(f"关闭窗口失败: {e}")
            return {"success": False, "message": str(e)}

    def get_window_position(self) -> dict[str, Any]:
        try:
            import webview

            if webview.windows:
                window = webview.windows[0]
                return {
                    "success": True,
                    "data": {"x": window.x, "y": window.y, "width": window.width, "height": window.height},
                    "message": "获取窗口位置成功",
                }
            return {"success": False, "message": "窗口未找到", "data": None}
        except Exception as e:
            logger.error(f"获取窗口位置失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def set_window_position(self, x: int, y: int) -> dict[str, Any]:
        try:
            import webview

            if webview.windows:
                webview.windows[0].move(x, y)
                return {"success": True, "message": f"窗口位置已设置为 ({x}, {y})"}
            return {"success": False, "message": "窗口未找到"}
        except Exception as e:
            logger.error(f"设置窗口位置失败: {e}")
            return {"success": False, "message": str(e)}

    def get_launcher_config(self) -> dict[str, Any]:
        try:
            config = self._config_manager.get_launcher_config()
            safe_config = make_json_safe(config)
            logger.debug(f"返回启动器配置: {safe_config}")
            return {"success": True, "data": safe_config, "message": "获取成功"}
        except Exception as e:
            logger.error(f"获取启动器配置失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def get_background_config(self) -> dict[str, Any]:
        try:
            config = self._config_manager.get_background_config()
            safe_config = make_json_safe(config)
            logger.debug(f"返回背景图配置: {safe_config}")
            return {"success": True, "data": safe_config, "message": "获取成功"}
        except Exception as e:
            logger.error(f"获取背景图配置失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def get_background_image(self) -> dict[str, Any]:
        try:
            config = self._config_manager.get_background_config()
            path_str = config.get("path", "")

            if not path_str:
                return {"success": False, "message": "未设置背景图", "data": None}

            path_str = path_str.replace("/", os.sep).replace("\\", os.sep)
            path = Path(path_str)

            if not path.exists():
                logger.error(f"[get_background_image] 文件不存在: {path}")
                return {"success": False, "message": f"背景图文件不存在: {path_str}", "data": None}

            try:
                image_data = path.read_bytes()
            except Exception as e:
                logger.error(f"[get_background_image] 读取文件失败: {e}")
                return {"success": False, "message": f"读取背景图文件失败: {e}", "data": None}

            mime_map = {
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
            }
            mime_type = mime_map.get(path.suffix.lower(), "image/jpeg")
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
        except Exception as e:
            logger.error(f"[get_background_image] 异常: {e}")
            return {"success": False, "message": str(e), "data": None}

    def update_background_config(self, background_config: dict[str, Any]) -> dict[str, Any]:
        try:
            if background_config.get("type") == "local" and background_config.get("path"):
                path = Path(background_config["path"])
                if path.exists():
                    background_config["image_base64"] = base64.b64encode(path.read_bytes()).decode("utf-8")

            self._config_manager.update_background_config(background_config)
            logger.info(f"背景图配置已更新: {background_config.get('type')}")

            if "blur" in background_config:
                current_theme = self._config_manager.get_theme_config()
                current_theme["blur_amount"] = background_config["blur"]
                self._config_manager.update_theme_config(current_theme)
                logger.info(f"同步背景模糊值到主题配置: {background_config['blur']}")

            return {"success": True, "message": "背景图更新成功"}
        except Exception as e:
            logger.error(f"更新背景图配置失败: {e}")
            return {"success": False, "message": str(e)}

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

            app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()

            background_dir = app_dir / "backgrounds"
            background_dir.mkdir(exist_ok=True)
            logger.info(f"[load_image_from_url] 背景图目录: {background_dir}")

            import hashlib

            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            file_path = background_dir / f"bg_{url_hash}.{ext}"
            logger.info(f"[load_image_from_url] 保存路径: {file_path}")

            file_path.write_bytes(response.content)

            if not file_path.exists():
                logger.error(f"[load_image_from_url] 文件保存失败，路径不存在: {file_path}")
                return {"success": False, "message": "图片保存失败", "data": None}

            abs_path = str(file_path.resolve()).replace("\\", "/")
            logger.info(f"[load_image_from_url] 成功: {abs_path} ({len(response.content)} bytes)")

            return {"success": True, "data": {"path": abs_path}, "message": "图片下载成功"}
        except Exception as e:
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
                                import time

                                time.sleep(2**attempt)
                                continue
                        return {"success": False, "message": f"URL不是图片类型: {content_type}", "data": None}

                    if len(response.content) < 100:
                        logger.warning(f"[fetch_image_data_url] 图片数据过小: {len(response.content)} bytes")
                        if attempt < max_retries - 1:
                            logger.info(f"[fetch_image_data_url] {2**attempt} 秒后重试...")
                            import time

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
                        import re

                        match = re.search(r"(\d{3})\s+Server Error", error_msg)
                        if match and 500 <= int(match.group(1)) < 600:
                            is_5xx_error = True

                    if is_5xx_error and attempt < max_retries - 1:
                        logger.info(f"[fetch_image_data_url] 服务器错误，{2**attempt} 秒后重试...")
                        import time

                        time.sleep(2**attempt)
                        continue

                    return {"success": False, "message": f"HTTP 错误 {status_code}: {error_msg}", "data": None}

                except requests.exceptions.RequestException as req_err:
                    logger.warning(f"[fetch_image_data_url] 请求异常: {req_err}")
                    if attempt < max_retries - 1:
                        logger.info(f"[fetch_image_data_url] {2**attempt} 秒后重试...")
                        import time

                        time.sleep(2**attempt)
                        continue
                    return {"success": False, "message": f"网络请求失败: {req_err!s}", "data": None}

            return {"success": False, "message": f"重试 {max_retries} 次后仍失败", "data": None}

        except Exception as e:
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
        except Exception as e:
            logger.error(f"[get_avatar_data_url] 生成头像失败: {e}")
            return {"success": False, "message": f"头像生成失败: {e!s}", "data": None}

    def load_image_from_local(self, file_path: str) -> dict[str, Any]:
        try:
            path_obj = Path(file_path)
            if not path_obj.exists():
                return {"success": False, "message": f"文件不存在: {file_path}", "data": None}

            valid_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
            if path_obj.suffix.lower() not in valid_extensions:
                return {"success": False, "message": f"不支持的图片格式: {path_obj.suffix}", "data": None}

            return {"success": True, "data": {"path": str(path_obj.absolute())}, "message": "图片验证成功"}
        except Exception as e:
            logger.error(f"验证本地图片失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def select_local_image(self) -> dict[str, Any]:
        try:
            root = Tk()
            root.withdraw()
            root.attributes("-topmost", True)

            result = filedialog.askopenfilename(
                title="选择图片", filetypes=[("Image files", "*.jpg;*.jpeg;*.png;*.gif;*.webp"), ("All files", "*.*")]
            )
            root.destroy()

            if result:
                return self.load_image_from_local(str(result))
            else:
                return {"success": False, "message": "用户取消选择", "data": None}
        except Exception as e:
            logger.error(f"选择本地图片失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def get_game_config(self) -> dict[str, Any]:
        try:
            config = self._config_manager.get_game_config()

            if "minecraft_paths" not in config:
                if "minecraft_path" in config and isinstance(config["minecraft_path"], str):
                    config["minecraft_paths"] = [
                        {"name": "默认路径", "path": config.pop("minecraft_path"), "protected": True}
                    ]
                else:
                    config["minecraft_paths"] = [{"name": "默认路径", "path": "./.minecraft", "protected": True}]

            formatted_paths = []
            for i, p in enumerate(config["minecraft_paths"]):
                if isinstance(p, dict):
                    path_obj = {"name": p.get("name", f"路径{i + 1}"), "path": p.get("path", "")}
                else:
                    path_obj = {"name": f"路径{i + 1}", "path": p}

                if path_obj["path"] == "./.minecraft":
                    path_obj["name"] = "默认路径"

                formatted_paths.append(path_obj)

            config["minecraft_paths"] = formatted_paths

            safe_config = make_json_safe(config)
            logger.debug(f"返回游戏配置: {safe_config}")
            return {"success": True, "data": safe_config, "message": "获取成功"}
        except Exception as e:
            logger.error(f"获取游戏配置失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def update_game_config(self, game_config: dict[str, Any]) -> dict[str, Any]:
        try:
            if "minecraft_paths" in game_config:
                paths = game_config["minecraft_paths"]
                has_default = any((p.get("path", "") if isinstance(p, dict) else p) == "./.minecraft" for p in paths)
                if not has_default:
                    logger.warning("检测到默认路径被删除，自动恢复")
                    paths.insert(0, {"name": "默认路径", "path": "./.minecraft", "protected": True})

            self._config_manager.update_game_config(game_config)
            return {"success": True, "message": "游戏配置更新成功"}
        except Exception as e:
            logger.error(f"更新游戏配置失败: {e}")
            return {"success": False, "message": str(e)}

    def get_java_list(self) -> dict[str, Any]:
        try:
            java_dicts = self._state.get_java_dicts()
            if not java_dicts:
                return {"success": True, "data": [], "message": "未找到Java安装"}
            return {"success": True, "data": java_dicts, "message": f"找到 {len(java_dicts)} 个Java安装"}
        except Exception as e:
            logger.error(f"获取Java列表失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def get_theme_config(self) -> dict[str, Any]:
        try:
            config = self._config_manager.get_theme_config()
            safe_config = make_json_safe(config)
            logger.debug(f"返回主题配置: {safe_config}")
            return {"success": True, "data": safe_config, "message": "获取成功"}
        except Exception as e:
            logger.error(f"获取主题配置失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def update_theme_config(self, theme_config: dict[str, Any]) -> dict[str, Any]:
        try:
            self._config_manager.update_theme_config(theme_config)
            return {"success": True, "message": "主题配置更新成功"}
        except Exception as e:
            logger.error(f"更新主题配置失败: {e}")
            return {"success": False, "message": str(e)}

    def get_download_config(self) -> dict[str, Any]:
        try:
            config = self._config_manager.get_download_config()
            safe_config = make_json_safe(config)
            logger.debug(f"返回下载配置: {safe_config}")
            return {"success": True, "data": safe_config, "message": "获取成功"}
        except Exception as e:
            logger.error(f"获取下载配置失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def update_download_config(self, download_config: dict[str, Any]) -> dict[str, Any]:
        try:
            self._config_manager.update_download_config(download_config)
            return {"success": True, "message": "下载配置更新成功"}
        except Exception as e:
            logger.error(f"更新下载配置失败: {e}")
            return {"success": False, "message": str(e)}

    def get_mouse_effect_config(self) -> dict[str, Any]:
        try:
            config = self._config_manager.get_mouse_effect_config()
            safe_config = make_json_safe(config)
            return {"success": True, "message": "鼠标点击效果配置获取成功", "data": safe_config}
        except Exception as e:
            logger.error(f"获取鼠标点击效果配置失败: {e}")
            return {"success": False, "message": f"获取鼠标点击效果配置失败: {e!s}", "data": None}

    def update_mouse_effect_config(self, mouse_effect_config: dict[str, Any]) -> dict[str, Any]:
        try:
            self._config_manager.update_mouse_effect_config(mouse_effect_config)
            return {"success": True, "message": "鼠标点击效果配置已更新"}
        except Exception as e:
            logger.error(f"更新鼠标点击效果配置失败: {e}")
            return {"success": False, "message": f"更新鼠标点击效果配置失败: {e!s}"}

    def get_locale_config(self) -> dict[str, Any]:
        try:
            config = self._config_manager.get_locale_config()
            safe_config = make_json_safe(config)
            logger.debug(f"返回语言配置: {safe_config}")
            return {"success": True, "data": safe_config, "message": "获取成功"}
        except Exception as e:
            logger.error(f"获取语言配置失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def update_locale_config(self, locale: str) -> dict[str, Any]:
        try:
            self._config_manager.update_locale_config(locale)
            return {"success": True, "message": "语言配置更新成功"}
        except Exception as e:
            logger.error(f"更新语言配置失败: {e}")
            return {"success": False, "message": str(e)}

    def select_directory(self) -> dict[str, Any]:
        try:
            root = Tk()
            root.withdraw()
            root.attributes("-topmost", True)

            selected_dir = filedialog.askdirectory(title="选择目录")
            root.destroy()

            if selected_dir:
                return {"success": True, "data": {"path": selected_dir}, "message": "目录选择成功"}
            else:
                return {"success": False, "message": "用户取消选择", "data": None}
        except Exception as e:
            logger.error(f"选择目录失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def select_java_executable(self) -> dict[str, Any]:
        try:
            root = Tk()
            root.withdraw()
            root.attributes("-topmost", True)

            result = filedialog.askopenfilename(
                title="选择 Java 可执行文件", filetypes=[("Java Executable", "*.exe;java"), ("All files", "*.*")]
            )
            root.destroy()

            if result:
                return {"success": True, "data": {"path": str(result)}, "message": "Java 路径选择成功"}
            else:
                return {"success": False, "message": "用户取消选择", "data": None}
        except Exception as e:
            logger.error(f"选择 Java 路径失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def scan_versions_in_path(self, path: str | list[str] | list[dict[str, str]]) -> dict[str, Any]:
        return {"success": True, "message": "扫描版本功能待对接", "data": []}

    def get_minecraft_versions(self, filter_type: str | None = None) -> dict[str, Any]:
        return {"success": True, "message": "版本列表功能待对接", "data": []}

    def get_fabric_versions(self) -> dict[str, Any]:
        return {"success": True, "message": "Fabric 版本列表功能待对接", "data": []}

    def install_version(self, version_id: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"success": False, "message": "安装功能待对接", "data": None}

    def uninstall_version(self, version_id: str, game_path: str | None = None) -> dict[str, Any]:
        try:
            from shutil import rmtree

            if not game_path:
                config = self._config_manager.get_game_config()
                paths = config.get("minecraft_paths", ["./.minecraft"])
                game_path = paths[0] if isinstance(paths[0], str) else paths[0].get("path", "./.minecraft")

            game_path = Path(game_path)
            version_dir = game_path / "versions" / version_id

            if not version_dir.exists():
                return {"success": False, "message": "版本不存在"}

            rmtree(version_dir)
            logger.info(f"版本 {version_id} 已卸载")

            return {"success": True, "message": f"版本 {version_id} 已卸载"}
        except Exception as e:
            logger.error(f"卸载版本失败: {e}")
            return {"success": False, "message": str(e)}

    def get_accounts(self) -> dict[str, Any]:
        try:
            accounts = self._account_manager.get_all_accounts()
            current = self._account_manager.get_current_account()
            return {
                "success": True,
                "data": {"accounts": accounts, "current": current},
                "message": f"获取到 {len(accounts)} 个账户",
            }
        except Exception as e:
            logger.error(f"获取账户列表失败: {e}")
            return {"success": False, "message": str(e), "data": {"accounts": [], "current": None}}

    def get_current_account(self) -> dict[str, Any]:
        try:
            current = self._account_manager.get_current_account()
            return {"success": True, "data": current, "message": "获取当前账户成功" if current else "未选择账户"}
        except Exception as e:
            logger.error(f"获取当前账户失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def add_offline_account(self, username: str) -> dict[str, Any]:
        try:
            result = self._account_manager.add_offline_account(username)
            return {"success": True, "data": make_json_safe(result), "message": result.get("message", "添加成功")}
        except Exception as e:
            logger.error(f"添加离线账户失败: {e}")
            return {"success": False, "message": str(e)}

    def start_microsoft_login(self) -> dict[str, Any]:
        try:
            result = self._account_manager.start_microsoft_login()

            if result.get("status") == "pending":
                verification_uri = result.get("verificationUri", "")
                user_code = result.get("userCode", "")

                if user_code:
                    try:
                        import pyperclip

                        pyperclip.copy(user_code)
                        logger.info(f"授权码已自动复制: {user_code}")
                    except Exception as copy_err:
                        logger.warning(f"自动复制授权码失败: {copy_err}")

                if verification_uri:
                    try:
                        import webbrowser

                        webbrowser.open(verification_uri)
                        logger.info(f"已自动打开浏览器: {verification_uri}")
                    except Exception as open_err:
                        logger.warning(f"自动打开浏览器失败: {open_err}")

            return {"success": True, "data": make_json_safe(result), "message": result.get("message", "请完成授权")}
        except Exception as e:
            logger.error(f"启动微软登录失败: {e}")
            return {"success": False, "message": str(e)}

    def poll_microsoft_login(self) -> dict[str, Any]:
        try:
            result = self._account_manager.poll_microsoft_login()

            if result.get("status") == "ready":
                try:
                    import webview

                    if webview.windows:
                        window = webview.windows[0]
                        window.restore()
                        window.on_top = True
                        window.on_top = False
                        logger.info("登录完成，窗口已置顶")
                except ModuleNotFoundError:
                    pass  # webview 未安装，静默跳过（如 Tauri 模式）
                except Exception as window_err:
                    logger.warning(f"窗口置顶失败: {window_err}")

            return make_json_safe(result)
        except Exception as e:
            logger.error(f"轮询微软登录状态失败: {e}")
            return {"success": False, "message": str(e)}

    def complete_microsoft_login(self) -> dict[str, Any]:
        try:
            result = self._account_manager.complete_microsoft_login()
            return {"success": True, "data": make_json_safe(result), "message": result.get("message", "登录成功")}
        except Exception as e:
            logger.error(f"完成微软登录失败: {e}")
            return {"success": False, "message": str(e)}

    def switch_account(self, account_id: str) -> dict[str, Any]:
        try:
            result = self._account_manager.switch_account(account_id)
            return {"success": True, "data": make_json_safe(result), "message": result.get("message", "切换成功")}
        except Exception as e:
            logger.error(f"切换账户失败: {e}")
            return {"success": False, "message": str(e)}

    def remove_account(self, account_id: str) -> dict[str, Any]:
        try:
            result = self._account_manager.remove_account(account_id)
            return {"success": True, "data": make_json_safe(result), "message": result.get("message", "移除成功")}
        except Exception as e:
            logger.error(f"移除账户失败: {e}")
            return {"success": False, "message": str(e)}

    def refresh_account_profile(self, account_id: str) -> dict[str, Any]:
        try:
            result = self._account_manager.refresh_account_profile(account_id)
            return {"success": True, "data": make_json_safe(result), "message": result.get("message", "刷新成功")}
        except Exception as e:
            logger.error(f"刷新账户档案失败: {e}")
            return {"success": False, "message": str(e)}

    def get_game_instances(self) -> dict[str, Any]:
        try:
            from ..game.Core.ECLauncherCore import ECLauncherCore

            core = ECLauncherCore()
            running_instances = core.instances_manager.get_instances_info()

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
        except Exception as e:
            logger.error(f"获取运行中的进程列表失败: {e}")
            return {"success": False, "message": str(e), "data": []}

    def launch_instance(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"success": False, "message": "启动功能待对接", "data": None}

    def get_launch_status(self, task_id: str) -> dict[str, Any]:
        return {"success": False, "message": "启动进度查询功能待对接", "data": None}

    def stop_instance(self, instance_id: str) -> dict[str, Any]:
        try:
            from ..game.Core.ECLauncherCore import ECLauncherCore

            core = ECLauncherCore()

            running_instances = core.instances_manager.get_instances_info()
            if not any(inst["ID"] == instance_id for inst in running_instances):
                return {"success": False, "message": "实例未在运行"}

            core.instances_manager.stop_instance(instance_id, terminate=True)

            return {"success": True, "message": "实例已停止"}
        except Exception as e:
            logger.error(f"停止实例失败: {e}")
            return {"success": False, "message": str(e)}
