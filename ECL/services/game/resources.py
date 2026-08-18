from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import time
import tomllib
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import nbtlib
from pydantic import BaseModel, ConfigDict, Field

from ECL.utils import atomic_write_text

from .base import GameServiceError
from .operations import OperationContext
from .workspace import move_to_trash, resolve_relative_id, safe_extract_zip

RESOURCE_DIRECTORIES = {
    "mod": "mods",
    "resourcepack": "resourcepacks",
    "shaderpack": "shaderpacks",
    "schematic": "schematics",
}

# 在线搜索的 resource_type -> Modrinth project_type 映射（存档无在线下载类型）
_RESOURCE_PROJECT_TYPE = {
    "mod": "mod",
    "resourcepack": "resourcepack",
    "shaderpack": "shader",
    "datapack": "datapack",
}


class _ModrinthSearchHit(BaseModel):
    """Modrinth 搜索命中 → 前端 ``ModSearchItem`` 的字段映射模型。"""

    model_config = ConfigDict(populate_by_name=True)

    id: Any = Field(default=None, validation_alias="project_id")
    project_id: Any = Field(default=None, validation_alias="project_id", serialization_alias="projectId")
    slug: Any = ""
    title: Any = None
    display_title: Any = Field(default=None, validation_alias="title", serialization_alias="displayTitle")
    description: Any = None
    author: Any = None
    icon_url: Any = Field(default=None, validation_alias="icon_url", serialization_alias="iconUrl")
    downloads: Any = None
    follows: Any = None
    date_modified: Any = Field(default=None, validation_alias="date_modified", serialization_alias="dateModified")
    source: str = ""
    project_url: str = Field(default="", serialization_alias="projectUrl")
    resource_type: str = Field(default="", serialization_alias="resourceType")
    categories: Any = Field(default_factory=list)
    loaders: Any = Field(default_factory=list)
    game_versions: Any = Field(
        default_factory=list, validation_alias="game_versions", serialization_alias="gameVersions"
    )
    alternatives: list[dict[str, Any]] = Field(default_factory=list)


class _ModrinthProjectInfo(BaseModel):
    """Modrinth 项目详情 → 前端 ``ModInfo`` 的字段映射模型。"""

    model_config = ConfigDict(populate_by_name=True)

    id: Any = Field(default=None)
    slug: Any = ""
    title: Any = None
    description: Any = None
    author: str = ""
    body: Any = None
    icon_url: Any = Field(default=None, validation_alias="icon_url", serialization_alias="iconUrl")
    source: str = "modrinth"
    resource_type: str = Field(default="", serialization_alias="resourceType")
    loaders: Any = Field(default_factory=list)
    game_versions: Any = Field(
        default_factory=list, validation_alias="game_versions", serialization_alias="gameVersions"
    )
    project_url: str = Field(default="", serialization_alias="projectUrl")


def _sha512(path: Path) -> str:
    digest = hashlib.sha512()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_json(data: bytes) -> dict[str, Any]:
    value = json.loads(data.decode("utf-8-sig"))
    return value if isinstance(value, dict) else {}


def _join_authors(authors: Any) -> str:
    """
    将 fabric/quilt 的 authors 结构（字符串或含 name 的对象）合并为逗号分隔文本。

    :param authors: 元数据中的作者列表
    :return: 逗号分隔的作者名
    """
    if not isinstance(authors, list):
        return ""
    names: list[str] = []
    for author in authors:
        if isinstance(author, str) and author:
            names.append(author)
        elif isinstance(author, dict) and author.get("name"):
            names.append(str(author["name"]))
    return ", ".join(names)


class ResourceCoordinator:
    """
    统一管理模组、资源包、光影包、数据包和原理图。
    """

    def _resource_root(
        self,
        game_path: Any,
        version_id: Any,
        resource_type: str,
        version_isolation: Any = False,
        world_id: str | None = None,
    ) -> Path:
        target = self.resolve_instance(game_path, version_id, version_isolation)
        if resource_type == "datapack":
            if not world_id:
                raise GameServiceError("数据包管理需要先选择世界", "WORLD_REQUIRED")
            world = resolve_relative_id(target.data_path / "saves", world_id)
            return world / "datapacks"
        directory = RESOURCE_DIRECTORIES.get(resource_type)
        if directory is None:
            raise GameServiceError("未知资源类型", "INVALID_RESOURCE_TYPE")
        return target.data_path / directory

    def _resource_manifest_path(self, game_path: Any, version_id: Any) -> Path:
        return self.resolve_instance(game_path, version_id).instance_path / ".ecl" / "resources.json"

    def _read_resource_manifest(self, game_path: Any, version_id: Any) -> dict[str, Any]:
        path = self._resource_manifest_path(game_path, version_id)
        if not path.is_file():
            return {"schemaVersion": 1, "resources": {}}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {"schemaVersion": 1, "resources": {}}
        except (OSError, UnicodeDecodeError, ValueError):
            return {"schemaVersion": 1, "resources": {}}

    def _write_resource_manifest(self, game_path: Any, version_id: Any, manifest: dict[str, Any]) -> None:
        path = self._resource_manifest_path(game_path, version_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, json.dumps(manifest, ensure_ascii=False, indent=2))

    @staticmethod
    def _parse_mod(path: Path) -> dict[str, Any]:
        result: dict[str, Any] = {"name": path.stem.removesuffix(".disabled"), "dependencies": []}
        if not zipfile.is_zipfile(path):
            return result
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                if "fabric.mod.json" in names:
                    data = _safe_json(archive.read("fabric.mod.json"))
                    depends = data.get("depends") or {}
                    result.update({
                        "loader": "fabric",
                        "projectId": data.get("id"),
                        "name": data.get("name") or data.get("id") or result["name"],
                        "version": data.get("version"),
                        "author": _join_authors(data.get("authors")),
                        "gameVersion": str(depends.get("minecraft")) if depends.get("minecraft") else None,
                        "dependencies": list(depends.keys()),
                    })
                elif "quilt.mod.json" in names:
                    data = _safe_json(archive.read("quilt.mod.json"))
                    quilt = data.get("quilt_loader") or {}
                    metadata = quilt.get("metadata") or {}
                    contributors = metadata.get("contributors") or {}
                    depends = quilt.get("depends") or []
                    minecraft = next(
                        (item.get("versions") for item in depends if isinstance(item, dict) and item.get("id") == "minecraft"),
                        None,
                    )
                    result.update({
                        "loader": "quilt",
                        "projectId": quilt.get("id"),
                        "name": metadata.get("name") or quilt.get("id") or result["name"],
                        "version": quilt.get("version"),
                        "author": ", ".join(contributors.keys()) if isinstance(contributors, dict) else "",
                        "gameVersion": str(minecraft) if minecraft else None,
                        "dependencies": [item.get("id") for item in depends if isinstance(item, dict)],
                    })
                else:
                    toml_name = "META-INF/neoforge.mods.toml" if "META-INF/neoforge.mods.toml" in names else "META-INF/mods.toml"
                    if toml_name in names:
                        data = tomllib.loads(archive.read(toml_name).decode("utf-8-sig"))
                        mods = data.get("mods") or []
                        first = mods[0] if mods and isinstance(mods[0], dict) else {}
                        mod_id = str(first.get("modId") or "")
                        dependencies: list[str] = []
                        minecraft_range: str | None = None
                        dep_map = data.get("dependencies") or {}
                        for dep in dep_map.get(mod_id) or []:
                            if not isinstance(dep, dict) or not dep.get("modId"):
                                continue
                            if dep.get("modId") == "minecraft":
                                minecraft_range = str(dep.get("versionRange") or "")
                            elif dep.get("mandatory"):
                                dependencies.append(str(dep["modId"]))
                        result.update({
                            "loader": "neoforge" if "neoforge" in toml_name else "forge",
                            "projectId": mod_id or None,
                            "name": first.get("displayName") or mod_id or result["name"],
                            "version": first.get("version"),
                            "author": str(first.get("authors") or ""),
                            "gameVersion": minecraft_range,
                            "dependencies": dependencies,
                        })
        except (OSError, ValueError, KeyError, zipfile.BadZipFile):
            pass
        return result

    @staticmethod
    def _parse_pack(path: Path) -> dict[str, Any]:
        result: dict[str, Any] = {"name": path.stem.removesuffix(".disabled")}
        try:
            if path.is_dir():
                data = json.loads((path / "pack.mcmeta").read_text(encoding="utf-8"))
            else:
                with zipfile.ZipFile(path) as archive:
                    data = _safe_json(archive.read("pack.mcmeta"))
            pack = data.get("pack") or {}
            result.update({"name": pack.get("description") or result["name"], "packFormat": pack.get("pack_format")})
        except (OSError, ValueError, KeyError, zipfile.BadZipFile):
            pass
        return result

    def list_resources(
        self,
        game_path: Any,
        version_id: Any,
        resource_type: str,
        version_isolation: Any = False,
        world_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        扫描资源文件、解析元数据，并标记重复哈希、重复模组 ID 与缺失依赖。
        """
        root = self._resource_root(game_path, version_id, resource_type, version_isolation, world_id)
        if not root.is_dir():
            return []
        manifest = self._read_resource_manifest(game_path, version_id).get("resources") or {}
        resources: list[dict[str, Any]] = []
        for path in root.iterdir():
            if path.name.startswith(".") or not (path.is_file() or (resource_type in {"resourcepack", "datapack"} and path.is_dir())):
                continue
            if resource_type == "mod" and path.suffix.casefold() not in {".jar", ".disabled"}:
                continue
            metadata = self._parse_mod(path) if resource_type == "mod" else self._parse_pack(path) if resource_type in {"resourcepack", "datapack"} else {"name": path.stem}
            digest = _sha512(path) if path.is_file() else None
            recorded = manifest.get(f"{resource_type}:{path.name}") or {}
            resources.append({
                "id": path.name,
                "type": resource_type,
                "path": str(path),
                "enabled": not path.name.endswith(".disabled"),
                "size": path.stat().st_size if path.is_file() else 0,
                "modifiedAt": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
                "sha512": digest,
                "source": recorded.get("source") or "local",
                "sourceProjectId": recorded.get("projectId"),
                "sourceVersionId": recorded.get("versionId"),
                **metadata,
            })
        hashes: dict[str, int] = {}
        ids: dict[str, int] = {}
        for item in resources:
            if item.get("sha512"):
                hashes[item["sha512"]] = hashes.get(item["sha512"], 0) + 1
            if resource_type == "mod" and item.get("projectId"):
                key = str(item["projectId"]).casefold()
                ids[key] = ids.get(key, 0) + 1
        installed_ids = set(ids)
        ignored_dependencies = {"minecraft", "java", "fabricloader", "forge", "neoforge", "quilt_loader"}
        for item in resources:
            item["duplicateHash"] = bool(item.get("sha512") and hashes.get(item["sha512"], 0) > 1)
            key = str(item.get("projectId") or "").casefold()
            item["duplicateProjectId"] = bool(key and ids.get(key, 0) > 1)
            item["missingDependencies"] = [
                dependency for dependency in item.get("dependencies") or []
                if str(dependency).casefold() not in installed_ids | ignored_dependencies
            ]
        return sorted(resources, key=lambda item: str(item.get("name") or item["id"]).casefold())

    def install_resources(
        self,
        game_path: Any,
        version_id: Any,
        resource_type: str,
        source_paths: list[Any],
        version_isolation: Any = False,
        world_id: str | None = None,
    ) -> dict[str, str]:
        """
        异步复制一个或多个本地资源，目标文件通过临时文件原子提交。
        """
        root = self._resource_root(game_path, version_id, resource_type, version_isolation, world_id)
        sources = [Path(str(value)).expanduser().resolve(strict=True) for value in source_paths]
        if not sources:
            raise GameServiceError("未选择资源文件", "RESOURCE_FILES_REQUIRED")

        def worker(context: OperationContext) -> dict[str, Any]:
            root.mkdir(parents=True, exist_ok=True)
            installed: list[str] = []
            for index, source in enumerate(sources, 1):
                context.check_cancelled()
                destination = resolve_relative_id(root, source.name, must_exist=False)
                if destination.exists():
                    raise GameServiceError(f"资源已存在：{source.name}", "RESOURCE_ALREADY_EXISTS")
                temp = destination.with_name(f".{destination.name}.ecl-tmp")
                try:
                    if source.is_dir():
                        shutil.copytree(source, temp)
                    else:
                        shutil.copy2(source, temp)
                    temp.replace(destination)
                finally:
                    if temp.is_dir():
                        shutil.rmtree(temp, ignore_errors=True)
                    else:
                        temp.unlink(missing_ok=True)
                installed.append(destination.name)
                context.progress(index * 100 / len(sources), "正在安装资源")
            return {"installed": installed}

        return self._game_operations.submit("resource_install", worker)

    @staticmethod
    def _patch_options_list(path: Path, key: str, filename: str, enabled: bool) -> None:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.is_file() else []
        prefix = f"{key}:"
        encoded = f'"file/{filename}"'
        found = False
        for index, line in enumerate(lines):
            if not line.startswith(prefix):
                continue
            found = True
            value = line[len(prefix):]
            entries = re.findall(r'"(?:\\.|[^"\\])*"', value)
            entries = [entry for entry in entries if entry != encoded]
            if enabled:
                entries.append(encoded)
            lines[index] = f"{prefix}[{','.join(entries)}]"
        if not found:
            lines.append(f"{prefix}[{encoded}]" if enabled else f"{prefix}[]")
        atomic_write_text(path, "\n".join(lines) + "\n")

    def toggle_resource(
        self,
        game_path: Any,
        version_id: Any,
        resource_type: str,
        resource_id: Any,
        enabled: bool,
        version_isolation: Any = False,
        world_id: str | None = None,
    ) -> dict[str, Any]:
        """
        按资源语义启停；原理图明确不提供无意义开关。
        """
        target = self.resolve_instance(game_path, version_id, version_isolation)
        root = self._resource_root(game_path, version_id, resource_type, version_isolation, world_id)
        path = resolve_relative_id(root, resource_id)
        if resource_type == "schematic":
            raise GameServiceError("原理图不支持启用或禁用", "RESOURCE_TOGGLE_UNSUPPORTED")
        if resource_type == "mod":
            if enabled and path.name.endswith(".disabled"):
                destination = path.with_name(path.name.removesuffix(".disabled"))
                path.rename(destination)
            elif not enabled and not path.name.endswith(".disabled"):
                destination = path.with_name(f"{path.name}.disabled")
                path.rename(destination)
        elif resource_type == "resourcepack":
            self._patch_options_list(target.data_path / "options.txt", "resourcePacks", path.name, enabled)
        elif resource_type == "shaderpack":
            options = target.data_path / "optionsshaders.txt"
            lines = options.read_text(encoding="utf-8", errors="replace").splitlines() if options.is_file() else []
            lines = [line for line in lines if not line.startswith("shaderPack=")]
            lines.append(f"shaderPack={path.name if enabled else 'OFF'}")
            atomic_write_text(options, "\n".join(lines) + "\n")
        elif resource_type == "datapack":
            world = resolve_relative_id(target.data_path / "saves", world_id)
            level_path = world / "level.dat"
            document = nbtlib.load(level_path)
            data = document.get("Data", document)
            packs = data.setdefault("DataPacks", nbtlib.Compound())
            name = f"file/{path.name}"
            enabled_values = [str(value) for value in packs.get("Enabled", []) if str(value) != name]
            disabled_values = [str(value) for value in packs.get("Disabled", []) if str(value) != name]
            (enabled_values if enabled else disabled_values).append(name)
            packs["Enabled"] = nbtlib.List[nbtlib.String](enabled_values)
            packs["Disabled"] = nbtlib.List[nbtlib.String](disabled_values)
            temp = level_path.with_name(".level.dat.ecl-tmp")
            try:
                document.save(temp, gzipped=True)
                temp.replace(level_path)
            finally:
                temp.unlink(missing_ok=True)
        return {"id": path.name, "enabled": bool(enabled)}

    def delete_resources_to_trash(
        self,
        game_path: Any,
        version_id: Any,
        resource_type: str,
        resource_ids: list[str],
        version_isolation: Any = False,
        world_id: str | None = None,
    ) -> None:
        root = self._resource_root(game_path, version_id, resource_type, version_isolation, world_id)
        for resource_id in resource_ids:
            move_to_trash(resolve_relative_id(root, resource_id))

    def export_resource_manifest(
        self,
        game_path: Any,
        version_id: Any,
        resource_type: str,
        output_path: Any,
        output_format: str,
        version_isolation: Any = False,
        world_id: str | None = None,
    ) -> dict[str, str]:
        resources = self.list_resources(game_path, version_id, resource_type, version_isolation, world_id)
        output = Path(str(output_path)).expanduser().resolve(strict=False)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output_format == "json":
            content = json.dumps({"schemaVersion": 1, "type": resource_type, "resources": resources}, ensure_ascii=False, indent=2)
        elif output_format == "csv":
            stream = io.StringIO(newline="")
            fields = ["id", "name", "version", "enabled", "source", "sourceProjectId", "sha512"]
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(resources)
            content = stream.getvalue()
        else:
            raise GameServiceError("资源清单仅支持 JSON 或 CSV", "INVALID_MANIFEST_FORMAT")
        atomic_write_text(output, content)
        return {"path": str(output)}

    def search_online_resources(
        self,
        query: str,
        game_version: str,
        loader: str,
        source: str = "modrinth",
        curseforge_key: str | None = None,
        limit: int = 20,
        resource_type: str = "mod",
    ) -> dict[str, Any]:
        """
        搜索 Modrinth 或 CurseForge；无 Key 时只禁用 CurseForge。

        :param resource_type: 资源类型（mod/resourcepack/shaderpack/datapack），决定 Modrinth project_type 过滤
        """
        if source == "modrinth":
            project_type = _RESOURCE_PROJECT_TYPE.get(resource_type)
            if project_type is None:
                raise GameServiceError("未知在线资源类型", "INVALID_RESOURCE_TYPE")
            if resource_type == "mod":
                facets = json.dumps([[f"versions:{game_version}"], [f"categories:{loader.casefold()}"]])
            else:
                facets = json.dumps([[f"project_type:{project_type}"], [f"versions:{game_version}"]])
            response = httpx.get(
                "https://api.modrinth.com/v2/search",
                params={"query": query, "facets": facets, "limit": min(limit, 50)},
                headers={"User-Agent": "EuoraCraft-Launcher/resource-workspace"},
                timeout=10,
            )
            response.raise_for_status()
            return {"source": source, "items": response.json().get("hits", []), "resource_type": resource_type}
        if source == "curseforge":
            key = os.getenv("CURSEFORGE_API_KEY") or curseforge_key
            if not key:
                raise GameServiceError("尚未配置 CurseForge API Key", "CURSEFORGE_KEY_REQUIRED")
            response = httpx.get(
                "https://api.curseforge.com/v1/mods/search",
                params={"gameId": 432, "searchFilter": query, "gameVersion": game_version, "pageSize": min(limit, 50)},
                headers={"x-api-key": key},
                timeout=10,
            )
            response.raise_for_status()
            return {"source": source, "items": response.json().get("data", [])}
        raise GameServiceError("未知在线资源来源", "INVALID_RESOURCE_SOURCE")

    @staticmethod
    def map_search_hits(
        source: str,
        hits: list[dict[str, Any]],
        resource_type: str = "mod",
    ) -> list[dict[str, Any]]:
        """
        将 Modrinth 搜索命中结果映射为前端在线模组卡片所需的结构。

        :param source: 数据来源（modrinth）
        :param hits: Modrinth ``/search`` 返回的命中列表
        :param resource_type: 资源类型（mod/resourcepack/shaderpack/datapack），决定项目页 URL 路径
        :return: 前端 ``ModSearchItem`` 兼容的字典列表
        """
        project_type = _RESOURCE_PROJECT_TYPE.get(resource_type, "mod")
        result: list[dict[str, Any]] = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            slug = str(hit.get("slug") or "")
            project_url = f"https://modrinth.com/{project_type}/{slug}"
            dto = _ModrinthSearchHit.model_validate(hit)
            dto.slug = slug
            dto.source = source
            dto.project_url = project_url
            dto.resource_type = resource_type
            dto.alternatives = [{
                "source": source,
                "projectId": dto.project_id,
                "slug": slug,
                "projectUrl": project_url,
            }]
            result.append(dto.model_dump(by_alias=True))
        return result

    def fetch_project_info(
        self,
        source: str,
        project_id: str,
        resource_type: str = "mod",
    ) -> dict[str, Any]:
        """
        获取 Modrinth 项目详情，映射为前端 ``ModInfo`` 结构。

        :param source: 数据来源（仅支持 modrinth）
        :param project_id: Modrinth 项目 ID
        :param resource_type: 资源类型（mod/resourcepack/shaderpack/datapack），用于兜底项目页 URL
        :return: 项目详情字典
        """
        if source != "modrinth":
            raise GameServiceError("暂不支持该来源", "INVALID_RESOURCE_SOURCE")
        response = httpx.get(
            f"https://api.modrinth.com/v2/project/{project_id}",
            headers={"User-Agent": "EuoraCraft-Launcher/resource-workspace"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        slug = str(data.get("slug") or "")
        project_type = str(data.get("project_type") or _RESOURCE_PROJECT_TYPE.get(resource_type, "mod"))
        dto = _ModrinthProjectInfo.model_validate(data)
        dto.slug = slug
        dto.resource_type = resource_type
        dto.project_url = f"https://modrinth.com/{project_type}/{slug}"
        return dto.model_dump(by_alias=True)

    def fetch_project_versions(
        self,
        source: str,
        project_id: str,
        game_version: str = "",
        loader: str = "",
    ) -> list[dict[str, Any]]:
        """
        获取 Modrinth 项目版本列表，映射为前端 ``ModVersion`` 结构。

        :param source: 数据来源（仅支持 modrinth）
        :param project_id: Modrinth 项目 ID
        :param game_version: 兼容的 Minecraft 版本筛选
        :param loader: 兼容的加载器筛选
        :return: 版本字典列表
        """
        if source != "modrinth":
            raise GameServiceError("暂不支持该来源", "INVALID_RESOURCE_SOURCE")
        params: dict[str, Any] = {}
        if game_version:
            params["game_versions"] = json.dumps([game_version])
        if loader:
            params["loaders"] = json.dumps([loader.casefold()])
        response = httpx.get(
            f"https://api.modrinth.com/v2/project/{project_id}/version",
            params=params,
            headers={"User-Agent": "EuoraCraft-Launcher/resource-workspace"},
            timeout=10,
        )
        response.raise_for_status()
        versions = response.json()
        result: list[dict[str, Any]] = []
        for item in versions if isinstance(versions, list) else []:
            if not isinstance(item, dict):
                continue
            files = item.get("files") or []
            primary = next(
                (file for file in files if isinstance(file, dict) and file.get("primary")),
                files[0] if files else None,
            )
            result.append({
                "id": item.get("id"),
                "projectId": item.get("project_id"),
                "name": item.get("name"),
                "versionNumber": item.get("version_number"),
                "gameVersions": item.get("game_versions") or [],
                "loaders": item.get("loaders") or [],
                "filename": primary.get("filename") if isinstance(primary, dict) else "",
                "datePublished": item.get("date_published"),
                "downloads": item.get("downloads"),
                "releaseType": item.get("release_type"),
            })
        return result

    def _fetch_online_version(self, version_id_str: str) -> dict[str, Any]:
        """获取 Modrinth 版本详情并返回主下载文件，无可用文件时抛出错误。"""
        response = httpx.get(
            f"https://api.modrinth.com/v2/version/{version_id_str}",
            headers={"User-Agent": "EuoraCraft-Launcher/resource-workspace"},
            timeout=10,
        )
        response.raise_for_status()
        files = response.json().get("files") or []
        selected = next(
            (item for item in files if isinstance(item, dict) and item.get("primary")),
            files[0] if files else None,
        )
        if not isinstance(selected, dict) or not selected.get("url") or not selected.get("filename"):
            raise GameServiceError("该版本缺少可下载文件", "RESOURCE_UPDATE_FILE_MISSING")
        return selected

    def _download_online_file(self, url: str, temp: Path, filename: str, task_id: str | None) -> None:
        """流式下载在线资源到临时文件，并按需上报字节进度与实时速度。"""
        with httpx.stream("GET", url, timeout=30, follow_redirects=True) as stream:
            stream.raise_for_status()
            total = int(stream.headers.get("content-length") or 0)
            with temp.open("wb") as output:
                downloaded = 0
                started = time.monotonic()
                last_emit = started
                last_bytes = 0
                if task_id:
                    self._emit_install_progress(
                        task_id, "download", f"正在下载 {filename}",
                        done=0, total=total, progress_type="bytes", speed=0,
                    )
                for chunk in stream.iter_bytes(1024 * 1024):
                    output.write(chunk)
                    downloaded += len(chunk)
                    if not task_id:
                        continue
                    now = time.monotonic()
                    if now - last_emit < 0.25 and downloaded < total:
                        continue
                    speed = int((downloaded - last_bytes) / max(now - last_emit, 0.001))
                    self._emit_install_progress(
                        task_id, "download", f"正在下载 {filename}",
                        done=downloaded, total=total, progress_type="bytes", speed=speed,
                    )
                    last_emit = now
                    last_bytes = downloaded

    def _record_installed_resource(
        self,
        game_path: Any,
        version_id: Any,
        resource_type: str,
        destination: Path,
        source: str,
        project_id: str,
        version_id_str: str,
    ) -> None:
        """在资源清单中记录已安装的在线资源来源信息。"""
        manifest = self._read_resource_manifest(game_path, version_id)
        records = manifest.setdefault("resources", {})
        records[f"{resource_type}:{destination.name}"] = {
            "source": source,
            "projectId": project_id,
            "versionId": version_id_str,
            "sha512": _sha512(destination),
            "enabled": True,
        }
        self._write_resource_manifest(game_path, version_id, manifest)

    def install_online_resource(
        self,
        game_path: Any,
        version_id: Any,
        resource_type: str,
        source: str,
        project_id: str,
        version_id_str: str,
        version_isolation: Any = False,
        task_id: str | None = None,
        world_id: str | None = None,
    ) -> dict[str, Any]:
        """
        按版本 ID 下载在线资源到目标目录，并记录来源到清单。

        :param game_path: Minecraft 游戏根目录
        :param version_id: 目标实例 ID
        :param resource_type: 资源类型（mod/resourcepack/shaderpack/datapack）
        :param source: 数据来源（modrinth）
        :param project_id: Modrinth 项目 ID
        :param version_id_str: Modrinth 版本 ID
        :param version_isolation: 是否启用版本隔离
        :param task_id: 任务队列 ID，非空时上报字节进度与实时速度事件
        :param world_id: 目标存档 ID（仅数据包安装到指定世界，其他类型忽略）
        :return: 安装结果（文件名、来源、是否跳过）
        """
        if source != "modrinth":
            raise GameServiceError("暂不支持该来源", "INVALID_RESOURCE_SOURCE")
        root = self._resource_root(game_path, version_id, resource_type, version_isolation, world_id)
        root.mkdir(parents=True, exist_ok=True)
        selected = self._fetch_online_version(version_id_str)
        destination = resolve_relative_id(root, str(selected["filename"]), must_exist=False)
        if destination.exists():
            raise GameServiceError(f"模组已存在：{selected['filename']}", "RESOURCE_ALREADY_EXISTS")
        temp = root / f".{destination.name}.ecl-download"
        filename = str(selected["filename"])
        try:
            self._download_online_file(str(selected["url"]), temp, filename, task_id)
            hashes = selected.get("hashes") or {}
            if hashes.get("sha512") and _sha512(temp).casefold() != str(hashes["sha512"]).casefold():
                raise GameServiceError("下载文件哈希校验失败", "RESOURCE_HASH_MISMATCH")
            temp.replace(destination)
            self._record_installed_resource(
                game_path, version_id, resource_type, destination, source, project_id, version_id_str
            )
            if task_id:
                self._emit_install_progress(task_id, "done", f"{filename} 已安装完成", done=1, total=1)
            return {"filename": destination.name, "source": source, "skipped": False}
        except GameServiceError as exc:
            if task_id:
                self._emit_install_progress(
                    task_id, "error", str(exc), done=0, total=1, error_code=exc.error_code,
                )
            raise
        except Exception as exc:
            if task_id:
                self._emit_install_progress(
                    task_id, "error", f"下载 {filename} 失败: {exc}", done=0, total=1,
                    error_code="RESOURCE_DOWNLOAD_FAILED",
                )
            raise
        finally:
            temp.unlink(missing_ok=True)

    def identify_resource_hash(
        self, sha512: str, curseforge_key: str | None = None
    ) -> dict[str, Any]:
        """
        用完整文件哈希查询 Modrinth 和 CurseForge，歧义时不猜测来源。
        """
        if not re.fullmatch(r"[a-fA-F0-9]{128}", sha512):
            raise GameServiceError("资源 SHA-512 格式无效", "INVALID_RESOURCE_HASH")
        candidates: list[dict[str, Any]] = []
        try:
            response = httpx.post(
                "https://api.modrinth.com/v2/version_files",
                json={"hashes": [sha512], "algorithm": "sha512"},
                headers={"User-Agent": "EuoraCraft-Launcher/resource-workspace"},
                timeout=10,
            )
            response.raise_for_status()
            if version := response.json().get(sha512):
                candidates.append({"source": "modrinth", "projectId": version.get("project_id"), "versionId": version.get("id")})
        except httpx.HTTPError:
            pass
        key = os.getenv("CURSEFORGE_API_KEY") or curseforge_key
        if key:
            # CurseForge 指纹使用 MurmurHash2 而非 SHA-512，未能识别的本地文件在此保持为本地。
            pass
        if len(candidates) != 1:
            return {"matched": False, "ambiguous": len(candidates) > 1, "candidates": candidates}
        return {"matched": True, **candidates[0]}

    def check_resource_updates(
        self,
        game_path: Any,
        version_id: Any,
        resource_type: str,
        game_version: str,
        loader: str,
        version_isolation: Any = False,
        world_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        查询与当前游戏版本和加载器严格兼容的 Modrinth 更新候选。
        """
        resources = self.list_resources(game_path, version_id, resource_type, version_isolation, world_id)
        updates: list[dict[str, Any]] = []
        with httpx.Client(headers={"User-Agent": "EuoraCraft-Launcher/resource-workspace"}, timeout=10) as client:
            for item in resources:
                if item.get("source") != "modrinth" or not item.get("sourceProjectId"):
                    continue
                response = client.get(
                    f"https://api.modrinth.com/v2/project/{item['sourceProjectId']}/version",
                    params={"game_versions": json.dumps([game_version]), "loaders": json.dumps([loader.casefold()])},
                )
                response.raise_for_status()
                versions = response.json()
                if not versions:
                    continue
                latest = versions[0]
                if latest.get("id") == item.get("sourceVersionId"):
                    continue
                updates.append({
                    "resourceId": item["id"],
                    "source": "modrinth",
                    "projectId": item["sourceProjectId"],
                    "versionId": latest.get("id"),
                    "versionNumber": latest.get("version_number"),
                    "publishedAt": latest.get("date_published"),
                    "dependencies": latest.get("dependencies") or [],
                    "changelog": re.sub(r"<[^>]+>", "", str(latest.get("changelog") or ""))[:12000],
                    "files": latest.get("files") or [],
                })
        return updates

    def update_resource(
        self,
        game_path: Any,
        version_id: Any,
        resource_type: str,
        resource_id: Any,
        update: dict[str, Any],
        version_isolation: Any = False,
        world_id: str | None = None,
    ) -> dict[str, str]:
        """
        下载校验更新文件后原子替换，旧文件仅移入系统回收站。
        """
        root = self._resource_root(game_path, version_id, resource_type, version_isolation, world_id)
        old = resolve_relative_id(root, resource_id)
        files = update.get("files") if isinstance(update.get("files"), list) else []
        selected = next((item for item in files if isinstance(item, dict) and item.get("primary")), files[0] if files else None)
        if not isinstance(selected, dict) or not selected.get("url") or not selected.get("filename"):
            raise GameServiceError("更新版本缺少可下载文件", "RESOURCE_UPDATE_FILE_MISSING")

        def worker(context: OperationContext) -> dict[str, str]:
            destination = resolve_relative_id(root, str(selected["filename"]), must_exist=False)
            temp = root / f".{destination.name}.ecl-download"
            try:
                with httpx.stream("GET", str(selected["url"]), timeout=30, follow_redirects=True) as response:
                    response.raise_for_status()
                    with temp.open("wb") as stream:
                        for chunk in response.iter_bytes(1024 * 1024):
                            context.check_cancelled()
                            stream.write(chunk)
                hashes = selected.get("hashes") or {}
                if hashes.get("sha512") and _sha512(temp).casefold() != str(hashes["sha512"]).casefold():
                    raise GameServiceError("更新文件哈希校验失败", "RESOURCE_HASH_MISMATCH")
                if destination != old and destination.exists():
                    raise GameServiceError("更新目标文件已存在", "RESOURCE_ALREADY_EXISTS")
                move_to_trash(old)
                temp.replace(destination)
                manifest = self._read_resource_manifest(game_path, version_id)
                records = manifest.setdefault("resources", {})
                records.pop(f"{resource_type}:{old.name}", None)
                records[f"{resource_type}:{destination.name}"] = {
                    "source": update.get("source"),
                    "projectId": update.get("projectId"),
                    "versionId": update.get("versionId"),
                    "sha512": _sha512(destination),
                    "enabled": True,
                }
                self._write_resource_manifest(game_path, version_id, manifest)
                return {"resourceId": destination.name}
            finally:
                temp.unlink(missing_ok=True)

        return self._game_operations.submit("resource_update", worker)

    def export_instance_pack(
        self,
        game_path: Any,
        version_id: Any,
        output_path: Any,
        pack_format: str,
        includes: list[str] | None = None,
    ) -> dict[str, str]:
        """
        导出 ECL 完整包或标准包；标准包默认排除隐私目录。
        """
        target = self.resolve_instance(game_path, version_id)
        output = Path(str(output_path)).expanduser().resolve(strict=False)
        include_set = set(includes or [])
        private = {"saves", "screenshots", "logs", "crash-reports", "servers.dat"}
        if pack_format not in {"ecl", "modrinth", "curseforge"}:
            raise GameServiceError("不支持的整合包格式", "INVALID_PACK_FORMAT")

        def worker(context: OperationContext) -> dict[str, str]:
            output.parent.mkdir(parents=True, exist_ok=True)
            temp = output.with_name(f".{output.name}.ecl-tmp")
            checksums: dict[str, str] = {}
            try:
                with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as archive:
                    roots = [target.instance_path]
                    resource_manifest = self._read_resource_manifest(target.game_path, target.version_id)
                    known_standard_files = {
                        key.split(":", 1)[1]
                        for key, metadata in (resource_manifest.get("resources") or {}).items()
                        if isinstance(metadata, dict) and metadata.get("source") in {"modrinth", "curseforge"}
                    }
                    for root in roots:
                        files = [path for path in root.rglob("*") if path.is_file()]
                        for index, path in enumerate(files, 1):
                            relative = path.relative_to(root)
                            top = relative.parts[0]
                            if pack_format != "ecl" and top in private and top not in include_set:
                                continue
                            if (
                                pack_format != "ecl"
                                and top in {"mods", "resourcepacks", "shaderpacks"}
                                and path.name not in known_standard_files
                            ):
                                continue
                            context.check_cancelled()
                            archive_name = Path("overrides") / relative if pack_format != "ecl" else relative
                            archive.write(path, archive_name)
                            checksums[str(archive_name).replace("\\", "/")] = _sha512(path)
                            context.progress(index * 85 / max(1, len(files)), "正在导出整合包")
                    if pack_format == "modrinth":
                        archive.writestr("modrinth.index.json", json.dumps({"formatVersion": 1, "game": "minecraft", "versionId": 1, "name": target.version_id, "summary": "Exported by ECL", "files": [], "dependencies": {"minecraft": target.version_id}}))
                    elif pack_format == "curseforge":
                        archive.writestr("manifest.json", json.dumps({"minecraft": {"version": target.version_id}, "manifestType": "minecraftModpack", "manifestVersion": 1, "name": target.version_id, "version": "1.0.0", "author": "ECL", "files": [], "overrides": "overrides"}))
                    else:
                        archive.writestr("ecl-pack.json", json.dumps({"schemaVersion": 1, "versionId": target.version_id, "checksums": checksums}, ensure_ascii=False))
                temp.replace(output)
                return {"path": str(output), "format": pack_format}
            finally:
                temp.unlink(missing_ok=True)

        return self._game_operations.submit("instance_export", worker)

    def import_instance_pack(
        self, game_path: Any, source_path: Any, new_version_id: Any
    ) -> dict[str, str]:
        """
        安全导入 mrpack、CurseForge ZIP 或 ECL ZIP 的 overrides/实例内容。
        """
        target = self.resolve_instance(game_path, new_version_id)
        source = Path(str(source_path)).expanduser().resolve(strict=True)
        if target.instance_path.exists():
            raise GameServiceError("目标实例已存在", "INSTANCE_ALREADY_EXISTS")

        def worker(context: OperationContext) -> dict[str, str]:
            with tempfile.TemporaryDirectory(prefix="ecl-pack-import-", dir=target.instance_path.parent) as temp_dir:
                extracted = Path(temp_dir)
                safe_extract_zip(source, extracted)
                if (extracted / "modrinth.index.json").is_file() or (extracted / "manifest.json").is_file():
                    content = extracted / "overrides"
                    if (extracted / "modrinth.index.json").is_file():
                        pack_manifest = json.loads((extracted / "modrinth.index.json").read_text(encoding="utf-8"))
                        base_version = str((pack_manifest.get("dependencies") or {}).get("minecraft") or "")
                    else:
                        pack_manifest = json.loads((extracted / "manifest.json").read_text(encoding="utf-8"))
                        base_version = str((pack_manifest.get("minecraft") or {}).get("version") or "")
                    base_json = target.game_path / "versions" / base_version / f"{base_version}.json"
                    if not base_version or not base_json.is_file():
                        raise GameServiceError(
                            f"请先安装整合包所需的基础版本 {base_version or '未知'}",
                            "PACK_BASE_VERSION_MISSING",
                        )
                elif (extracted / "ecl-pack.json").is_file():
                    content = extracted
                    base_version = ""
                else:
                    raise GameServiceError("无法识别整合包格式", "INVALID_PACK_ARCHIVE")
                context.check_cancelled()
                destination_temp = target.instance_path.with_name(f".{target.version_id}.ecl-import")
                shutil.copytree(content, destination_temp, ignore=shutil.ignore_patterns("ecl-pack.json"))
                if base_version:
                    atomic_write_text(
                        destination_temp / f"{target.version_id}.json",
                        json.dumps({"id": target.version_id, "inheritsFrom": base_version}, ensure_ascii=False, indent=2),
                    )
                else:
                    manifests = list(destination_temp.glob("*.json"))
                    original = next((path for path in manifests if path.name != "ecl-pack.json"), None)
                    if original and original.name != f"{target.version_id}.json":
                        original.rename(destination_temp / f"{target.version_id}.json")
                destination_temp.replace(target.instance_path)
                return {"versionId": target.version_id, "path": str(target.instance_path)}

        return self._game_operations.submit("instance_import", worker)
