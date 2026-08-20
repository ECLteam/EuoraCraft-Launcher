import base64
import hashlib
import webbrowser
from pathlib import Path
from time import time
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx
from anyio import to_thread
from pytauri_plugins.dialog import DialogExt

from ECL.api.models import (
    FileSavePurpose,
    FileSaveRequest,
    FileSelectionPurpose,
    FileSelectionRequest,
    ImagePurpose,
    ImageSelectionRequest,
)
from ECL.utils.files import atomic_write_bytes

from .bridge import (
    _MAX_REMOTE_IMAGE_SIZE,
    _download_remote_image,
    _encode_image_bytes,
    _FrontendState,
    _guess_image_extension,
    _image_mime_map,
    _ipc_handler,
    _mime_to_ext,
    _normalize_image_url,
    _open_folder,
    _read_image_data_url,
    _validate_body,
)
from .contracts import success

_REMOTE_IMAGE_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
_REMOTE_IMAGE_CACHE_MAX_FILES = 128
_REMOTE_IMAGE_CACHE_MAX_BYTES = 96 * 1024 * 1024
_MAX_FILE_READ_BYTES = 20 * 1024 * 1024

# 图片选择对话框按用途映射标题与允许的扩展名。
_IMAGE_SELECTION_OPTIONS: dict[ImagePurpose, tuple[str, list[str]]] = {
    ImagePurpose.SKIN: ("选择 Minecraft 皮肤", ["png"]),
    ImagePurpose.CAPE: ("选择 Minecraft 披风", ["png"]),
    ImagePurpose.INSTANCE_ICON: ("选择实例图标", ["png", "jpg", "jpeg", "gif", "bmp", "webp"]),
    ImagePurpose.BACKGROUND: ("选择背景图片", ["png", "jpg", "jpeg", "gif", "bmp", "webp"]),
}

# 文件保存对话框按导出用途映射标题、默认文件名与允许的扩展名。
_SAVE_FILE_OPTIONS: dict[FileSavePurpose, tuple[str, str, list[str]]] = {
    FileSavePurpose.CRASH_REPORT: ("保存 Minecraft 崩溃报告", "EuoraCraft-crash-report.zip", ["zip"]),
    FileSavePurpose.LAUNCHER_LOGS: ("保存 EuoraCraft 启动器日志", "EuoraCraft-logs.zip", ["zip"]),
    FileSavePurpose.WORLD_EXPORT: ("导出 Minecraft 存档", "world.zip", ["zip"]),
    FileSavePurpose.INSTANCE_EXPORT: ("导出实例整合包", "instance.zip", ["zip"]),
    FileSavePurpose.SCREENSHOT: ("另存 Minecraft 截图", "screenshot.png", ["png", "jpg", "jpeg", "webp", "gif", "bmp"]),
    FileSavePurpose.RESOURCE_MANIFEST: ("导出资源清单", "resources.json", ["json", "csv"]),
    FileSavePurpose.MOD_FILE: ("另存模组文件", "mod.jar", ["jar", "zip"]),
}


class FileHandlers(_FrontendState):
    """提供本地文件与图片读取、远程图片缓存及本地选择的正式 IPC 边界。"""

    @staticmethod
    def _remote_image_cache_dir(data_path: Path) -> Path:
        """返回远程图片持久化缓存目录。"""
        return data_path / "cache" / "remote-images"

    @staticmethod
    def _remote_image_digest(url: str) -> str:
        """按远程 URL 生成稳定缓存摘要键。"""
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def _read_remote_image_cache(self, url: str) -> tuple[bytes, str, bool] | None:
        """
        按远程 URL 读取持久化图片缓存，并返回其新鲜度。

        :param url: 已完成协议和主机校验的远程图片地址
        :return: 图片字节、扩展名和是否仍在刷新周期内；未命中返回 ``None``
        """
        cache_dir = self._remote_image_cache_dir(self.data_path)
        digest = self._remote_image_digest(url)
        for extension in _image_mime_map:
            candidate = cache_dir / f"{digest}{extension}"
            try:
                stat = candidate.stat()
                if not candidate.is_file() or candidate.is_symlink() or stat.st_size <= 0 or stat.st_size > _MAX_REMOTE_IMAGE_SIZE:
                    continue
                return candidate.read_bytes(), extension, time() - stat.st_mtime <= _REMOTE_IMAGE_CACHE_TTL_SECONDS
            except OSError:
                continue
        return None

    def _write_remote_image_cache(self, url: str, extension: str, image_bytes: bytes) -> None:
        """
        原子写入远程图片缓存，并按最近使用时间限制缓存规模。

        :param url: 用于生成稳定缓存键的远程图片地址
        :param extension: 已根据响应头识别且在白名单内的图片扩展名
        :param image_bytes: 已经过远程下载大小限制的图片内容
        """
        cache_dir = self._remote_image_cache_dir(self.data_path)
        digest = self._remote_image_digest(url)
        safe_extension = extension if extension in _image_mime_map else ".jpg"
        target = cache_dir / f"{digest}{safe_extension}"
        atomic_write_bytes(target, image_bytes)

        entries: list[tuple[Path, int, float]] = []
        for candidate in cache_dir.iterdir():
            try:
                if candidate.is_symlink() or not candidate.is_file() or candidate.suffix.lower() not in _image_mime_map:
                    continue
                stat = candidate.stat()
                entries.append((candidate, stat.st_size, stat.st_mtime))
            except OSError:
                continue
        entries.sort(key=lambda item: item[2], reverse=True)
        retained_bytes = 0
        for index, (candidate, size, _mtime) in enumerate(entries):
            retained_bytes += size
            if index < _REMOTE_IMAGE_CACHE_MAX_FILES and retained_bytes <= _REMOTE_IMAGE_CACHE_MAX_BYTES:
                continue
            try:
                candidate.unlink()
            except OSError:
                self.logger.debug("清理远程图片缓存失败: %s", candidate, exc_info=True)

    @_ipc_handler("FILE_RESOLVE_FAILED")
    async def file_resolve(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        规整本地路径，供前端转换为可访问的资源 URL。

        :param body: 包含 ``path`` 的请求数据
        :return: 绝对路径及其存在状态
        """
        raw_path = body.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip() or "\0" in raw_path:
            return {"success": False, "message": "路径无效", "errorCode": "INVALID_PATH"}
        path = Path(self._normalize_file_path(raw_path)).expanduser().resolve(strict=False)
        return {"success": True, "data": {"path": str(path)}}

    @_ipc_handler("FS_EXISTS_FAILED")
    async def fs_exists(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        查询本地路径类型，不修改文件系统。

        :param body: 包含 ``path`` 的请求数据
        :return: 路径是否存在以及目录、文件类型标记
        """
        raw_path = body.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip() or "\0" in raw_path:
            return {"success": False, "message": "路径无效", "errorCode": "INVALID_PATH"}
        path = Path(self._normalize_file_path(raw_path)).expanduser()
        return {
            "success": True,
            "data": {"exists": path.exists(), "is_dir": path.is_dir(), "is_file": path.is_file()},
        }

    @_ipc_handler("FS_READ_DIR_FAILED")
    async def fs_read_dir(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        读取指定目录的一层条目及基础元数据。

        :param body: 包含 ``path`` 的请求数据
        :return: 按名称排序的目录条目
        """
        raw_path = body.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip() or "\0" in raw_path:
            return {"success": False, "message": "路径无效", "errorCode": "INVALID_PATH"}
        path = Path(self._normalize_file_path(raw_path)).expanduser()
        if not path.is_dir():
            return {"success": False, "message": "目录不存在", "errorCode": "DIRECTORY_NOT_FOUND"}

        def read_entries() -> list[dict[str, Any]]:
            entries = []
            for entry in path.iterdir():
                stat = entry.stat()
                entries.append(
                    {
                        "name": entry.name,
                        "is_dir": entry.is_dir(),
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                    }
                )
            return sorted(entries, key=lambda item: str(item["name"]).casefold())

        return {"success": True, "data": await to_thread.run_sync(read_entries)}

    @_ipc_handler("FS_READ_FILE_FAILED")
    async def fs_read_file(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        以 UTF-8 文本或 Base64 读取大小受限的本地文件。

        :param body: 包含 ``path`` 和可选 ``mode`` 的请求数据
        :return: 文件内容与原始字节数
        """
        raw_path = body.get("path")
        mode = body.get("mode", "text")
        if not isinstance(raw_path, str) or not raw_path.strip() or "\0" in raw_path:
            return {"success": False, "message": "路径无效", "errorCode": "INVALID_PATH"}
        if mode not in {"text", "base64"}:
            return {"success": False, "message": "文件读取模式无效", "errorCode": "INVALID_FILE_MODE"}
        path = Path(self._normalize_file_path(raw_path)).expanduser()
        if not path.is_file():
            return {"success": False, "message": "文件不存在", "errorCode": "FILE_NOT_FOUND"}
        if path.stat().st_size > _MAX_FILE_READ_BYTES:
            return {"success": False, "message": "文件超过 20 MiB 读取限制", "errorCode": "FILE_TOO_LARGE"}
        content = await to_thread.run_sync(path.read_bytes)
        encoded = base64.b64encode(content).decode("ascii") if mode == "base64" else content.decode("utf-8")
        return {"success": True, "data": {"content": encoded, "size": len(content)}}

    @_ipc_handler("IMAGE_FETCH_FAILED")
    async def image_fetch_data_url(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        下载远程图片并转换为受大小限制的 Data URL。

        :param body: 包含 HTTP(S) 图片 ``url`` 的请求数据
        :return: Data URL、Base64 数据和原始 URL
        """
        url = _normalize_image_url(body.get("url"))
        if url is None:
            return {"success": False, "message": "无效的图片 URL", "errorCode": "INVALID_IMAGE_URL"}
        cached = await to_thread.run_sync(self._read_remote_image_cache, url)
        if cached is not None and cached[2]:
            image_bytes, extension, _fresh = cached
            data_url, encoded = await to_thread.run_sync(_encode_image_bytes, image_bytes, extension)
            return {
                "success": True,
                "data": {"dataUrl": data_url, "base64": encoded, "url": url, "cached": True},
            }
        try:
            image_bytes, response = await _download_remote_image(url)
            extension = _guess_image_extension(response, url)
        except (httpx.HTTPError, OSError, ValueError):
            if cached is None:
                raise
            image_bytes, extension, _fresh = cached
            self.logger.warning("远程图片刷新失败，继续使用磁盘缓存: %s", url)
            data_url, encoded = await to_thread.run_sync(_encode_image_bytes, image_bytes, extension)
            return {
                "success": True,
                "data": {"dataUrl": data_url, "base64": encoded, "url": url, "cached": True, "stale": True},
            }
        try:
            await to_thread.run_sync(self._write_remote_image_cache, url, extension, image_bytes)
        except OSError:
            self.logger.warning("远程图片缓存写入失败，本次仍使用已下载内容: %s", url, exc_info=True)
        data_url, encoded = await to_thread.run_sync(_encode_image_bytes, image_bytes, extension)
        return {
            "success": True,
            "data": {"dataUrl": data_url, "base64": encoded, "url": url, "cached": False},
        }

    @_ipc_handler("IMAGE_SAVE_URL_ERROR")
    async def image_save_url(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        下载背景图片并缓存到本地数据目录。

        :param body: 经过边界校验的 IPC 请求数据
        """
        url = _normalize_image_url(body.get("url"))
        if url is None:
            return {"success": False, "message": "无效的图片 URL", "errorCode": "INVALID_IMAGE_URL"}

        image_bytes, response = await _download_remote_image(url)
        ext = _guess_image_extension(response, url)
        data_url, b64 = await to_thread.run_sync(_encode_image_bytes, image_bytes, ext)

        local_path: str | None = None
        try:
            local_path = await to_thread.run_sync(self._persist_background_image, data_url)
        except (OSError, ValueError):
            self.logger.exception("背景图落盘失败，仅返回内存数据: %s", url)

        self.logger.info("远程背景图已原样保存: %s, ext=%s, base64_len=%d", url, ext, len(b64))
        return {
            "success": True,
            "data": {"dataUrl": data_url, "base64": b64, "url": url, "path": local_path},
        }

    @staticmethod
    def _parse_image_data_url(data_url: str) -> tuple[bytes, str]:
        """
        解析 Data URL 为原始图片字节与 MIME 类型。

        :param data_url: 形如 ``data:<mime>;base64,<payload>`` 的图片数据
        :return: ``(图片字节, MIME 类型)``
        :raises ValueError: Data URL 格式不合法或 Base64 解码失败
        """
        header, b64 = data_url.split(",", 1)
        mime = header.split(";")[0].split(":", 1)[1] if ":" in header else "image/png"
        return base64.b64decode(b64), mime

    def _persist_background_image(self, data_url: str) -> str:
        """
        将编码后的图片写入数据目录下的背景图缓存目录，返回本地路径。

        :param data_url: 需要解码并保存的 Data URL
        """
        try:
            payload, mime = self._parse_image_data_url(data_url)
        except (ValueError, base64.binascii.Error) as exc:
            raise ValueError(f"无法解析图片数据: {exc}") from exc
        ext = _mime_to_ext.get(mime, ".jpg")
        digest = hashlib.sha1(payload).hexdigest()[:16]
        target_dir = self.data_path / "backgrounds"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{digest}{ext}"
        if not target.is_file():
            target.write_bytes(payload)
        return str(target)

    @_ipc_handler("IMAGE_SAVE_AS_ERROR")
    async def image_save_as(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        保存背景图片。

        :param body: 经过边界校验的 IPC 请求数据
        """
        data_url = body.get("data_url") or body.get("dataUrl") or ""
        url = body.get("url") or ""
        path = body.get("path") or ""

        image_bytes: bytes | None = None
        default_name = "background.png"

        if isinstance(data_url, str) and data_url.startswith("data:"):
            try:
                image_bytes, mime = self._parse_image_data_url(data_url)
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
        """将 file:// URL 规整为本地文件系统路径。"""
        if path.startswith("file://"):
            parsed = urlsplit(path)
            return unquote(parsed.path)
        return path

    @_ipc_handler("IMAGE_READ_ERROR")
    async def image_read_file(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        读取图片（带 LRU 缓存）。

        :param body: 经过边界校验的 IPC 请求数据
        """
        raw_path = body.get("path", "")
        if not raw_path:
            return {"success": False, "message": "路径不能为空", "errorCode": "INVALID_PATH"}

        path = self._normalize_file_path(raw_path)
        file_path = Path(path)
        if not file_path.is_file():
            self.logger.warning("图片文件不存在: %s", file_path)
            return {"success": False, "message": "图片文件不存在", "errorCode": "FILE_NOT_FOUND"}

        try:
            stat = file_path.stat()
        except OSError:
            return {"success": False, "message": "图片文件不存在", "errorCode": "FILE_NOT_FOUND"}

        # 使用 bridge 的 functools LRU 缓存（键含 mtime_ns 与 size，文件变化自动失效）
        data_url, mime, base64_len = await to_thread.run_sync(
            _read_image_data_url, file_path, stat.st_mtime_ns, stat.st_size
        )
        self.logger.info("图片读取成功: %s, mime=%s, base64_len=%d", file_path, mime, base64_len)
        return {
            "success": True,
            "data": {"dataUrl": data_url},
        }

    @_ipc_handler("IMAGE_LIST_FILES_ERROR")
    async def image_list_files(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取图片列表。

        :param body: 经过边界校验的 IPC 请求数据
        """
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

    async def _pick_path(self, pick_folder: bool, title: str, extensions: list[str] | None = None) -> str:
        """打开系统文件选择对话框，返回用户选择的路径；取消时返回空字符串。"""
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

    async def _pick_save_path(self, title: str, default_name: str, extensions: list[str], filter_label: str = "ZIP 压缩包") -> str:
        """
        在 Tauri 主窗口上打开系统文件保存对话框。

        :param title: 系统对话框标题
        :param default_name: 预填充且不包含目录部分的文件名
        :param extensions: 允许用户选择的扩展名列表
        :param filter_label: 系统对话框中的文件类型筛选标签
        :return: 用户确认的绝对路径；取消时返回空字符串
        """
        if self._webview is None:
            return ""

        file_path = await to_thread.run_sync(
            lambda: DialogExt.file(self._webview).blocking_save_file(
                add_filter=(filter_label, extensions),
                set_file_name=default_name,
                set_title=title,
            )
        )
        return self._normalize_file_path(str(file_path)) if file_path else ""

    @_ipc_handler("SELECT_DIRECTORY_ERROR")
    async def select_directory(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        选择目录。

        :param body: 经过边界校验的 IPC 请求数据
        """
        path = await self._pick_path(True, "选择游戏目录")
        self.logger.info("目录选择结果: %s", path)
        return {"success": True, "data": {"path": path}}

    @_ipc_handler("SELECT_JAVA_ERROR")
    async def select_java(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        选择 Java。

        :param body: 经过边界校验的 IPC 请求数据
        """
        path = await self._pick_path(False, "选择 Java 可执行文件")
        self.logger.info("Java 选择结果: %s", path)
        return {"success": True, "data": {"path": path}}

    @_ipc_handler("SELECT_IMAGE_ERROR")
    async def select_image(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        按使用场景选择图片；皮肤和披风只允许 PNG。

        :param body: 包含可选图片用途的 IPC 请求数据
        :return: 用户选择的本地绝对路径，取消时路径为空
        """
        request, invalid = _validate_body(ImageSelectionRequest, body)
        if invalid is not None:
            return invalid
        title, extensions = _IMAGE_SELECTION_OPTIONS.get(
            request.purpose, ("选择背景图片", ["png", "jpg", "jpeg", "gif", "bmp", "webp"])
        )
        path = await self._pick_path(False, title, extensions)
        self.logger.info("图片选择结果: %s", path)
        return {"success": True, "data": {"path": path, "base64": ""}}

    @_ipc_handler("SELECT_FILE_ERROR")
    async def select_file(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        选择文件。

        :param body: 经过边界校验的 IPC 请求数据
        """
        request, invalid = _validate_body(FileSelectionRequest, body)
        if invalid is not None:
            return invalid
        if request.purpose == FileSelectionPurpose.CRASH_ANALYSIS:
            path = await self._pick_path(False, "选择 Minecraft 崩溃日志", ["log", "txt", "zip"])
        else:
            path = await self._pick_path(False, "选择文件")
        self.logger.info("文件选择结果: %s", path)
        return {"success": True, "data": {"path": path}}

    @_ipc_handler("SELECT_FILES_ERROR")
    async def select_files(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        按实例工作台用途选择多个本地文件。
        """
        request, invalid = _validate_body(FileSelectionRequest, body)
        if invalid is not None:
            return invalid
        if self._webview is None:
            return success({"paths": []})

        def pick_files():
            dialog = DialogExt.file(self._webview)
            if request.purpose == FileSelectionPurpose.RESOURCE_FILES:
                return dialog.blocking_pick_files(add_filter=("资源文件", ["jar", "zip", "disabled", "schem", "litematic"]))
            return dialog.blocking_pick_files(set_title="选择文件")

        selected = await to_thread.run_sync(pick_files)
        paths = [self._normalize_file_path(str(path)) for path in (selected or [])]
        return success({"paths": paths})

    @_ipc_handler("SELECT_SAVE_FILE_ERROR")
    async def select_save_file(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        按导出用途打开系统 ZIP 文件保存对话框。

        该命令只选择目标路径，不写入任何内容；实际导出仍由对应业务命令负责。

        :param body: 符合 ``FileSaveRequest`` 的导出用途
        :return: 用户选择的 ZIP 绝对路径；取消时路径为空
        """
        request, invalid = _validate_body(FileSaveRequest, body)
        if invalid is not None:
            return invalid
        title, default_name, extensions = _SAVE_FILE_OPTIONS.get(
            request.purpose, ("导出资源清单", "resources.json", ["zip"])
        )
        filter_label = "JAR 文件" if request.purpose == FileSavePurpose.MOD_FILE else "ZIP 压缩包"
        selected = await self._pick_save_path(title, default_name, extensions, filter_label)
        if (
            selected
            and request.purpose
            not in {FileSavePurpose.RESOURCE_MANIFEST, FileSavePurpose.SCREENSHOT, FileSavePurpose.MOD_FILE}
            and Path(selected).suffix.casefold() != ".zip"
        ):
            selected = str(Path(selected).with_suffix(".zip"))
        self.logger.info("导出文件保存路径选择完成: purpose=%s, selected=%s", request.purpose.value, bool(selected))
        return success({"path": selected})

    @_ipc_handler("OPEN_FOLDER_FAILED")
    async def open_folder(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        打开目录。

        :param body: 经过边界校验的 IPC 请求数据
        """
        path = body.get("path")
        if not isinstance(path, str) or not path.strip():
            return {"success": False, "message": "路径不能为空", "errorCode": "INVALID_PATH"}
        await to_thread.run_sync(_open_folder, path)
        self.logger.info("已打开文件夹: %s", path)
        return {"success": True, "data": None}

    @_ipc_handler("OPEN_URL_FAILED")
    async def open_url(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        打开链接。

        :param body: 经过边界校验的 IPC 请求数据
        """
        url = body.get("url")
        if not isinstance(url, str) or not url.strip():
            return {"success": False, "message": "URL 不能为空", "errorCode": "INVALID_URL"}
        opened = webbrowser.open(url.strip())
        self.logger.info("已在默认浏览器中打开: %s", url)
        return {"success": True, "data": opened}
