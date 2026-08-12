import base64
import hashlib
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from anyio import to_thread
from pydantic import ValidationError
from pytauri_plugins.dialog import DialogExt

from ECL.api.models import ImagePurpose, ImageSelectionRequest

from .bridge import (
    _download_remote_image,
    _encode_image_bytes,
    _ext_to_mime,
    _FrontendState,
    _guess_image_extension,
    _image_cache_get,
    _image_cache_key,
    _image_cache_put,
    _image_mime_map,
    _ipc_handler,
    _mime_to_ext,
    _normalize_image_url,
    _open_folder,
)


class FileHandlers(_FrontendState):
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
        if path.stat().st_size > 20 * 1024 * 1024:
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
        image_bytes, response = await _download_remote_image(url)
        extension = _guess_image_extension(response, url)
        data_url, encoded = await to_thread.run_sync(_encode_image_bytes, image_bytes, extension)
        return {"success": True, "data": {"dataUrl": data_url, "base64": encoded, "url": url}}

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

    def _persist_background_image(self, data_url: str) -> str:
        """
        将编码后的图片写入数据目录下的背景图缓存目录，返回本地路径。

        :param data_url: 需要解码并保存的 Data URL
        """
        try:
            header, b64 = data_url.split(",", 1)
            mime = header.split(";")[0].split(":", 1)[1] if ":" in header else "image/png"
            payload = base64.b64decode(b64)
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
        """
        读取图片（带 LRU 缓存）。

        :param body: 经过边界校验的 IPC 请求数据
        """
        raw_path = body.get("path", "")
        if not raw_path:
            return {"success": False, "message": "路径不能为空", "errorCode": "INVALID_PATH"}

        path = self._normalize_file_path(raw_path)
        file_path = Path(path)
        cache_key = _image_cache_key(file_path)

        cached = _image_cache_get(cache_key)
        if cached is not None:
            return {"success": True, "data": {"dataUrl": cached}}

        def _read() -> dict[str, str] | None:
            if not file_path.is_file():
                self.logger.warning("图片文件不存在: %s", file_path)
                return None
            ext = file_path.suffix.lower() or ".png"
            data_url, b64 = _encode_image_bytes(file_path.read_bytes(), ext)
            mime = _ext_to_mime.get(ext, "image/jpeg")
            return {"dataUrl": data_url, "b64": b64, "mime": mime}

        result = await to_thread.run_sync(_read)
        if result is None:
            return {"success": False, "message": "图片文件不存在", "errorCode": "FILE_NOT_FOUND"}
        _image_cache_put(cache_key, result["dataUrl"])
        self.logger.info("图片读取成功: %s, mime=%s, base64_len=%d", file_path, result["mime"], len(result["b64"]))
        return {
            "success": True,
            "data": {"dataUrl": result["dataUrl"]},
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
        try:
            request = ImageSelectionRequest.model_validate(body)
        except ValidationError as exc:
            return self._invalid_request(exc)
        if request.purpose == ImagePurpose.SKIN:
            title = "选择 Minecraft 皮肤"
            extensions = ["png"]
        elif request.purpose == ImagePurpose.CAPE:
            title = "选择 Minecraft 披风"
            extensions = ["png"]
        else:
            title = "选择背景图片"
            extensions = ["png", "jpg", "jpeg", "gif", "bmp", "webp"]
        path = await self._pick_path(False, title, extensions)
        self.logger.info("图片选择结果: %s", path)
        return {"success": True, "data": {"path": path, "base64": ""}}

    @_ipc_handler("SELECT_FILE_ERROR")
    async def select_file(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        选择文件。

        :param body: 经过边界校验的 IPC 请求数据
        """
        path = await self._pick_path(False, "选择文件")
        self.logger.info("文件选择结果: %s", path)
        return {"success": True, "data": {"path": path}}

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
