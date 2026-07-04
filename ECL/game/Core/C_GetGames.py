import json
from collections.abc import Callable
from pathlib import Path

import requests

from . import C_FilesChecker


class GetGames:
    def __init__(self, files_checker: C_FilesChecker.FilesChecker | None = None):
        self.files_checker = files_checker or C_FilesChecker.FilesChecker()
        self.output_log: Callable[[str], None] = print
        self._cached_versions: dict | None = None
        self._cached_fabric_versions: dict | None = None

    def set_output_log(self, output_function: Callable[[str], None]) -> None:
        self.output_log = output_function

    def set_api_url(self, api_url_dict: dict):
        self.files_checker.api_url.update_from_dict(api_url_dict)

    def get_minecraft_versions(self):  # 获取版本列表
        if self._cached_versions:
            return self._cached_versions
        try:
            get_versions = requests.get(
                f"{self.files_checker.api_url.Meta}/mc/game/version_manifest_v2.json", timeout=30
            ).json()
        except (requests.exceptions.RequestException, json.JSONDecodeError):
            return None
        snapshot = []
        release = []
        fool_days = []
        beta = []
        alpha = []
        for version_info in get_versions.get("versions", []):
            if version_info["type"] == "release":
                release.append(version_info)
            elif version_info["type"] == "snapshot":
                if "-04-01" in version_info.get("releaseTime", "") or version_info["id"] == "1.RV-Pre1":
                    fool_days.append(version_info)
                else:
                    snapshot.append(version_info)
            elif "beta" in version_info["type"]:
                beta.append(version_info)
            elif "alpha" in version_info["type"]:
                alpha.append(version_info)
        result = {
            "Latest": get_versions["latest"],  # 上一个版本{"release": "", "snapshot": ""}
            "All": get_versions["versions"],  # 所有版本
            "Snapshot": snapshot,  # 快照版
            "Release": release,  # 正式版
            "FoolDays": fool_days,  # 愚人节版
            "Beta": beta,  # Beta版
            "Alpha": alpha,  # Alpha版
        }
        self._cached_versions = result
        return result

    def download_minecraft(
        self,
        game_path: str | Path,
        version_id: str,
        download_file: bool = True,
        download_max_thread: int = 32,
        save_version_name: str | None = None,
        get_versions: dict | None = None,
    ) -> bool:
        game_path = Path(str(game_path))
        save_version_name = save_version_name if save_version_name else version_id
        save_json_path = game_path / "versions" / save_version_name / f"{save_version_name}.json"
        get_versions = get_versions if get_versions else self.get_minecraft_versions()
        if not get_versions:
            return False
        get_version_info = {}
        not_find = True
        for version_info in get_versions["All"]:
            if version_info["id"] == version_id:
                get_version_info = version_info
                try:
                    response = requests.get(
                        f"{self.files_checker.api_url.Meta}/v1/packages/{version_info['sha1']}/{version_id}.json",
                        timeout=30,
                    )
                    response.raise_for_status()
                    save_json_path.parent.mkdir(parents=True, exist_ok=True)
                    save_json_path.write_text(response.text, encoding="utf-8")
                    not_find = False
                    break
                except requests.exceptions.RequestException:
                    continue  # 尝试其他版本
        if not_find:
            return False
        (game_path / "versions" / "Manifest.json").write_text(
            json.dumps(get_versions, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        versions_info = {}
        versions_info_path = game_path / "versions" / "VersionsInfo.json"
        if versions_info_path.is_file():
            versions_info = json.loads(versions_info_path.read_text("utf-8"))
        versions_info.update(
            {version_id: {"Type": "Vanilla", "Version": version_id, "VanillaType": get_version_info["type"]}}
        )
        versions_info_path.write_text(json.dumps(versions_info, ensure_ascii=False, indent=4), encoding="utf-8")
        if download_file:
            self.files_checker.check_files(game_path, save_version_name, download_max_thread)
        return True

    def get_fabric_versions(self, game_version_id: str) -> dict[str, list[dict[str, str | bool]]] | None:
        """获取指定 Minecraft 版本对应的 Fabric 加载器版本列表（v2 API）。"""
        url = f"{self.files_checker.api_url.FabricMeta}/v2/versions/loader/{game_version_id}"
        print(f"[Fabric] 请求: {url}")
        try:
            response = requests.get(url, timeout=30)
            print(f"[Fabric] 状态码: {response.status_code}")
            if response.status_code == 404:
                print(f"[Fabric] 版本 {game_version_id} 不被 Fabric 支持")
                return None
            response.raise_for_status()
            get_versions = response.json()
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            print(f"[Fabric] 获取失败: {e}")
            return None
        print(f"[Fabric] 返回条目数: {len(get_versions)}")
        if len(get_versions) <= 0:
            print(f"[Fabric] 版本 {game_version_id} 无可用 Fabric 加载器")
            return None
        if len(get_versions) > 0:
            print(f"[Fabric] 首条样例: {json.dumps(get_versions[0], ensure_ascii=False)[:300]}")
        all_versions = []
        stable_versions = []
        not_stable_versions = []
        for version_info in get_versions:
            try:
                game_ver = (
                    version_info.get("intermediary", {}).get("version")
                    or version_info.get("mappings", {}).get("gameVersion")
                    or game_version_id
                )
                the_info = {
                    "GameVersion": game_ver,
                    "LoaderVersion": version_info["loader"]["version"],
                    "Stable": version_info["loader"]["stable"],
                }
                all_versions.append(the_info)
                if version_info["loader"]["stable"]:
                    stable_versions.append(the_info)
                else:
                    not_stable_versions.append(the_info)
            except (KeyError, TypeError) as e:
                print(f"[Fabric] 跳过格式异常条目: {e} | {json.dumps(version_info, ensure_ascii=False)[:200]}")
                continue
        print(f"[Fabric] 解析完成: All={len(all_versions)} Stable={len(stable_versions)} NotStable={len(not_stable_versions)}")
        return {"All": all_versions, "Stable": stable_versions, "NotStable": not_stable_versions}

    def download_fabric(
        self,
        game_path: str | Path,
        game_version_id: str,
        fabric_version: str,
        download_vanilla: bool = True,
        download_max_thread: int = 32,
        save_version_name: str | None = None,
    ):
        game_path = Path(str(game_path))
        save_version_name = (
            save_version_name if save_version_name else f"fabric-loader-{fabric_version}-{game_version_id}"
        )
        save_json_path = game_path / "versions" / save_version_name / f"{save_version_name}.json"
        try:
            response = requests.get(
                f"{self.files_checker.api_url.FabricMeta}/v2/versions/loader/{game_version_id}/{fabric_version}/profile/json",
                timeout=30,
            )
            response.raise_for_status()
            version_json = response.json()
            save_json_path.parent.mkdir(parents=True, exist_ok=True)
            save_json_path.write_text(response.text, encoding="utf-8")
        except requests.exceptions.RequestException:
            return False
        get_versions = self.get_minecraft_versions()
        if not get_versions:
            return False
        get_version_info = {}
        not_find = True
        for version_info in get_versions["All"]:
            if version_info["id"] == game_version_id:
                get_version_info = version_info
                not_find = False
        if not_find:
            return False
        versions_info = {}
        versions_info_path = game_path / "versions" / "VersionsInfo.json"
        if versions_info_path.is_file():
            versions_info = json.loads(versions_info_path.read_text("utf-8"))
        versions_info.update(
            {
                save_version_name: {
                    "Type": "Fabric",
                    "Version": fabric_version,
                    "VanillaType": get_version_info["type"],
                    "VanillaVersion": game_version_id,
                }
            }
        )
        versions_info_path.write_text(json.dumps(versions_info, ensure_ascii=False, indent=4), encoding="utf-8")
        if download_vanilla:
            self.download_minecraft(game_path, game_version_id, True, download_max_thread, None, get_versions)
        self.files_checker.check_files(game_path, save_version_name, download_max_thread)
        return True
