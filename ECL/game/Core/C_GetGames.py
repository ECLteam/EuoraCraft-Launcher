import json
import xml.etree.ElementTree as ET
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
        self._cached_forge_versions: dict | None = None
        self._cached_neoforge_versions: dict | None = None
        self._cached_optifine_versions: dict | None = None
        self._cached_quilt_versions: dict | None = None

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
        print(
            f"[MC] download_minecraft: game_path={game_path}, version_id={version_id}, "
            f"download_file={download_file}, download_max_thread={download_max_thread}, "
            f"save_version_name={save_version_name}"
        )
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
        print(
            f"[Fabric] 解析完成: All={len(all_versions)} Stable={len(stable_versions)} NotStable={len(not_stable_versions)}"
        )
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
            response.json()
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

    def get_forge_versions(self, game_version_id: str) -> dict | None:
        url = f"{self.files_checker.api_url.ForgeMeta}/forge/minecraft/{game_version_id}"
        print(f"[Forge] 请求: {url}")
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            get_versions = response.json()
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            print(f"[Forge] 获取失败: {e}")
            return None
        all_versions = []
        stable_versions = []
        not_stable_versions = []
        for version_info in get_versions:
            forge_ver = version_info.get("version", "")
            is_stable = version_info.get("branch") == "stable"
            the_info = {
                "GameVersion": game_version_id,
                "LoaderVersion": forge_ver,
                "Stable": is_stable,
            }
            all_versions.append(the_info)
            if is_stable:
                stable_versions.append(the_info)
            else:
                not_stable_versions.append(the_info)
        result = {"All": all_versions, "Stable": stable_versions, "NotStable": not_stable_versions}
        self._cached_forge_versions = result
        return result

    def download_forge(
        self,
        game_path,
        game_version_id,
        forge_version,
        save_version_name,
        download_max_thread=32,
    ):
        game_path = Path(str(game_path))
        print(
            f"[Forge] download: game_path={game_path}, game_version_id={game_version_id}, "
            f"forge_version={forge_version}, save_version_name={save_version_name}"
        )
        save_json_path = game_path / "versions" / save_version_name / f"{save_version_name}.json"
        try:
            response = requests.get(
                f"{self.files_checker.api_url.ForgeMeta}/forge/download/{forge_version}/json",
                timeout=30,
            )
            response.raise_for_status()
            response.json()
            save_json_path.parent.mkdir(parents=True, exist_ok=True)
            save_json_path.write_text(response.text, encoding="utf-8")
        except requests.exceptions.RequestException as e:
            print(f"[Forge] download json failed: {e}")
            return False
        self.download_minecraft(
            game_path,
            game_version_id,
            download_file=True,
            download_max_thread=download_max_thread,
            save_version_name=save_version_name,
        )
        self.files_checker.check_files(game_path, save_version_name, download_max_thread)
        versions_info = {}
        versions_info_path = game_path / "versions" / "VersionsInfo.json"
        if versions_info_path.is_file():
            versions_info = json.loads(versions_info_path.read_text("utf-8"))
        versions_info.update(
            {
                save_version_name: {
                    "Type": "Forge",
                    "Version": forge_version,
                    "LoaderVersion": forge_version,
                    "VanillaVersion": game_version_id,
                }
            }
        )
        versions_info_path.write_text(json.dumps(versions_info, ensure_ascii=False, indent=4), encoding="utf-8")
        return True

    def get_quilt_versions(self, game_version_id):
        if self._cached_quilt_versions:
            return self._cached_quilt_versions
        url = f"https://meta.quiltmc.org/v3/versions/loader/{game_version_id}"
        print(f"[Quilt] 请求: {url}")
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            get_versions = response.json()
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            print(f"[Quilt] 获取失败: {e}")
            return None
        all_versions = []
        stable_versions = []
        not_stable_versions = []
        for version_info in get_versions:
            try:
                loader = version_info["loader"]
                is_stable = version_info.get("stable", False)
                the_info = {
                    "GameVersion": game_version_id,
                    "LoaderVersion": loader["version"],
                    "Stable": is_stable,
                }
                all_versions.append(the_info)
                if is_stable:
                    stable_versions.append(the_info)
                else:
                    not_stable_versions.append(the_info)
            except (KeyError, TypeError) as e:
                print(f"[Quilt] 跳过格式异常条目: {e} | {json.dumps(version_info, ensure_ascii=False)[:200]}")
                continue
        print(
            f"[Quilt] 解析完成: All={len(all_versions)} Stable={len(stable_versions)} NotStable={len(not_stable_versions)}"
        )
        result = {"All": all_versions, "Stable": stable_versions, "NotStable": not_stable_versions}
        self._cached_quilt_versions = result
        return result

    def download_quilt(self, game_path, game_version_id, quilt_version, save_version_name, download_max_thread=32):
        game_path = Path(str(game_path))
        print(
            f"[Quilt] download: game_path={game_path}, game_version_id={game_version_id}, "
            f"quilt_version={quilt_version}, save_version_name={save_version_name}"
        )
        save_json_path = game_path / "versions" / save_version_name / f"{save_version_name}.json"
        try:
            response = requests.get(
                f"https://meta.quiltmc.org/v3/versions/loader/{game_version_id}/{quilt_version}/profile/json",
                timeout=30,
            )
            response.raise_for_status()
            save_json_path.parent.mkdir(parents=True, exist_ok=True)
            save_json_path.write_text(response.text, encoding="utf-8")
        except requests.exceptions.RequestException as e:
            print(f"[Quilt] download json failed: {e}")
            return False
        self.download_minecraft(
            game_path,
            game_version_id,
            download_file=True,
            download_max_thread=download_max_thread,
            save_version_name=save_version_name,
        )
        self.files_checker.check_files(game_path, save_version_name, download_max_thread)
        versions_info = {}
        versions_info_path = game_path / "versions" / "VersionsInfo.json"
        if versions_info_path.is_file():
            versions_info = json.loads(versions_info_path.read_text("utf-8"))
        versions_info.update(
            {
                save_version_name: {
                    "Type": "Quilt",
                    "Version": quilt_version,
                    "LoaderVersion": quilt_version,
                    "VanillaVersion": game_version_id,
                }
            }
        )
        versions_info_path.write_text(json.dumps(versions_info, ensure_ascii=False, indent=4), encoding="utf-8")
        return True

    def get_neoforge_versions(self, game_version_id: str) -> dict | None:
        url = f"{self.files_checker.api_url.NeoForged}/net/neoforged/neoforge/maven-metadata.xml"
        print(f"[NeoForge] 请求: {url}")
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            root = ET.fromstring(response.text)
        except (requests.exceptions.RequestException, ET.ParseError) as e:
            print(f"[NeoForge] 获取失败: {e}")
            return None
        all_versions = []
        stable_versions = []
        not_stable_versions = []
        for versioning in root.findall("versioning"):
            for versions_elem in versioning.findall("versions"):
                for version_elem in versions_elem.findall("version"):
                    ver = version_elem.text
                    if not ver or game_version_id not in ver:
                        continue
                    is_stable = "beta" not in ver.lower() and "alpha" not in ver.lower() and "rc" not in ver.lower()
                    the_info = {
                        "GameVersion": game_version_id,
                        "LoaderVersion": ver,
                        "Stable": is_stable,
                    }
                    all_versions.append(the_info)
                    if is_stable:
                        stable_versions.append(the_info)
                    else:
                        not_stable_versions.append(the_info)
        result = {"All": all_versions, "Stable": stable_versions, "NotStable": not_stable_versions}
        self._cached_neoforge_versions = result
        return result

    def download_neoforge(
        self,
        game_path,
        game_version_id,
        neoforge_version,
        save_version_name,
        download_max_thread=32,
    ):
        game_path = Path(str(game_path))
        print(
            f"[NeoForge] download: game_path={game_path}, game_version_id={game_version_id}, "
            f"neoforge_version={neoforge_version}, save_version_name={save_version_name}"
        )
        save_json_path = game_path / "versions" / save_version_name / f"{save_version_name}.json"
        save_json_path.parent.mkdir(parents=True, exist_ok=True)
        profile_json = {
            "id": save_version_name,
            "inheritsFrom": game_version_id,
            "releaseTime": "2024-01-01T00:00:00+00:00",
            "time": "2024-01-01T00:00:00+00:00",
            "type": "release",
            "mainClass": "net.neoforged.installer.Main",
            "arguments": {
                "game": [],
                "jvm": [
                    "-Djava.library.path=${natives_directory}",
                    "-cp",
                    "${classpath}",
                ],
            },
            "libraries": [
                {
                    "name": f"net.neoforged:neoforge:{neoforge_version}",
                    "url": f"{self.files_checker.api_url.NeoForged}/",
                    "downloads": {
                        "artifact": {
                            "path": f"net/neoforged/neoforge/{neoforge_version}/neoforge-{neoforge_version}-installer.jar",
                            "url": f"{self.files_checker.api_url.NeoForged}/net/neoforged/neoforge/{neoforge_version}/neoforge-{neoforge_version}-installer.jar",
                            "sha1": "",
                            "size": 0,
                        }
                    },
                }
            ],
        }
        save_json_path.write_text(json.dumps(profile_json, ensure_ascii=False, indent=4), encoding="utf-8")
        self.download_minecraft(
            game_path,
            game_version_id,
            download_file=True,
            download_max_thread=download_max_thread,
            save_version_name=save_version_name,
        )
        self.files_checker.check_files(game_path, save_version_name, download_max_thread)
        versions_info = {}
        versions_info_path = game_path / "versions" / "VersionsInfo.json"
        if versions_info_path.is_file():
            versions_info = json.loads(versions_info_path.read_text("utf-8"))
        versions_info.update(
            {
                save_version_name: {
                    "Type": "NeoForge",
                    "Version": neoforge_version,
                    "LoaderVersion": neoforge_version,
                    "VanillaVersion": game_version_id,
                }
            }
        )
        versions_info_path.write_text(json.dumps(versions_info, ensure_ascii=False, indent=4), encoding="utf-8")
        return True

    def get_optifine_versions(self, game_version_id: str) -> dict | None:
        url = f"{self.files_checker.api_url.Optifine}/optifine/{game_version_id}"
        print(f"[OptiFine] 请求: {url}")
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            get_versions = response.json()
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            print(f"[OptiFine] 获取失败: {e}")
            return None
        all_versions = []
        stable_versions = []
        not_stable_versions = []
        for version_info in get_versions:
            optifine_ver = version_info.get("version", "")
            optifine_type = version_info.get("type", "")
            optifine_patch = version_info.get("patch", "")
            is_stable = optifine_type == "HD_U"
            the_info = {
                "GameVersion": game_version_id,
                "LoaderVersion": optifine_ver,
                "Stable": is_stable,
                "Type": optifine_type,
                "Patch": optifine_patch,
            }
            all_versions.append(the_info)
            if is_stable:
                stable_versions.append(the_info)
            else:
                not_stable_versions.append(the_info)
        result = {"All": all_versions, "Stable": stable_versions, "NotStable": not_stable_versions}
        self._cached_optifine_versions = result
        return result

    def download_optifine(
        self,
        game_path,
        game_version_id,
        optifine_version,
        optifine_type,
        optifine_patch,
        save_version_name,
        download_max_thread=32,
    ):
        game_path = Path(str(game_path))
        save_json_path = game_path / "versions" / save_version_name / f"{save_version_name}.json"
        save_json_path.parent.mkdir(parents=True, exist_ok=True)
        # 下载 OptiFine JAR
        optifine_jar_name = f"OptiFine-{optifine_version}.jar"
        optifine_jar_path = game_path / "versions" / save_version_name / optifine_jar_name
        try:
            jar_url = (
                f"{self.files_checker.api_url.Optifine}/optifine/{game_version_id}/{optifine_type}/{optifine_patch}"
            )
            jar_response = requests.get(jar_url, timeout=60)
            jar_response.raise_for_status()
            optifine_jar_path.write_bytes(jar_response.content)
        except requests.exceptions.RequestException:
            return False
        # 生成继承原版的 profile JSON
        profile_json = {
            "id": save_version_name,
            "inheritsFrom": game_version_id,
            "releaseTime": "2024-01-01T00:00:00+00:00",
            "time": "2024-01-01T00:00:00+00:00",
            "type": "release",
            "mainClass": "net.minecraft.launchwrapper.Launch",
            "arguments": {
                "game": ["--tweakClass", "optifine.OptiFineTweaker"],
                "jvm": [
                    "-Djava.library.path=${natives_directory}",
                    "-cp",
                    "${classpath}",
                ],
            },
            "libraries": [
                {
                    "name": f"optifine:OptiFine:{optifine_version}",
                    "downloads": {
                        "artifact": {
                            "path": f"versions/{save_version_name}/{optifine_jar_name}",
                            "url": "",
                            "sha1": "",
                            "size": 0,
                        }
                    },
                }
            ],
        }
        save_json_path.write_text(json.dumps(profile_json, ensure_ascii=False, indent=4), encoding="utf-8")
        self.download_minecraft(game_path, game_version_id, True, save_version_name, download_max_thread)
        self.files_checker.check_files(game_path, save_version_name, download_max_thread)
        versions_info = {}
        versions_info_path = game_path / "versions" / "VersionsInfo.json"
        if versions_info_path.is_file():
            versions_info = json.loads(versions_info_path.read_text("utf-8"))
        versions_info.update(
            {
                save_version_name: {
                    "Type": "OptiFine",
                    "Version": optifine_version,
                    "LoaderVersion": optifine_version,
                    "VanillaVersion": game_version_id,
                }
            }
        )
        versions_info_path.write_text(json.dumps(versions_info, ensure_ascii=False, indent=4), encoding="utf-8")
        return True
