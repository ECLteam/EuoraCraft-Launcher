from __future__ import annotations

import gzip
import os
import shutil
import struct
from pathlib import Path
from typing import Any

from ..common.logger import get_logger

logger = get_logger("resources.manager")


class ResourceManager:

    # ── 资源包 ──

    @staticmethod
    def list_resourcepacks(game_path: str) -> list[dict[str, Any]]:
        rp_dir = Path(game_path) / "resourcepacks"
        return ResourceManager._list_dir_items(rp_dir)

    @staticmethod
    def remove_resourcepack(game_path: str, filename: str) -> dict[str, Any]:
        rp_dir = Path(game_path) / "resourcepacks"
        return ResourceManager._remove_item(rp_dir, filename, "资源包")

    @staticmethod
    def open_resourcepacks_folder(game_path: str) -> dict[str, Any]:
        rp_dir = Path(game_path) / "resourcepacks"
        rp_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(rp_dir))
        return {"success": True, "path": str(rp_dir)}

    # ── 光影包 ──

    @staticmethod
    def list_shaderpacks(game_path: str) -> list[dict[str, Any]]:
        sp_dir = Path(game_path) / "shaderpacks"
        return ResourceManager._list_dir_items(sp_dir)

    @staticmethod
    def remove_shaderpack(game_path: str, filename: str) -> dict[str, Any]:
        sp_dir = Path(game_path) / "shaderpacks"
        return ResourceManager._remove_item(sp_dir, filename, "光影包")

    @staticmethod
    def open_shaderpacks_folder(game_path: str) -> dict[str, Any]:
        sp_dir = Path(game_path) / "shaderpacks"
        sp_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(sp_dir))
        return {"success": True, "path": str(sp_dir)}

    # ── 存档 ──

    @staticmethod
    def list_saves(game_path: str) -> list[dict[str, Any]]:
        saves_dir = Path(game_path) / "saves"
        if not saves_dir.is_dir():
            return []

        saves = []
        for entry in sorted(saves_dir.iterdir()):
            if not entry.is_dir():
                continue
            level_dat = entry / "level.dat"
            info: dict[str, Any] = {
                "filename": entry.name,
                "size": 0,
                "is_folder": True,
                "level_name": entry.name,
                "game_type": "未知",
                "last_played": 0,
            }

            try:
                total = 0
                for f in entry.rglob("*"):
                    if f.is_file():
                        try:
                            total += f.stat().st_size
                        except OSError:
                            pass
                info["size"] = total
            except OSError:
                pass

            if level_dat.is_file():
                nbt_info = ResourceManager._parse_level_dat(str(level_dat))
                info["level_name"] = nbt_info.get("level_name", entry.name)
                info["game_type"] = nbt_info.get("game_type", "未知")
                info["last_played"] = nbt_info.get("last_played", 0)

            saves.append(info)

        return saves

    @staticmethod
    def delete_save(game_path: str, save_name: str) -> dict[str, Any]:
        saves_dir = Path(game_path) / "saves"
        save_path = saves_dir / save_name
        if not save_path.exists():
            return {"success": False, "message": f"存档不存在: {save_name}"}
        if not save_path.is_dir():
            return {"success": False, "message": f"不是有效的存档目录: {save_name}"}

        try:
            shutil.rmtree(str(save_path))
            logger.info("resource:removed", extra={"type": "save", "name": save_name, "path": str(save_path)})
            return {"success": True, "message": f"存档已删除: {save_name}"}
        except OSError as e:
            return {"success": False, "message": f"删除存档失败: {e}"}

    @staticmethod
    def open_saves_folder(game_path: str) -> dict[str, Any]:
        saves_dir = Path(game_path) / "saves"
        saves_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(saves_dir))
        return {"success": True, "path": str(saves_dir)}

    # ── 通用工具 ──

    @staticmethod
    def _list_dir_items(directory: Path) -> list[dict[str, Any]]:
        if not directory.is_dir():
            return []
        items = []
        for entry in sorted(directory.iterdir()):
            try:
                stat = entry.stat()
                items.append({
                    "filename": entry.name,
                    "size": stat.st_size if entry.is_file() else 0,
                    "is_folder": entry.is_dir(),
                })
            except OSError:
                continue
        return items

    @staticmethod
    def _remove_item(directory: Path, filename: str, item_type: str) -> dict[str, Any]:
        target = directory / filename
        if not target.exists():
            return {"success": False, "message": f"{item_type}不存在: {filename}"}
        try:
            if target.is_dir():
                shutil.rmtree(str(target))
            else:
                target.unlink()
            logger.info("resource:removed", extra={"type": item_type, "name": filename, "path": str(target)})
            return {"success": True, "message": f"{item_type}已删除: {filename}"}
        except OSError as e:
            return {"success": False, "message": f"删除{item_type}失败: {e}"}

    # ── NBT 解析 (level.dat) ──

    @staticmethod
    def _parse_level_dat(file_path: str) -> dict[str, Any]:
        result: dict[str, Any] = {"level_name": "", "game_type": "未知", "last_played": 0}

        try:
            with gzip.open(file_path, "rb") as f:
                data = f.read()
        except (gzip.BadGzipFile, OSError):
            return result

        try:
            offset = 0

            tag_type = data[offset]
            offset += 1
            if tag_type != 10:  # TAG_Compound
                return result

            offset = ResourceManager._nbt_skip_name(data, offset)

            data_offset = ResourceManager._nbt_find_data_compound(data, offset)
            if data_offset == -1:
                return result

            offset = data_offset
            while offset < len(data):
                if data[offset] == 0:  # TAG_End
                    break
                tag_type = data[offset]
                offset += 1
                name_len = struct.unpack(">H", data[offset:offset + 2])[0]
                offset += 2
                name = data[offset:offset + name_len].decode("utf-8", errors="replace")
                offset += name_len

                if tag_type == 8 and name == "LevelName":  # TAG_String
                    offset = ResourceManager._nbt_read_string(data, offset, result, "level_name")
                elif tag_type == 3 and name == "GameType":  # TAG_Int
                    if offset + 4 <= len(data):
                        game_type_val = struct.unpack(">i", data[offset:offset + 4])[0]
                        offset += 4
                        game_type_names = {0: "生存", 1: "创造", 2: "冒险", 3: "旁观"}
                        result["game_type"] = game_type_names.get(game_type_val, f"未知({game_type_val})")
                elif tag_type == 4 and name == "LastPlayed":  # TAG_Long
                    if offset + 8 <= len(data):
                        result["last_played"] = struct.unpack(">q", data[offset:offset + 8])[0]
                        offset += 8
                else:
                    offset = ResourceManager._nbt_skip_tag(data, offset, tag_type)

        except (struct.error, IndexError, UnicodeDecodeError):
            pass

        return result

    @staticmethod
    def _nbt_skip_name(data: bytes, offset: int) -> int:
        if offset + 2 > len(data):
            return offset
        name_len = struct.unpack(">H", data[offset:offset + 2])[0]
        offset += 2 + name_len
        return offset

    @staticmethod
    def _nbt_read_string(data: bytes, offset: int, result: dict[str, Any], key: str) -> int:
        if offset + 2 > len(data):
            return offset
        str_len = struct.unpack(">H", data[offset:offset + 2])[0]
        offset += 2
        if offset + str_len <= len(data):
            result[key] = data[offset:offset + str_len].decode("utf-8", errors="replace")
        offset += str_len
        return offset

    @staticmethod
    def _nbt_skip_tag(data: bytes, offset: int, tag_type: int) -> int:
        if tag_type == 1:  # TAG_Byte
            return offset + 1
        elif tag_type == 2:  # TAG_Short
            return offset + 2
        elif tag_type == 3:  # TAG_Int
            return offset + 4
        elif tag_type == 4:  # TAG_Long
            return offset + 8
        elif tag_type == 5:  # TAG_Float
            return offset + 4
        elif tag_type == 6:  # TAG_Double
            return offset + 8
        elif tag_type == 7:  # TAG_Byte_Array
            if offset + 4 > len(data):
                return offset
            length = struct.unpack(">i", data[offset:offset + 4])[0]
            offset += 4 + length
            return offset
        elif tag_type == 8:  # TAG_String
            if offset + 2 > len(data):
                return offset
            str_len = struct.unpack(">H", data[offset:offset + 2])[0]
            offset += 2 + str_len
            return offset
        elif tag_type == 9:  # TAG_List
            if offset + 5 > len(data):
                return offset
            list_tag_type = data[offset]
            offset += 1
            length = struct.unpack(">i", data[offset:offset + 4])[0]
            offset += 4
            for _ in range(length):
                offset = ResourceManager._nbt_skip_tag(data, offset, list_tag_type)
            return offset
        elif tag_type == 10:  # TAG_Compound
            while offset < len(data):
                if data[offset] == 0:  # TAG_End
                    return offset + 1
                inner_type = data[offset]
                offset += 1
                offset = ResourceManager._nbt_skip_name(data, offset)
                offset = ResourceManager._nbt_skip_tag(data, offset, inner_type)
            return offset
        elif tag_type == 11:  # TAG_Int_Array
            if offset + 4 > len(data):
                return offset
            length = struct.unpack(">i", data[offset:offset + 4])[0]
            offset += 4 + length * 4
            return offset
        elif tag_type == 12:  # TAG_Long_Array
            if offset + 4 > len(data):
                return offset
            length = struct.unpack(">i", data[offset:offset + 4])[0]
            offset += 4 + length * 8
            return offset
        return offset

    @staticmethod
    def _nbt_find_data_compound(data: bytes, offset: int) -> int:
        while offset < len(data):
            if data[offset] == 0:  # TAG_End
                break
            tag_type = data[offset]
            offset += 1
            name_len = struct.unpack(">H", data[offset:offset + 2])[0]
            offset += 2
            name = data[offset:offset + name_len].decode("utf-8", errors="replace")
            offset += name_len

            if name == "Data" and tag_type == 10:  # TAG_Compound
                return offset

            offset = ResourceManager._nbt_skip_tag(data, offset, tag_type)

        return -1