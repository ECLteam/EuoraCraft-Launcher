import json
import os
import shutil
import tomllib
import zipfile
from pathlib import Path
from typing import Any

from ..common.logger import get_logger

logger = get_logger("mods.manager")


class ModManager:

    @staticmethod
    def get_mods(game_path: str) -> list[dict[str, Any]]:
        # 获取已安装 Mod 列表（含元数据解析与启用状态）
        mods_dir = Path(game_path) / "mods"
        if not mods_dir.is_dir():
            return []

        mods = []
        for entry in sorted(mods_dir.iterdir()):
            if not entry.is_file():
                continue

            filename = entry.name
            enabled = True

            # 检测 .jar.disabled
            if filename.endswith(".jar.disabled"):
                enabled = False
                original_name = filename[:-9]  # 去掉 .disabled
                original_path = mods_dir / original_name
                jar_path = str(original_path) if original_path.exists() else str(entry)
            elif filename.endswith(".jar"):
                jar_path = str(entry)
            else:
                continue

            # 解析 jar 内元数据
            info: dict[str, Any] = {
                "name": "",
                "version": "",
                "author": "",
                "loader_type": "未知",
                "game_version": "",
            }

            try:
                with zipfile.ZipFile(jar_path, "r") as zf:
                    namelist = zf.namelist()

                    # mcmod.info
                    mcmod_candidates = [n for n in namelist if n == "mcmod.info" or n.endswith("/mcmod.info")]
                    if mcmod_candidates:
                        try:
                            data = json.loads(zf.read(mcmod_candidates[0]).decode("utf-8"))
                            if isinstance(data, list) and len(data) > 0:
                                data = data[0]
                            if isinstance(data, dict):
                                modlist = data.get("modList") or data.get("modlist") or [data]
                                if isinstance(modlist, list) and len(modlist) > 0:
                                    mod_entry = modlist[0]
                                    if isinstance(mod_entry, dict):
                                        info["name"] = mod_entry.get("name", "") or info["name"]
                                        info["version"] = str(mod_entry.get("version", "")) or info["version"]
                                        info["author"] = mod_entry.get("author", "") or info["author"]
                                        info["game_version"] = str(mod_entry.get("mcversion", "")) or info["game_version"]
                        except (json.JSONDecodeError, UnicodeDecodeError, KeyError, IndexError):
                            pass

                    # fabric.mod.json
                    if "fabric.mod.json" in namelist:
                        try:
                            data = json.loads(zf.read("fabric.mod.json").decode("utf-8"))
                            if isinstance(data, dict):
                                info["name"] = data.get("name", "") or info["name"]
                                info["version"] = str(data.get("version", "")) or info["version"]
                                info["loader_type"] = "Fabric"
                                authors = data.get("authors", [])
                                if isinstance(authors, list):
                                    if authors and isinstance(authors[0], dict):
                                        info["author"] = authors[0].get("name", "") or info["author"]
                                    elif authors:
                                        info["author"] = str(authors[0]) or info["author"]
                                depends = data.get("depends", {})
                                if isinstance(depends, dict):
                                    mc_ver = depends.get("minecraft", "")
                                    info["game_version"] = str(mc_ver) if mc_ver else info["game_version"]
                        except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
                            pass

                    # quilt.mod.json
                    if "quilt.mod.json" in namelist:
                        try:
                            data = json.loads(zf.read("quilt.mod.json").decode("utf-8"))
                            if isinstance(data, dict):
                                qmc = data.get("quilt_loader", {}) or data.get("loader", {})
                                if isinstance(qmc, dict):
                                    meta = qmc.get("metadata", {})
                                    if isinstance(meta, dict):
                                        info["name"] = meta.get("name", "") or info["name"]
                                        info["version"] = str(meta.get("version", "")) or info["version"]
                                        contributors = meta.get("contributors", {})
                                        if isinstance(contributors, dict):
                                            for k in contributors:
                                                info["author"] = str(k) if not info["author"] else info["author"]
                                                break
                                    depends = qmc.get("depends", [])
                                    if isinstance(depends, list):
                                        for dep in depends:
                                            if isinstance(dep, dict) and dep.get("id") == "minecraft":
                                                versions = dep.get("versions", "")
                                                info["game_version"] = str(versions) if versions else info["game_version"]
                                                break
                                info["loader_type"] = "Quilt"
                        except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
                            pass

                    # META-INF/mods.toml (Forge)
                    if "META-INF/mods.toml" in namelist:
                        try:
                            raw = zf.read("META-INF/mods.toml").decode("utf-8")
                            data = tomllib.loads(raw)
                            mods_list = data.get("mods", [])
                            if isinstance(mods_list, list) and len(mods_list) > 0:
                                mod_entry = mods_list[0]
                                if isinstance(mod_entry, dict):
                                    info["name"] = mod_entry.get("displayName", "") or info["name"]
                                    info["version"] = str(mod_entry.get("version", "")) or info["version"]
                                    info["author"] = mod_entry.get("authors", "") or info["author"]
                            deps = data.get("dependencies", {})
                            if isinstance(deps, dict):
                                mc_dep = deps.get("minecraft", "")
                                if mc_dep:
                                    info["game_version"] = str(mc_dep) if isinstance(mc_dep, str) else info["game_version"]
                            info["loader_type"] = "Forge"
                        except (tomllib.TOMLDecodeError, UnicodeDecodeError, KeyError):
                            pass

                    # META-INF/neoforge.mods.toml
                    if "META-INF/neoforge.mods.toml" in namelist:
                        try:
                            raw = zf.read("META-INF/neoforge.mods.toml").decode("utf-8")
                            data = tomllib.loads(raw)
                            mods_list = data.get("mods", [])
                            if isinstance(mods_list, list) and len(mods_list) > 0:
                                mod_entry = mods_list[0]
                                if isinstance(mod_entry, dict):
                                    info["name"] = mod_entry.get("displayName", "") or info["name"]
                                    info["version"] = str(mod_entry.get("version", "")) or info["version"]
                                    info["author"] = mod_entry.get("authors", "") or info["author"]
                            info["loader_type"] = "NeoForge"
                        except (tomllib.TOMLDecodeError, UnicodeDecodeError, KeyError):
                            pass

                    # litemod.json (LiteLoader)
                    if "litemod.json" in namelist:
                        try:
                            data = json.loads(zf.read("litemod.json").decode("utf-8"))
                            if isinstance(data, dict):
                                info["name"] = data.get("name", "") or info["name"]
                                info["version"] = str(data.get("version", "")) or info["version"]
                                info["author"] = data.get("author", "") or info["author"]
                                info["game_version"] = str(data.get("mcversion", "")) or info["game_version"]
                                info["loader_type"] = "LiteLoader"
                        except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
                            pass

            except (zipfile.BadZipFile, OSError):
                pass  # 非 zip 文件或读取失败

            # 如果元数据缺失，使用文件名兜底
            if not info["name"]:
                info["name"] = filename.rsplit(".", 1)[0] if filename.endswith(".jar") else filename

            mods.append(
                {
                    "filename": filename,
                    "name": info["name"],
                    "version": info["version"],
                    "author": info["author"],
                    "loader_type": info["loader_type"],
                    "game_version": info["game_version"],
                    "enabled": enabled,
                }
            )

        logger.info("mods scanned: %d mods found", len(mods))
        return mods

    @staticmethod
    def toggle_mod(game_path: str, filename: str) -> dict[str, Any]:
        # 切换 Mod 启用/禁用状态
        mods_dir = Path(game_path) / "mods"
        disabled = filename.endswith(".jar.disabled")

        if disabled:
            new_name = filename[:-9]  # 去掉 .disabled
            old_path = mods_dir / filename
            new_path = mods_dir / new_name
            if new_path.exists():
                return {"success": False, "message": f"目标文件已存在: {new_name}"}
            old_path.rename(new_path)
            logger.info("mod enabled: %s", filename)
            return {"success": True, "enabled": True}

        new_name = filename + ".disabled"
        old_path = mods_dir / filename
        new_path = mods_dir / new_name
        old_path.rename(new_path)
        logger.info("mod disabled: %s", filename)
        return {"success": True, "enabled": False}

    @staticmethod
    def add_mod(game_path: str, source_path: str) -> dict[str, Any]:
        # 复制 Mod 到 mods 目录
        mods_dir = Path(game_path) / "mods"
        mods_dir.mkdir(parents=True, exist_ok=True)

        source = Path(source_path)
        if not source.is_file():
            return {"success": False, "message": "源文件不存在"}

        dest = mods_dir / source.name
        shutil.copy2(str(source), str(dest))

        logger.info("mod added: %s", source.name)
        return {"success": True, "filename": source.name}

    @staticmethod
    def remove_mod(game_path: str, filename: str) -> dict[str, Any]:
        # 删除指定 Mod 文件
        mods_dir = Path(game_path) / "mods"
        target = mods_dir / filename

        if not target.exists() and not filename.endswith(".disabled"):
            target = mods_dir / (filename + ".disabled")
        if not target.exists() and not filename.endswith(".jar") and not filename.endswith(".disabled"):
            target = mods_dir / (filename + ".jar")

        if not target.exists():
            return {"success": False, "message": f"文件不存在: {filename}"}

        target.unlink()
        logger.info("mod removed: %s", filename)
        return {"success": True, "filename": filename}

    @staticmethod
    def open_mods_folder(game_path: str) -> dict[str, Any]:
        # 打开 mods 文件夹
        mods_dir = Path(game_path) / "mods"
        mods_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(mods_dir))
        logger.info("mods folder opened: %s", mods_dir)
        return {"success": True, "path": str(mods_dir)}
