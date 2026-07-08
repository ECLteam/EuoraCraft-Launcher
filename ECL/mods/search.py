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
    # ── 公开 API ──

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

        if source in ("both", "modrinth"):
            mr_data = OnlineModSearch._search_modrinth(query, loader, version, limit, offset)
            results.extend(mr_data["hits"])
            total += mr_data["total"]

        if source in ("both", "curseforge") and cf_api_key:
            cf_data = OnlineModSearch._search_curseforge(query, loader, version, limit, offset, cf_api_key)
            results.extend(cf_data["hits"])
            total += cf_data["total"]

        # 按 slug 去重，Modrinth 已在前面优先
        results = OnlineModSearch._slug_dedup(results)

        return {
            "hits": results,
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    @staticmethod
    def get_mod_info(project_id: str, source: str, cf_api_key: str = "") -> dict[str, Any]:
        # 获取 Mod 详细信息
        if source == "modrinth":
            return OnlineModSearch._get_modrinth_mod_info(project_id)
        elif source == "curseforge":
            if not cf_api_key:
                return {"error": "CurseForge API Key 未配置"}
            return OnlineModSearch._get_curseforge_mod_info(project_id, cf_api_key)
        else:
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
        if source == "modrinth":
            return OnlineModSearch._get_modrinth_versions(project_id, loader, game_version)
        elif source == "curseforge":
            if not cf_api_key:
                return []
            return OnlineModSearch._get_curseforge_versions(project_id, loader, game_version, cf_api_key)
        else:
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

        if source == "modrinth":
            return OnlineModSearch._download_modrinth(version_id, str(mods_dir), filename)
        elif source == "curseforge":
            if not cf_api_key:
                return {"success": False, "message": "CurseForge API Key 未配置"}
            return OnlineModSearch._download_curseforge(project_id, version_id, str(mods_dir), filename, cf_api_key)
        else:
            return {"success": False, "message": f"未知 source: {source}"}

    # ── Modrinth API ──

    @staticmethod
    def _search_modrinth(
        query: str,
        loader: str,
        version: str,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        # 搜索 Modrinth
        facets: list[list[str]] = [["project_type:mod"]]

        if loader and loader in VALID_LOADERS:
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

        headers = {"User-Agent": USER_AGENT}
        try:
            resp = requests.get(
                f"{MODRINTH_BASE}/search",
                params=params,
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            return {"hits": [], "total": 0}

        hits = []
        for item in data.get("hits", []):
            hits.append(
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

        return {
            "hits": hits,
            "total": data.get("total_hits", 0),
        }

    @staticmethod
    def _get_modrinth_mod_info(project_id: str) -> dict[str, Any]:
        # 获取 Modrinth 项目详情
        headers = {"User-Agent": USER_AGENT}
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
            "license": data.get("license", {}).get("name", "") if isinstance(data.get("license"), dict) else "",
            "updated": data.get("updated", ""),
            "approved": data.get("approved", ""),
            "published": data.get("published", ""),
            "client_side": data.get("client_side", ""),
            "server_side": data.get("server_side", ""),
            "status": data.get("status", ""),
        }

    @staticmethod
    def _get_modrinth_versions(
        project_id: str,
        loader: str,
        game_version: str,
    ) -> list[dict[str, Any]]:
        # 获取 Modrinth 版本列表
        params: dict[str, Any] = {}
        loaders_list = []
        if loader:
            loaders_list = [f'"{loader}"']
        if game_version:
            gv_list = [f'"{game_version}"']

        if loaders_list:
            params["loaders"] = f"[{','.join(loaders_list)}]"
        if game_version:
            params["game_versions"] = f"[{','.join(gv_list)}]"

        headers = {"User-Agent": USER_AGENT}
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

    # ── CurseForge API ──

    @staticmethod
    def _search_curseforge(
        query: str,
        loader: str,
        version: str,
        limit: int,
        offset: int,
        api_key: str,
    ) -> dict[str, Any]:
        # 搜索 CurseForge
        params: dict[str, Any] = {
            "gameId": 432,
            "classId": 6,
            "searchFilter": query,
            "pageSize": limit,
            "sortField": 2,
            "sortOrder": "desc",
            "index": offset,
        }

        if loader and loader in CF_LOADER_MAP:
            params["modLoaderType"] = CF_LOADER_MAP[loader]
        if version:
            params["gameVersion"] = version

        headers = {
            "User-Agent": USER_AGENT,
            "x-api-key": api_key,
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
            return {"hits": [], "total": 0}

        hits = []
        for item in data.get("data", []):
            # 作者名
            authors = item.get("authors", [])
            author_name = authors[0].get("name", "") if authors else ""

            # 分类
            categories = [c.get("name", "") for c in item.get("categories", [])]

            # 图标
            logo = item.get("logo", {})
            icon_url = logo.get("thumbnailUrl", "") if logo else ""

            hits.append(
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

        pagination = data.get("pagination", {})
        return {
            "hits": hits,
            "total": pagination.get("totalCount", 0),
        }

    @staticmethod
    def _get_curseforge_mod_info(project_id: str, api_key: str) -> dict[str, Any]:
        # 获取 CurseForge 项目详情
        headers = {
            "User-Agent": USER_AGENT,
            "x-api-key": api_key,
        }
        try:
            resp = requests.get(
                f"{CURSEFORGE_BASE}/mods/{project_id}",
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
        except (requests.RequestException, ValueError):
            return {"error": "获取 CurseForge 项目信息失败"}

        # 作者
        authors = data.get("authors", [])
        author_names = [a.get("name", "") for a in authors]

        # 分类
        categories = [c.get("name", "") for c in data.get("categories", [])]

        # 图标
        logo = data.get("logo", {})
        icon_url = logo.get("thumbnailUrl", "") if logo else ""

        # 链接
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

    @staticmethod
    def _get_curseforge_versions(
        project_id: str,
        loader: str,
        game_version: str,
        api_key: str,
    ) -> list[dict[str, Any]]:
        # 获取 CurseForge 文件列表
        params: dict[str, Any] = {
            "pageSize": 50,
            "index": 0,
        }

        if loader and loader in CF_LOADER_MAP:
            params["modLoaderType"] = CF_LOADER_MAP[loader]
        if game_version:
            params["gameVersion"] = game_version

        headers = {
            "User-Agent": USER_AGENT,
            "x-api-key": api_key,
        }
        try:
            resp = requests.get(
                f"{CURSEFORGE_BASE}/mods/{project_id}/files",
                params=params,
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
        except (requests.RequestException, ValueError):
            return []

        versions = []
        for item in data:
            # loader 映射回名称
            loader_type = item.get("modLoaderType", 0)
            loader_name = ""
            for k, v in CF_LOADER_MAP.items():
                if v == loader_type:
                    loader_name = k
                    break

            # 文件信息
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

            # 游戏版本
            game_versions = item.get("gameVersions", [])

            versions.append(
                {
                    "id": str(item.get("id", "")),
                    "name": item.get("displayName", ""),
                    "version_number": item.get("displayName", ""),
                    "loaders": [loader_name] if loader_name else [],
                    "game_versions": game_versions,
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

    # ── 下载实现 ──

    @staticmethod
    def _download_modrinth(
        version_id: str,
        mods_dir: str,
        filename: str = "",
    ) -> dict[str, Any]:
        # 从 Modrinth 下载 Mod
        # 先获取版本信息以拿到文件 URL
        versions = OnlineModSearch._get_modrinth_versions_from_id(version_id)
        if not versions or not versions[0].get("files"):
            return {"success": False, "message": "未找到版本文件"}

        file_info = versions[0]["files"][0]
        download_url = file_info.get("url", "")
        if not download_url:
            return {"success": False, "message": "下载 URL 为空"}

        if not filename:
            filename = file_info.get("filename", f"{version_id}.jar")

        dest_path = Path(mods_dir) / filename
        return OnlineModSearch._stream_download(download_url, str(dest_path), filename)

    @staticmethod
    def _download_curseforge(
        project_id: str,
        version_id: str,
        mods_dir: str,
        filename: str,
        api_key: str,
    ) -> dict[str, Any]:
        # 从 CurseForge 下载 Mod（先获取下载 URL）
        headers = {
            "User-Agent": USER_AGENT,
            "x-api-key": api_key,
        }

        # 获取文件信息
        try:
            resp = requests.get(
                f"{CURSEFORGE_BASE}/mods/{project_id}/files/{version_id}",
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            file_data = resp.json().get("data", {})
        except (requests.RequestException, ValueError):
            return {"success": False, "message": "获取 CurseForge 文件信息失败"}

        if not filename:
            filename = file_data.get("fileName", f"{version_id}.jar")

        # 获取实际下载 URL
        try:
            resp = requests.get(
                f"{CURSEFORGE_BASE}/mods/{project_id}/files/{version_id}/download-url",
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            download_url = resp.json().get("data", "")
        except (requests.RequestException, ValueError):
            # 回退：尝试直接使用文件信息中的 downloadUrl
            download_url = file_data.get("downloadUrl", "")

        if not download_url:
            return {"success": False, "message": "获取 CurseForge 下载 URL 失败"}

        dest_path = Path(mods_dir) / filename
        return OnlineModSearch._stream_download(download_url, str(dest_path), filename)

    @staticmethod
    def _stream_download(
        url: str,
        dest_path: str,
        filename: str,
    ) -> dict[str, Any]:
        # 流式下载文件，支持进度日志
        headers = {"User-Agent": USER_AGENT}
        try:
            resp = requests.get(url, headers=headers, stream=True, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.info(f"mod:download_failed {filename}: {e}")
            return {"success": False, "message": f"下载失败: {e}"}

        total_size = int(resp.headers.get("content-length", 0))
        downloaded = 0
        start_time = time.time()

        try:
            with dest_path.open("wb") as f:
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
                                    f"({downloaded}/{total_size}, {OnlineModSearch._calc_speed(downloaded, start_time)})"
                                )
        except (OSError, requests.RequestException) as e:
            # 清理未完成的文件
            with contextlib.suppress(OSError):
                Path(dest_path).unlink(missing_ok=True)
            logger.info(f"mod:download_failed {filename}: {e}")
            return {"success": False, "message": f"写入文件失败: {e}"}

        elapsed = time.time() - start_time
        logger.info(
            f"mod:downloaded {filename}: {downloaded} bytes in {elapsed:.2f}s "
            f"({OnlineModSearch._calc_speed(downloaded, start_time)})"
        )
        return {
            "success": True,
            "filename": filename,
            "path": dest_path,
            "size": downloaded,
            "elapsed": round(elapsed, 2),
        }

    # ── 工具方法 ──

    @staticmethod
    def _get_modrinth_versions_from_id(version_id: str) -> list[dict[str, Any]]:
        # 获取单个 Modrinth 版本（用于下载时获取文件 URL）
        headers = {"User-Agent": USER_AGENT}
        try:
            resp = requests.get(
                f"{MODRINTH_BASE}/version/{version_id}",
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            return []

        files = []
        for f in data.get("files", []):
            files.append(
                {
                    "url": f.get("url", ""),
                    "filename": f.get("filename", ""),
                    "size": f.get("size", 0),
                    "hashes": f.get("hashes", {}),
                }
            )

        return [
            {
                "id": data.get("id", ""),
                "name": data.get("name", ""),
                "version_number": data.get("version_number", ""),
                "loaders": data.get("loaders", []),
                "game_versions": data.get("game_versions", []),
                "downloads": data.get("downloads", 0),
                "date_published": data.get("date_published", ""),
                "files": files,
            }
        ]

    @staticmethod
    def _slug_dedup(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # 按 slug 去重，保留先出现的（Modrinth 优先）
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
        return deduped

    @staticmethod
    def _calc_speed(downloaded: int, start_time: float) -> str:
        # 计算下载速度，返回可读字符串
        elapsed = time.time() - start_time
        if elapsed <= 0:
            return "0 B/s"
        speed = downloaded / elapsed
        if speed >= 1024 * 1024:
            return f"{speed / (1024 * 1024):.1f} MB/s"
        elif speed >= 1024:
            return f"{speed / 1024:.1f} KB/s"
        else:
            return f"{speed:.0f} B/s"
