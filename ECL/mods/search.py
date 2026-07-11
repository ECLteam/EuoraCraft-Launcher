import contextlib
import json
import time
from pathlib import Path
from typing import Any

import requests

from ..common.logger import get_logger

logger = get_logger("mods.search")

# ── 常量 ──

USER_AGENT = "EuoraCraftLauncher/0.1.0 (contact@euoracraft.com)"

MODRINTH_BASE = "https://api.modrinth.com/v2"
CURSEFORGE_BASE = "https://api.curseforge.com/v1"

# CurseForge loader 名称 -> modLoaderType 整数映射
CF_LOADER_MAP = {
    "any": 0,
    "forge": 1,
    "fabric": 4,
    "quilt": 5,
    "neoforge": 6,
}

# 内置 loader 列表（用于 Modrinth facets）
VALID_LOADERS = ["fabric", "forge", "neoforge", "quilt", "liteloader"]


class OnlineModSearch:

    @staticmethod
    def search_mods(
        query: str,
        loader: str = "",
        version: str = "",
        limit: int = 20,
        offset: int = 0,
        source: str = "both",
        cf_api_key: str = "",
    ) -> dict[str, Any]:
        # 搜索 Mod，支持 Modrinth / CurseForge / 两者
        results: list[dict[str, Any]] = []
        total = 0

        # Modrinth 搜索
        if source in ("both", "modrinth"):
            facets: list[list[str]] = [["project_type:mod"]]
            if loader in VALID_LOADERS:
                facets.append([f"categories:{loader}"])
            if version:
                facets.append([f"versions:{version}"])

            params = {
                "query": query,
                "facets": json.dumps(facets),
                "limit": limit,
                "offset": offset,
                "index": "downloads",
            }

            try:
                resp = requests.get(
                    f"{MODRINTH_BASE}/search",
                    params=params,
                    headers={"User-Agent": USER_AGENT},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except (requests.RequestException, ValueError):
                data = {}

            for item in data.get("hits", []):
                results.append(
                    {
                        "project_id": item.get("project_id", ""),
                        "title": item.get("title", ""),
                        "author": item.get("author", ""),
                        "description": item.get("description", ""),
                        "downloads": item.get("downloads", 0),
                        "icon_url": item.get("icon_url", ""),
                        "categories": item.get("categories", []),
                        "source": "modrinth",
                        "slug": item.get("slug", ""),
                    }
                )
            total += data.get("total_hits", 0)

        # CurseForge 搜索
        if source in ("both", "curseforge") and cf_api_key:
            params: dict[str, Any] = {
                "gameId": 432,
                "classId": 6,
                "searchFilter": query,
                "pageSize": limit,
                "sortField": 2,
                "sortOrder": "desc",
                "index": offset,
            }
            if loader in CF_LOADER_MAP:
                params["modLoaderType"] = CF_LOADER_MAP[loader]
            if version:
                params["gameVersion"] = version

            headers = {
                "User-Agent": USER_AGENT,
                "x-api-key": cf_api_key,
            }
            try:
                resp = requests.get(
                    f"{CURSEFORGE_BASE}/mods/search",
                    params=params,
                    headers=headers,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except (requests.RequestException, ValueError):
                data = {}

            for item in data.get("data", []):
                authors = item.get("authors", [])
                author_name = authors[0].get("name", "") if authors else ""
                categories = [c.get("name", "") for c in item.get("categories", [])]
                logo = item.get("logo", {})
                icon_url = logo.get("thumbnailUrl", "") if logo else ""

                results.append(
                    {
                        "project_id": str(item.get("id", "")),
                        "title": item.get("name", ""),
                        "author": author_name,
                        "description": item.get("summary", ""),
                        "downloads": item.get("downloadCount", 0),
                        "icon_url": icon_url,
                        "categories": categories,
                        "source": "curseforge",
                        "slug": item.get("slug", ""),
                    }
                )

            total += data.get("pagination", {}).get("totalCount", 0)

        # 按 slug 去重，Modrinth 已在前面优先
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for item in results:
            slug = item.get("slug", "")
            if not slug:
                deduped.append(item)
                continue
            slug_lower = slug.lower()
            if slug_lower in seen:
                continue
            seen.add(slug_lower)
            deduped.append(item)

        return {
            "hits": deduped,
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    @staticmethod
    def get_mod_info(project_id: str, source: str, cf_api_key: str = "") -> dict[str, Any]:
        # 获取 Mod 详细信息
        headers = {"User-Agent": USER_AGENT}

        if source == "modrinth":
            try:
                resp = requests.get(
                    f"{MODRINTH_BASE}/project/{project_id}",
                    headers=headers,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except (requests.RequestException, ValueError):
                return {"error": "获取 Modrinth 项目信息失败"}

            license = data.get("license", {})
            return {
                "project_id": data.get("id", ""),
                "title": data.get("title", ""),
                "description": data.get("description", ""),
                "body": data.get("body", ""),
                "author": data.get("team", ""),
                "downloads": data.get("downloads", 0),
                "followers": data.get("followers", 0),
                "icon_url": data.get("icon_url", ""),
                "categories": data.get("categories", []),
                "source": "modrinth",
                "slug": data.get("slug", ""),
                "source_url": data.get("source_url", ""),
                "issues_url": data.get("issues_url", ""),
                "wiki_url": data.get("wiki_url", ""),
                "discord_url": data.get("discord_url", ""),
                "license": license.get("name", "") if isinstance(license, dict) else "",
                "updated": data.get("updated", ""),
                "approved": data.get("approved", ""),
                "published": data.get("published", ""),
                "client_side": data.get("client_side", ""),
                "server_side": data.get("server_side", ""),
                "status": data.get("status", ""),
            }

        if source == "curseforge":
            if not cf_api_key:
                return {"error": "CurseForge API Key 未配置"}

            try:
                resp = requests.get(
                    f"{CURSEFORGE_BASE}/mods/{project_id}",
                    headers={"User-Agent": USER_AGENT, "x-api-key": cf_api_key},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
            except (requests.RequestException, ValueError):
                return {"error": "获取 CurseForge 项目信息失败"}

            authors = data.get("authors", [])
            author_names = [a.get("name", "") for a in authors]
            categories = [c.get("name", "") for c in data.get("categories", [])]
            logo = data.get("logo", {})
            icon_url = logo.get("thumbnailUrl", "") if logo else ""
            links = data.get("links", {})

            return {
                "project_id": str(data.get("id", "")),
                "title": data.get("name", ""),
                "description": data.get("summary", ""),
                "body": data.get("description", ""),
                "author": ", ".join(author_names),
                "authors": author_names,
                "downloads": data.get("downloadCount", 0),
                "icon_url": icon_url,
                "categories": categories,
                "source": "curseforge",
                "slug": data.get("slug", ""),
                "source_url": links.get("websiteUrl", ""),
                "issues_url": links.get("issuesUrl", ""),
                "wiki_url": links.get("wikiUrl", ""),
                "updated": data.get("dateModified", ""),
                "released": data.get("dateReleased", ""),
                "created": data.get("dateCreated", ""),
                "status": data.get("status", 0),
                "allow_mod_distribution": data.get("allowModDistribution", True),
                "is_featured": data.get("isFeatured", False),
                "popularity_score": data.get("popularityScore", 0),
                "game_popularity_rank": data.get("gamePopularityRank", 0),
            }

        return {"error": f"未知 source: {source}"}

    @staticmethod
    def get_mod_versions(
        project_id: str,
        source: str,
        loader: str = "",
        game_version: str = "",
        cf_api_key: str = "",
    ) -> list[dict[str, Any]]:
        # 获取 Mod 版本列表
        headers = {"User-Agent": USER_AGENT}

        if source == "modrinth":
            params: dict[str, Any] = {}
            loaders_list = []
            if loader:
                loaders_list = [f'"{loader}"']
            gv_list = [f'"{game_version}"'] if game_version else []

            if loaders_list:
                params["loaders"] = f"[{','.join(loaders_list)}]"
            if game_version:
                params["game_versions"] = f"[{','.join(gv_list)}]"

            try:
                resp = requests.get(
                    f"{MODRINTH_BASE}/project/{project_id}/version",
                    params=params,
                    headers=headers,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except (requests.RequestException, ValueError):
                return []

            versions = []
            for item in data:
                files = []
                for f in item.get("files", []):
                    files.append(
                        {
                            "url": f.get("url", ""),
                            "filename": f.get("filename", ""),
                            "size": f.get("size", 0),
                            "hashes": f.get("hashes", {}),
                        }
                    )
                versions.append(
                    {
                        "id": item.get("id", ""),
                        "name": item.get("name", ""),
                        "version_number": item.get("version_number", ""),
                        "loaders": item.get("loaders", []),
                        "game_versions": item.get("game_versions", []),
                        "downloads": item.get("downloads", 0),
                        "date_published": item.get("date_published", ""),
                        "files": files,
                    }
                )
            return versions

        if source == "curseforge":
            if not cf_api_key:
                return []

            params: dict[str, Any] = {
                "pageSize": 50,
                "index": 0,
            }
            if loader in CF_LOADER_MAP:
                params["modLoaderType"] = CF_LOADER_MAP[loader]
            if game_version:
                params["gameVersion"] = game_version

            try:
                resp = requests.get(
                    f"{CURSEFORGE_BASE}/mods/{project_id}/files",
                    params=params,
                    headers={"User-Agent": USER_AGENT, "x-api-key": cf_api_key},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json().get("data", [])
            except (requests.RequestException, ValueError):
                return []

            versions = []
            for item in data:
                loader_type = item.get("modLoaderType", 0)
                loader_name = ""
                for k, v in CF_LOADER_MAP.items():
                    if v == loader_type:
                        loader_name = k
                        break

                files = [
                    {
                        "url": item.get("downloadUrl", ""),
                        "filename": item.get("fileName", ""),
                        "size": item.get("fileLength", 0),
                        "hashes": {
                            "sha1": item.get("hashes", [{}])[0].get("value", "") if item.get("hashes") else "",
                        },
                    }
                ]

                versions.append(
                    {
                        "id": str(item.get("id", "")),
                        "name": item.get("displayName", ""),
                        "version_number": item.get("displayName", ""),
                        "loaders": [loader_name] if loader_name else [],
                        "game_versions": item.get("gameVersions", []),
                        "downloads": item.get("downloadCount", 0),
                        "date_published": item.get("fileDate", ""),
                        "files": files,
                        "release_type": {
                            1: "release",
                            2: "beta",
                            3: "alpha",
                        }.get(item.get("releaseType", 1), "release"),
                    }
                )
            return versions

        return []

    @staticmethod
    def download_mod(
        project_id: str,
        version_id: str,
        source: str,
        game_path: str,
        filename: str = "",
        cf_api_key: str = "",
    ) -> dict[str, Any]:
        # 下载 Mod 到 {game_path}/mods/
        mods_dir = Path(game_path) / "mods"
        mods_dir.mkdir(parents=True, exist_ok=True)

        headers = {"User-Agent": USER_AGENT}

        if source == "modrinth":
            try:
                resp = requests.get(
                    f"{MODRINTH_BASE}/version/{version_id}",
                    headers=headers,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except (requests.RequestException, ValueError):
                return {"success": False, "message": "未找到版本文件"}

            files = [
                {
                    "url": f.get("url", ""),
                    "filename": f.get("filename", ""),
                    "size": f.get("size", 0),
                    "hashes": f.get("hashes", {}),
                }
                for f in data.get("files", [])
            ]
            if not files:
                return {"success": False, "message": "未找到版本文件"}

            file_info = files[0]
            download_url = file_info.get("url", "")
            if not download_url:
                return {"success": False, "message": "下载 URL 为空"}

            if not filename:
                filename = file_info.get("filename", f"{version_id}.jar")

            dest_path = mods_dir / filename
            return OnlineModSearch._stream_download(download_url, str(dest_path), filename)

        if source == "curseforge":
            if not cf_api_key:
                return {"success": False, "message": "CurseForge API Key 未配置"}

            cf_headers = {"User-Agent": USER_AGENT, "x-api-key": cf_api_key}

            try:
                resp = requests.get(
                    f"{CURSEFORGE_BASE}/mods/{project_id}/files/{version_id}",
                    headers=cf_headers,
                    timeout=30,
                )
                resp.raise_for_status()
                file_data = resp.json().get("data", {})
            except (requests.RequestException, ValueError):
                return {"success": False, "message": "获取 CurseForge 文件信息失败"}

            if not filename:
                filename = file_data.get("fileName", f"{version_id}.jar")

            try:
                resp = requests.get(
                    f"{CURSEFORGE_BASE}/mods/{project_id}/files/{version_id}/download-url",
                    headers=cf_headers,
                    timeout=30,
                )
                resp.raise_for_status()
                download_url = resp.json().get("data", "")
            except (requests.RequestException, ValueError):
                download_url = file_data.get("downloadUrl", "")

            if not download_url:
                return {"success": False, "message": "获取 CurseForge 下载 URL 失败"}

            dest_path = mods_dir / filename
            return OnlineModSearch._stream_download(download_url, str(dest_path), filename)

        return {"success": False, "message": f"未知 source: {source}"}

    @staticmethod
    def _stream_download(
        url: str,
        dest_path: str,
        filename: str,
    ) -> dict[str, Any]:
        # 流式下载文件，支持进度日志
        def _format_speed(downloaded: int, start_time: float) -> str:
            elapsed = time.time() - start_time
            if elapsed <= 0:
                return "0 B/s"
            speed = downloaded / elapsed
            if speed >= 1024 * 1024:
                return f"{speed / (1024 * 1024):.1f} MB/s"
            if speed >= 1024:
                return f"{speed / 1024:.1f} KB/s"
            return f"{speed:.0f} B/s"

        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, stream=True, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.info(f"mod:download_failed {filename}: {e}")
            return {"success": False, "message": f"下载失败: {e}"}

        total_size = int(resp.headers.get("content-length", 0))
        downloaded = 0
        start_time = time.time()

        try:
            with Path(dest_path).open("wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            progress = round(downloaded / total_size * 100, 1)
                            # 每 5% 或每 1MB 记录一次进度
                            if progress % 5 < 1 or downloaded % (1024 * 1024) < 8192:
                                logger.info(
                                    f"mod:download_progress {filename}: {progress}% "
                                    f"({downloaded}/{total_size}, {_format_speed(downloaded, start_time)})"
                                )
        except (OSError, requests.RequestException) as e:
            with contextlib.suppress(OSError):
                Path(dest_path).unlink(missing_ok=True)
            logger.info(f"mod:download_failed {filename}: {e}")
            return {"success": False, "message": f"写入文件失败: {e}"}

        elapsed = time.time() - start_time
        logger.info(
            f"mod:downloaded {filename}: {downloaded} bytes in {elapsed:.2f}s "
            f"({_format_speed(downloaded, start_time)})"
        )
        return {
            "success": True,
            "filename": filename,
            "path": dest_path,
            "size": downloaded,
            "elapsed": round(elapsed, 2),
        }
