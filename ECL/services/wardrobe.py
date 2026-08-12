from __future__ import annotations

import hashlib
import json
import logging
import struct
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Literal, TypedDict
from uuid import uuid4

from ECL.utils import atomic_write_bytes, atomic_write_text

logger = logging.getLogger("EuoraCraft-Launcher.Wardrobe")

WardrobeKind = Literal["skin", "cape"]
SkinModel = Literal["classic", "slim"]

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_TEXTURE_BYTES = 5 * 1024 * 1024
MAX_TEXTURE_DIMENSION = 1024


class WardrobeError(RuntimeError):
    """
    表示可安全返回给前端的衣柜业务错误。

    :param message: 面向用户的错误说明
    :param error_code: 供 IPC 和前端稳定识别的错误码
    """

    def __init__(self, message: str, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class WardrobeItem(TypedDict):
    id: str
    kind: WardrobeKind
    name: str
    model: SkinModel | None
    favorite: bool
    width: int
    height: int
    byteSize: int
    sha256: str
    createdAt: str
    updatedAt: str


class WardrobeStore:
    """
    管理本地皮肤与披风收藏，并保证元数据和纹理文件始终位于衣柜目录中。

    本服务不解码、裁切或转换图片，只读取 PNG 文件头中的尺寸。文件复制和元数据
    写入均使用同目录临时文件与原子替换，避免应用中断后留下半写入数据。

    :param data_path: 启动器持久化数据目录
    """

    def __init__(self, data_path: Path) -> None:
        self.root = data_path / "wardrobe"
        self.metadata_path = self.root / "wardrobe.json"
        self.skin_path = self.root / "skins"
        self.cape_path = self.root / "capes"
        # 保护一次运行中的元数据读改写；外部账户上传不持有此锁。
        self._lock = RLock()
        self.root.mkdir(parents=True, exist_ok=True)
        self.skin_path.mkdir(parents=True, exist_ok=True)
        self.cape_path.mkdir(parents=True, exist_ok=True)
        self._items = self._load_items()
        self._cleanup_files()

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _png_dimensions(data: bytes) -> tuple[int, int]:
        """
        从 PNG 签名和 IHDR 块读取尺寸，不让后端参与图片解码。

        :param data: 完整的 PNG 原始字节
        :return: 图片宽度和高度
        """
        if len(data) < 24 or data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
            raise WardrobeError("请选择有效的 PNG 图片", "WARDROBE_INVALID_PNG")
        width, height = struct.unpack(">II", data[16:24])
        if width <= 0 or height <= 0:
            raise WardrobeError("PNG 图片尺寸无效", "WARDROBE_INVALID_PNG")
        return width, height

    @staticmethod
    def _validate_dimensions(kind: WardrobeKind, width: int, height: int) -> None:
        if width > MAX_TEXTURE_DIMENSION or height > MAX_TEXTURE_DIMENSION:
            raise WardrobeError("纹理尺寸不能超过 1024×1024", "WARDROBE_INVALID_DIMENSIONS")
        scale, remainder = divmod(width, 64)
        if scale < 1 or remainder:
            raise WardrobeError("纹理宽度必须是 64 的整数倍", "WARDROBE_INVALID_DIMENSIONS")
        valid_heights = {32 * scale} if kind == "cape" else {32 * scale, 64 * scale}
        if height not in valid_heights:
            description = "64×32 的整数倍" if kind == "cape" else "64×32 或 64×64 的整数倍"
            raise WardrobeError(f"纹理尺寸必须是 {description}", "WARDROBE_INVALID_DIMENSIONS")

    def _load_items(self) -> list[WardrobeItem]:
        if not self.metadata_path.is_file():
            return []
        try:
            document = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            if document.get("version") != 1 or not isinstance(document.get("items"), list):
                raise ValueError("不支持的衣柜元数据格式")
            required = {
                "id",
                "kind",
                "name",
                "model",
                "width",
                "height",
                "byteSize",
                "sha256",
                "createdAt",
                "updatedAt",
            }
            items = document["items"]
            if any(
                not isinstance(item, dict)
                or not required.issubset(item)
                or item.get("kind") not in {"skin", "cape"}
                or not isinstance(item.get("sha256"), str)
                or len(item["sha256"]) != 64
                or any(character not in "0123456789abcdef" for character in item["sha256"])
                for item in items
            ):
                raise ValueError("衣柜条目格式无效")
            for item in items:
                item["favorite"] = bool(item.get("favorite", False))
            return items
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            backup = self.metadata_path.with_name(
                f"wardrobe.corrupt-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.json"
            )
            try:
                self.metadata_path.replace(backup)
            except OSError:
                logger.exception("备份损坏的衣柜元数据失败")
                raise WardrobeError("衣柜数据损坏且无法备份", "WARDROBE_METADATA_INVALID") from exc
            logger.warning("衣柜元数据损坏，已备份后重建: %s", backup.name)
            return []

    def _save_items(self) -> None:
        document = {"version": 1, "items": self._items}
        atomic_write_text(self.metadata_path, json.dumps(document, ensure_ascii=False, indent=2))

    def _texture_path(self, item: WardrobeItem) -> Path:
        directory = self.skin_path if item["kind"] == "skin" else self.cape_path
        target = (directory / f"{item['sha256']}.png").resolve()
        if not target.is_relative_to(directory.resolve()):
            raise WardrobeError("衣柜纹理路径越界", "WARDROBE_PATH_ESCAPE")
        return target

    def _cleanup_files(self) -> None:
        referenced = {self._texture_path(item) for item in self._items}
        for directory in (self.skin_path, self.cape_path):
            for path in directory.iterdir():
                if path.name.endswith(".tmp") or (path.suffix.lower() == ".png" and path.resolve() not in referenced):
                    try:
                        path.unlink()
                    except OSError:
                        logger.warning("清理衣柜孤立文件失败: %s", path.name)

    def list_items(self) -> list[WardrobeItem]:
        """
        返回按最近更新时间排序的衣柜条目副本。

        :return: 不包含本地绝对路径的衣柜元数据列表
        """
        with self._lock:
            return sorted(
                deepcopy(self._items),
                key=lambda item: (item.get("favorite", False), item["updatedAt"]),
                reverse=True,
            )

    def import_file(
        self,
        source: Path,
        kind: WardrobeKind,
        name: str | None = None,
        model: SkinModel | None = None,
    ) -> tuple[WardrobeItem, bool]:
        """
        校验并复制用户选择的 PNG 文件；重复内容直接返回已有收藏。

        :param source: 由文件选择器返回的本地源文件
        :param kind: 素材类型，皮肤或披风
        :param name: 可选显示名称，默认使用文件名
        :param model: 皮肤手臂模型；披风必须为空
        :return: 衣柜条目以及是否命中重复内容
        """
        if not source.is_file():
            raise WardrobeError("选择的文件不存在", "WARDROBE_FILE_NOT_FOUND")
        size = source.stat().st_size
        if size > MAX_TEXTURE_BYTES:
            raise WardrobeError("纹理文件不能超过 5 MiB", "WARDROBE_FILE_TOO_LARGE")
        try:
            data = source.read_bytes()
        except OSError as exc:
            raise WardrobeError("读取纹理文件失败", "WARDROBE_FILE_READ_FAILED") from exc
        return self.import_bytes(data, kind, name or source.stem, model)

    def import_bytes(
        self,
        data: bytes,
        kind: WardrobeKind,
        name: str,
        model: SkinModel | None = None,
    ) -> tuple[WardrobeItem, bool]:
        """
        校验并持久化来自可信下载边界的 PNG 字节，沿用本地导入的哈希去重规则。

        :param data: 已完成网络大小限制或本地文件限制检查的 PNG 原始字节
        :param kind: 素材类型，皮肤或披风
        :param name: 衣柜中展示的素材名称
        :param model: 皮肤手臂模型；披风必须为空
        :return: 衣柜条目以及是否命中重复内容
        """
        if len(data) > MAX_TEXTURE_BYTES:
            raise WardrobeError("纹理文件不能超过 5 MiB", "WARDROBE_FILE_TOO_LARGE")
        width, height = self._png_dimensions(data)
        self._validate_dimensions(kind, width, height)
        digest = hashlib.sha256(data).hexdigest()

        with self._lock:
            existing = next(
                (item for item in self._items if item["kind"] == kind and item["sha256"] == digest),
                None,
            )
            if existing is not None:
                logger.debug("衣柜导入命中重复纹理: kind=%s, hash=%s", kind, digest[:12])
                return deepcopy(existing), True

            normalized_name = name.strip()[:80] or "未命名纹理"
            timestamp = self._timestamp()
            item: WardrobeItem = {
                "id": uuid4().hex,
                "kind": kind,
                "name": normalized_name,
                "model": (model or "classic") if kind == "skin" else None,
                "favorite": False,
                "width": width,
                "height": height,
                "byteSize": len(data),
                "sha256": digest,
                "createdAt": timestamp,
                "updatedAt": timestamp,
            }
            atomic_write_bytes(self._texture_path(item), data)
            self._items.append(item)
            try:
                self._save_items()
            except OSError:
                self._items.pop()
                self._texture_path(item).unlink(missing_ok=True)
                raise
            logger.info("已导入本地衣柜纹理: kind=%s, size=%dx%d, hash=%s", kind, width, height, digest[:12])
            return deepcopy(item), False

    def update_item(
        self,
        item_id: str,
        name: str | None,
        model: SkinModel | None,
        favorite: bool | None = None,
    ) -> WardrobeItem:
        """
        更新衣柜条目的展示信息，不修改原始纹理字节。

        :param item_id: 衣柜条目稳定标识
        :param name: 新显示名称，为空时保持原值
        :param model: 皮肤手臂模型；披风忽略此字段
        :param favorite: 是否收藏并置顶；为空时保持原状态
        :return: 更新后的衣柜条目
        """
        with self._lock:
            item = self._find_item(item_id)
            if name is not None:
                normalized = name.strip()[:80]
                if not normalized:
                    raise WardrobeError("衣柜名称不能为空", "WARDROBE_INVALID_NAME")
                item["name"] = normalized
            if model is not None and item["kind"] == "skin":
                item["model"] = model
            if favorite is not None:
                item["favorite"] = favorite
            item["updatedAt"] = self._timestamp()
            self._save_items()
            return deepcopy(item)

    def delete_item(self, item_id: str) -> None:
        """
        删除衣柜元数据和对应内部纹理，不影响已经上传到外部账户的皮肤。

        :param item_id: 衣柜条目稳定标识
        """
        with self._lock:
            item = self._find_item(item_id)
            self._items.remove(item)
            self._save_items()
            try:
                self._texture_path(item).unlink(missing_ok=True)
            except OSError:
                logger.warning("删除衣柜纹理失败，后续启动会再次清理: %s", item["sha256"][:12])
            logger.info("已删除本地衣柜纹理: kind=%s, hash=%s", item["kind"], item["sha256"][:12])

    def read_texture(self, item_id: str) -> tuple[WardrobeItem, bytes]:
        """
        读取内部纹理原始字节，供前端预览或账户服务上传。

        :param item_id: 衣柜条目稳定标识
        :return: 衣柜元数据和未转换的 PNG 字节
        """
        with self._lock:
            item = deepcopy(self._find_item(item_id))
            path = self._texture_path(item)
        try:
            return item, path.read_bytes()
        except OSError as exc:
            raise WardrobeError("衣柜纹理文件不存在", "WARDROBE_FILE_NOT_FOUND") from exc

    def _find_item(self, item_id: str) -> WardrobeItem:
        item = next((candidate for candidate in self._items if candidate["id"] == item_id), None)
        if item is None:
            raise WardrobeError("衣柜条目不存在", "WARDROBE_ITEM_NOT_FOUND")
        return item


__all__ = ["SkinModel", "WardrobeError", "WardrobeItem", "WardrobeKind", "WardrobeStore"]
