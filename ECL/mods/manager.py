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
    def _parse_jar_metadata(jar_path: str) -> dict[str, Any]:
        # 解析 jar 内元数据文件，返回合并后的信息
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
                                entry = modlist[0]
                                if isinstance(entry, dict):
                                    info["name"] = entry.get("name", "") or info["name"]
                                    info["version"] = str(entry.get("version", "")) or info["version"]
                                    info["author"] = entry.get("author", "") or info["author"]
                                    info["game_version"] = str(entry.get("mcversion", "")) or info["game_version"]
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
                            # 作者：从 authors 或 contact 中提取
                            authors = data.get("authors", [])
                            if isinstance(authors, list):
                                if authors and isinstance(authors[0], dict):
                                    info["author"] = authors[0].get("name", "") or info["author"]
                                elif authors:
                                    info["author"] = str(authors[0]) or info["author"]
                            # 游戏版本：从 depends.minecraft 中提取
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
                        mods = data.get("mods", [])
                        if isinstance(mods, list) and len(mods) > 0:
                            entry = mods[0]
                            if isinstance(entry, dict):
                                info["name"] = entry.get("displayName", "") or info["name"]
                                info["version"] = str(entry.get("version", "")) or info["version"]
                                info["author"] = entry.get("authors", "") or info["author"]
                        # 依赖信息
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
                        mods = data.get("mods", [])
                        if isinstance(mods, list) and len(mods) > 0:
                            entry = mods[0]
                            if isinstance(entry, dict):
                                info["name"] = entry.get("displayName", "") or info["name"]
                                info["version"] = str(entry.get("version", "")) or info["version"]
                                info["author"] = entry.get("authors", "") or info["author"]
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
            pass  # 非 zip 文件

        return info

    # ── 公共方法 ──

    @staticmethod
    def get_mods(game_path: str) -> list[dict[str, Any]]:
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
                # 读取原始文件名对应的 jar（如果存在）
                original_name = filename[:-9]  # 去掉 .disabled
                original_path = mods_dir / original_name
                jar_path = str(original_path) if original_path.exists() else str(entry)
            elif filename.endswith(".jar"):
                jar_path = str(entry)
            else:
                continue

            # 解析元数据
            try:
                meta = ModManager._parse_jar_metadata(jar_path)
            except Exception:
                meta = {"name": "", "version": "", "author": "", "loader_type": "未知", "game_version": ""}

            # 如果元数据缺失，使用文件名
            if not meta.get("name"):
                meta["name"] = filename.rsplit(".", 1)[0] if filename.endswith(".jar") else filename

            mods.append(
                {
                    "filename": filename,
                    "name": meta.get("name", ""),
                    "version": meta.get("version", ""),
                    "author": meta.get("author", ""),
                    "loader_type": meta.get("loader_type", "未知"),
                    "game_version": meta.get("game_version", ""),
                    "enabled": enabled,
                }
            )

        logger.info("mods scanned: %d mods found", len(mods))
        return mods

    @staticmethod
    def toggle_mod(game_path: str, filename: str) -> dict[str, Any]:
        mods_dir = Path(game_path) / "mods"
        disabled = filename.endswith(".jar.disabled")

        if disabled:
            # 启用：.jar.disabled -> .jar
            new_name = filename[:-9]  # 去掉 .disabled
            old_path = mods_dir / filename
            new_path = mods_dir / new_name
            if new_path.exists():
                return {"success": False, "message": f"目标文件已存在: {new_name}"}
            old_path.rename(new_path)
            logger.info("mod enabled: %s", filename)
            return {"success": True, "enabled": True}
        else:
            # 禁用：.jar -> .jar.disabled
            new_name = filename + ".disabled"
            old_path = mods_dir / filename
            new_path = mods_dir / new_name
            old_path.rename(new_path)
            logger.info("mod disabled: %s", filename)
            return {"success": True, "enabled": False}

    @staticmethod
    def add_mod(game_path: str, source_path: str) -> dict[str, Any]:
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
        mods_dir = Path(game_path) / "mods"
        target = mods_dir / filename

        # 如果传入的是不带 .disabled 的，尝试 .jar.disabled
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
        mods_dir = Path(game_path) / "mods"
        mods_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(mods_dir))
        logger.info("mods folder opened: %s", mods_dir)
        return {"success": True, "path": str(mods_dir)}
