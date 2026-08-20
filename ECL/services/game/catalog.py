from typing import Any

import httpx

from .base import GameServiceError, _GameState

_FABRIC_API_PROJECT = "fabric-api"
_FABRIC_API_TIMEOUT_SECONDS = 10


class CatalogCoordinator(_GameState):
    @staticmethod
    def _catalog_item(item: dict[str, Any], version_type: str) -> dict[str, Any]:
        return {
            "id": str(item.get("id") or ""),
            "type": version_type,
            "releaseTime": str(item.get("releaseTime") or ""),
        }

    def minecraft_versions_classified(self, source: Any = "official") -> dict[str, list[dict[str, Any]]]:
        """
        查询并按正式版、快照和旧版本分类 Minecraft 版本。

        :param source: 下载源名称，如 ``official`` 或 ``bmclapi``
        """
        raw = self._query_context(source).games.get_minecraft_versions()
        groups = {
            "release": "Release",
            "snapshot": "Snapshot",
            "april_fools": "FoolDays",
            "old_beta": "Beta",
            "old_alpha": "Alpha",
        }
        catalog: dict[str, list[dict[str, Any]]] = {"all": []}
        type_by_id: dict[str, str] = {}
        for output_name, core_name in groups.items():
            values = [
                self._catalog_item(item, output_name)
                for item in raw.get(core_name, [])
                if isinstance(item, dict) and item.get("id")
            ]
            catalog[output_name] = values
            type_by_id.update({item["id"]: output_name for item in values})
        catalog["all"] = [
            self._catalog_item(item, type_by_id.get(str(item.get("id") or ""), "release"))
            for item in raw.get("All", [])
            if isinstance(item, dict) and item.get("id")
        ]
        return catalog

    def minecraft_versions(self, filter_type: Any = None, source: Any = "official") -> list[dict[str, Any]]:
        """
        查询 Minecraft 版本，可按版本类别过滤。

        :param filter_type: 版本目录筛选类型
        :param source: 下载源名称，如 ``official`` 或 ``bmclapi``
        """
        catalog = self.minecraft_versions_classified(source)
        key = str(filter_type or "all").strip().casefold().replace("-", "_")
        if key not in catalog:
            raise GameServiceError("未知的版本分类", "INVALID_VERSION_FILTER")
        return catalog[key]

    def loader_versions(self, loader_type: Any, game_version: Any, source: Any = "official") -> list[str]:
        """
        查询指定游戏版本兼容的加载器版本。

        :param loader_type: 模组加载器类型
        :param game_version: 目标 Minecraft 游戏版本
        :param source: 下载源名称，如 ``official`` 或 ``bmclapi``
        """
        loader = str(loader_type or "").strip().casefold()
        version = self._normalize_version_name(game_version, "Minecraft 版本")
        games = self._query_context(source).games
        if loader == "fabric":
            result = games.get_fabric_versions(version)
        elif loader == "forge":
            result = games.get_forge_versions(version)
        elif loader in {"neoforge", "neoforged"}:
            result = games.get_neoforged_versions(version)
        elif loader == "quilt":
            result = games.get_quilt_versions(version)
        else:
            raise GameServiceError(f"暂不支持加载器: {loader_type}", "UNSUPPORTED_LOADER")
        if isinstance(result, dict):
            values = result.get("All", result.get("all", []))
        else:
            values = result if isinstance(result, list) else []
        return [
            str(item.get("LoaderVersion") or "").strip()
            for item in values
            if isinstance(item, dict) and item.get("LoaderVersion")
        ]

    def fabric_api_versions(self, game_version: Any) -> list[str]:
        """
        查询指定 Minecraft 版本可用的 Fabric API 版本。

        :param game_version: 目标 Minecraft 游戏版本
        :return: Fabric API 版本号列表，按发布时间降序
        """
        version = self._normalize_version_name(game_version, "Minecraft 版本")
        params = {
            "game_versions": '["' + version + '"]',
            "loaders": '["fabric"]',
        }
        response = httpx.get(
            f"https://api.modrinth.com/v2/project/{_FABRIC_API_PROJECT}/version",
            params=params,
            headers={"User-Agent": "EuoraCraft-Launcher/version-install"},
            timeout=_FABRIC_API_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        versions = response.json()
        if not isinstance(versions, list):
            return []
        return [
            str(item.get("version_number") or "").strip()
            for item in versions
            if isinstance(item, dict) and item.get("version_number")
        ]
