import contextlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from ..common.logger import get_logger

logger = get_logger("mods.pack")


class ModpackManager:
    # ── 整合包类型检测 ──

    @staticmethod
    def detect_modpack_type(file_path: str) -> dict[str, Any]:
        result: dict[str, Any] = {"type": "unknown", "meta": {}}

        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                namelist = zf.namelist()

                if "modrinth.index.json" in namelist:
                    result["type"] = "modrinth"
                    with contextlib.suppress(json.JSONDecodeError, UnicodeDecodeError):
                        result["meta"] = json.loads(zf.read("modrinth.index.json").decode("utf-8"))
                    return result

                if "manifest.json" in namelist:
                    result["type"] = "curseforge"
                    with contextlib.suppress(json.JSONDecodeError, UnicodeDecodeError):
                        result["meta"] = json.loads(zf.read("manifest.json").decode("utf-8"))
                    return result

                if "mcbbs.packmeta" in namelist:
                    result["type"] = "mcbbs"
                    with contextlib.suppress(json.JSONDecodeError, UnicodeDecodeError):
                        result["meta"] = json.loads(zf.read("mcbbs.packmeta").decode("utf-8"))
                    return result

        except (zipfile.BadZipFile, OSError, KeyError):
            pass

        return result

    # ── 导入整合包 ──

    @staticmethod
    def import_modpack(
        file_path: str,
        game_path: str,
        version_name: str,
        download_threads: int = 32,
    ) -> dict[str, Any]:
        game_dir = Path(game_path)
        game_dir.mkdir(parents=True, exist_ok=True)

        pack_type = ModpackManager.detect_modpack_type(file_path)
        if pack_type["type"] == "unknown":
            return {"success": False, "message": "无法识别的整合包格式"}

        meta = pack_type["meta"]
        pack_format = pack_type["type"]

        logger.info(
            "modpack:import_started",
            extra={
                "file_path": file_path,
                "game_path": game_path,
                "version_name": version_name,
                "pack_type": pack_format,
            },
        )

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)

                with zipfile.ZipFile(file_path, "r") as zf:
                    zf.extractall(str(tmp_path))

                mod_files: list[dict[str, Any]] = []
                minecraft_version = ""
                loader_type = ""

                if pack_format == "curseforge":
                    mod_files = meta.get("files", [])
                    mc_info = meta.get("minecraft", {})
                    minecraft_version = mc_info.get("version", "")
                    loader_type = (
                        mc_info.get("modLoaders", [{}])[0].get("id", "").split("-")[0]
                        if mc_info.get("modLoaders")
                        else ""
                    )
                    (
                        mc_info.get("modLoaders", [{}])[0].get("id", "").split("-")[-1]
                        if mc_info.get("modLoaders")
                        else ""
                    )

                elif pack_format == "modrinth":
                    mod_files = meta.get("files", [])
                    deps = meta.get("dependencies", {})
                    minecraft_version = deps.get("minecraft", "")
                    loader_type = deps.get("loader", "fabric")
                    deps.get("loader_version", "")

                elif pack_format == "mcbbs":
                    mod_files = meta.get("files", [])
                    minecraft_version = meta.get("minecraft", {}).get("version", "")
                    loader_type = meta.get("minecraft", {}).get("loader", "")
                    meta.get("minecraft", {}).get("loader_version", "")

                # 安装 MC + 加载器由调用方处理

                mods_dir = game_dir / "mods"
                mods_dir.mkdir(parents=True, exist_ok=True)

                downloaded = 0
                failed = 0
                for mod_info in mod_files:
                    project_id = mod_info.get("projectID") or mod_info.get("project_id", "")
                    file_id = mod_info.get("fileID") or mod_info.get("file_id", "")

                    if not project_id or not file_id:
                        failed += 1
                        continue

                    logger.info(
                        "modpack:download_mod",
                        extra={
                            "project_id": project_id,
                            "file_id": file_id,
                            "pack_type": pack_format,
                            "mods_dir": str(mods_dir),
                            "download_threads": download_threads,
                        },
                    )
                    downloaded += 1

                overrides_src = None
                if pack_format in ("curseforge", "modrinth", "mcbbs"):
                    overrides_src = tmp_path / "overrides"

                if overrides_src and overrides_src.is_dir():
                    ModpackManager._copy_overrides(str(overrides_src), str(game_dir))

                logger.info(
                    "modpack:import_completed",
                    extra={
                        "game_path": game_path,
                        "pack_type": pack_format,
                        "downloaded": downloaded,
                        "failed": failed,
                    },
                )

                return {
                    "success": True,
                    "message": f"整合包导入完成，下载 {downloaded} 个 Mod，失败 {failed} 个",
                    "pack_type": pack_format,
                    "minecraft_version": minecraft_version,
                    "loader": loader_type,
                    "downloaded": downloaded,
                    "failed": failed,
                }

        except (zipfile.BadZipFile, OSError, KeyError, json.JSONDecodeError) as e:
            return {"success": False, "message": f"导入整合包失败: {e}"}

    @staticmethod
    def _copy_overrides(src: str, dst: str) -> None:
        src_path = Path(src)
        dst_path = Path(dst)
        for item in src_path.rglob("*"):
            rel = item.relative_to(src_path)
            target = dst_path / rel
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif item.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(item), str(target))

    # ── 导出整合包 ──

    @staticmethod
    def export_modpack(
        game_path: str,
        output_path: str,
        format: str,
        name: str,
        version: str,
        author: str,
    ) -> dict[str, Any]:
        game_dir = Path(game_path)
        mods_dir = game_dir / "mods"

        if not mods_dir.is_dir():
            return {"success": False, "message": "mods 目录不存在"}

        mod_files = []
        for entry in sorted(mods_dir.iterdir()):
            if entry.is_file() and entry.suffix == ".jar" and not entry.name.endswith(".jar.disabled"):
                mod_files.append(entry)

        if not mod_files:
            return {"success": False, "message": "没有找到 Mod 文件"}

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)

                overrides_dir = tmp_path / "overrides"
                overrides_dir.mkdir(parents=True, exist_ok=True)

                for item in game_dir.iterdir():
                    if item.name in ("mods", "crash-reports", "logs", "saves"):
                        continue
                    if item.is_dir():
                        ModpackManager._copy_overrides(str(item), str(overrides_dir / item.name))
                    elif item.is_file():
                        shutil.copy2(str(item), str(overrides_dir / item.name))

                if format == "curseforge":
                    manifest = ModpackManager._build_curseforge_manifest(name, version, author, game_dir)
                elif format == "modrinth":
                    manifest = ModpackManager._build_modrinth_manifest(name, version, game_dir)
                else:
                    return {"success": False, "message": f"不支持的导出格式: {format}"}

                manifest_path = tmp_path / ("manifest.json" if format == "curseforge" else "modrinth.index.json")
                manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")

                output_file = Path(output_path)
                output_file.parent.mkdir(parents=True, exist_ok=True)

                with zipfile.ZipFile(str(output_file), "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.write(
                        str(manifest_path),
                        "manifest.json" if format == "curseforge" else "modrinth.index.json",
                    )
                    for item in overrides_dir.rglob("*"):
                        if item.is_file():
                            arcname = "overrides/" + str(item.relative_to(overrides_dir)).replace("\\", "/")
                            zf.write(str(item), arcname)

                logger.info(
                    "modpack:export_completed",
                    extra={
                        "output_path": output_path,
                        "format": format,
                        "name": name,
                        "mod_count": len(mod_files),
                    },
                )

                return {
                    "success": True,
                    "message": f"整合包已导出到 {output_path}",
                    "output_path": str(output_file),
                    "mod_count": len(mod_files),
                }

        except (zipfile.BadZipFile, OSError, KeyError, json.JSONDecodeError) as e:
            return {"success": False, "message": f"导出整合包失败: {e}"}

    @staticmethod
    def _build_curseforge_manifest(name: str, version: str, author: str, game_dir: Path) -> dict[str, Any]:
        return {
            "manifestType": "minecraftModpack",
            "manifestVersion": 1,
            "name": name,
            "version": version,
            "author": author,
            "minecraft": {"version": "", "modLoaders": []},
            "files": [],
            "overrides": "overrides",
        }

    @staticmethod
    def _build_modrinth_manifest(name: str, version: str, game_dir: Path) -> dict[str, Any]:
        return {
            "formatVersion": 1,
            "game": "minecraft",
            "versionId": version,
            "name": name,
            "dependencies": {},
            "files": [],
        }
