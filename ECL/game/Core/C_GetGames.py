import json
from collections.abc import Callable
from pathlib import Path

import requests

from . import C_FilesChecker


class GetGames:
    def __init__(self, files_checker: C_FilesChecker.FilesChecker | None = None):
        self.files_checker = files_checker or C_FilesChecker.FilesChecker()
        self.output_log: Callable[[str], None] = print

    def set_output_log(self, output_function: Callable[[str], None]) -> None:
        self.output_log = output_function

    def set_api_url(self, api_url_dict: dict):
        self.files_checker.api_url.update_from_dict(api_url_dict)

    def get_minecraft_versions(self):  # 获取版本列表
        try:
            get_versions = requests.get(f"{self.files_checker.api_url.Meta}/mc/game/version_manifest_v2.json").json()
        except requests.exceptions.RequestException:
            return None
        snapshot = []
        release = []
        fool_days = []
        beta = []
        alpha = []
        for version_info in get_versions["versions"]:
            if version_info["type"] == "release":
                release.append(version_info)
            elif version_info["type"] == "snapshot":
                if "-04-01" in version_info["releaseTime"] or version_info["id"] == "1.RV-Pre1":
                    fool_days.append(version_info)
                else:
                    snapshot.append(version_info)
            elif "beta" in version_info["type"]:
                beta.append(version_info)
            elif "alpha" in version_info["type"]:
                alpha.append(version_info)
        return {
            "Latest": get_versions["latest"],  # 上一个版本{"release": "", "snapshot": ""}
            "All": get_versions["versions"],  # 所有版本
            "Snapshot": snapshot,  # 快照版
            "Release": release,  # 正式版
            "FoolDays": fool_days,  # 愚人节版
            "Beta": beta,  # Beta版
            "Alpha": alpha,  # Alpha版
        }

    def download_minecraft(
        self,
        game_path: str | Path,
        version_id: str,
        download_file: bool = True,
        download_max_thread: int = 32,
        save_version_name: str | None = None,
        get_versions: dict | None = None,
    ) -> bool:
        game_path = Path(game_path)
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
                        f"{self.files_checker.api_url.Meta}/v1/packages/{version_info['sha1']}/{version_id}.json"
                    )
                    response.raise_for_status()
                    save_json_path.parent.mkdir(parents=True, exist_ok=True)
                    save_json_path.write_text(response.text, encoding="utf-8")
                    not_find = False
                    break
                except requests.exceptions.RequestException:
                    return False
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
        get_versions = requests.get(
            f"{self.files_checker.api_url.FabricMeta}/v1/versions/loader/{game_version_id}"
        ).json()
        if len(get_versions) <= 0:
            return None
        all_versions = []
        stable_versions = []
        not_stable_versions = []
        for version_info in get_versions:
            the_info = {
                "GameVersion": version_info["mappings"]["gameVersion"],
                "LoaderVersion": version_info["loader"]["version"],
                "Stable": version_info["loader"]["stable"],
            }
            all_versions.append(the_info)
            if version_info["loader"]["stable"]:
                stable_versions.append(the_info)
            else:
                not_stable_versions.append(the_info)
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
        game_path = Path(game_path)
        save_version_name = (
            save_version_name if save_version_name else f"fabric-loader-{fabric_version}-{game_version_id}"
        )
        save_json_path = game_path / "versions" / save_version_name / f"{save_version_name}.json"
        try:
            response = requests.get(
                f"{self.files_checker.api_url.FabricMeta}/v2/versions/loader/{game_version_id}/{fabric_version}/profile/json"
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
                not_find = False
        if not_find:
            return False
        versions_info = {}
        versions_info_path = game_path / "versions" / "VersionsInfo.json"
        if versions_info_path.is_file():
            versions_info = json.loads(versions_info_path.read_text("utf-8"))
        versions_info.update(
            {
                version_json: {
                    "Type": "Fabric",
                    "Version": fabric_version,
                    "VanillaType": get_version_info["type"],
                    "VanillaVersion": game_version_id,
                }
            }
        )
        versions_info_path.write_text(json.dumps(versions_info, ensure_ascii=False, indent=4), encoding="utf-8")
        if download_vanilla:
            self.download_minecraft(game_path, game_version_id, False, download_max_thread, None, get_versions)
        self.files_checker.check_files(game_path, save_version_name, download_max_thread)
        return True
