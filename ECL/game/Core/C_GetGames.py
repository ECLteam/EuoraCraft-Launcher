import io
import json
import xml.etree.ElementTree as ET
import zipfile
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

    def set_api_url(self, api_url_dict: dict) -> None:
        self.files_checker.api_url.update_from_dict(api_url_dict)

    def get_minecraft_versions(self) -> dict | None:  # 获取版本列表
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
        self.output_log(
            f"download_minecraft: game_path={game_path}, version_id={version_id}, "
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
                    continue
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
        url = f"{self.files_checker.api_url.FabricMeta}/v2/versions/loader/{game_version_id}"
        self.output_log(f"请求: {url}")
        try:
            response = requests.get(url, timeout=30)
            self.output_log(f"状态码: {response.status_code}")
            if response.status_code == 404:
                self.output_log(f"版本 {game_version_id} 不被 Fabric 支持")
                return None
            response.raise_for_status()
            get_versions = response.json()
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            self.output_log(f"获取失败: {e}")
            return None
        self.output_log(f"返回条目数: {len(get_versions)}")
        if len(get_versions) <= 0:
            self.output_log(f"版本 {game_version_id} 无可用 Fabric 加载器")
            return None
        if len(get_versions) > 0:
            self.output_log(f"首条样例: {json.dumps(get_versions[0], ensure_ascii=False)[:300]}")
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
                self.output_log(f"跳过格式异常条目: {e} | {json.dumps(version_info, ensure_ascii=False)[:200]}")
                continue
        self.output_log(
            f"解析完成: All={len(all_versions)} Stable={len(stable_versions)} NotStable={len(not_stable_versions)}"
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
    ) -> bool:
        game_path = Path(str(game_path))
        save_version_name = (
            save_version_name if save_version_name else f"fabric-loader-{fabric_version}-{game_version_id}"
        )
        # 独立文件夹：versions/{save_version_name}/
        version_dir = game_path / "versions" / save_version_name
        version_dir.mkdir(parents=True, exist_ok=True)

        # 下载原版到 Fabric 文件夹（JAR + JSON + libraries）
        get_versions = self.get_minecraft_versions()
        if not get_versions:
            return False
        if download_vanilla:
            self.download_minecraft(game_path, game_version_id, True, download_max_thread, save_version_name, get_versions)

        # 获取 Fabric JSON
        try:
            response = requests.get(
                f"{self.files_checker.api_url.FabricMeta}/v2/versions/loader/{game_version_id}/{fabric_version}/profile/json",
                timeout=30,
            )
            response.raise_for_status()
            fabric_data = response.json()
        except requests.exceptions.RequestException:
            return False

        # 读取原版 JSON，合并到 Fabric JSON（不再需要独立原版文件夹）
        vanilla_json_path = version_dir / f"{save_version_name}.json"
        try:
            vanilla_data = json.loads(vanilla_json_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            vanilla_data = {}

        # 合并 arguments
        if "arguments" in vanilla_data:
            for arg_type in ("jvm", "game"):
                if arg_type in vanilla_data["arguments"]:
                    v_args = vanilla_data["arguments"][arg_type]
                    fabric_data.setdefault("arguments", {}).setdefault(arg_type, [])
                    # 原版参数在前，Fabric 参数在后
                    fabric_data["arguments"][arg_type] = v_args + fabric_data["arguments"][arg_type]

        # 合并 libraries：原版在前
        vanilla_libs = vanilla_data.get("libraries", [])
        if vanilla_libs:
            fabric_libs = fabric_data.get("libraries", [])
            fabric_data["libraries"] = vanilla_libs + fabric_libs

        # 合并 assetIndex / assets / mainClass
        for key in ("assetIndex", "assets", "mainClass"):
            if key not in fabric_data and key in vanilla_data:
                fabric_data[key] = vanilla_data[key]

        # 移除 inheritsFrom，消除对独立原版文件夹的依赖
        fabric_data.pop("inheritsFrom", None)
        fabric_data["id"] = save_version_name
        fabric_data["vanillaVersion"] = game_version_id  # 标记原版版本号，供扫描使用

        # 写入合并后的 JSON
        vanilla_json_path.write_text(json.dumps(fabric_data, ensure_ascii=False, indent=4), encoding="utf-8")

        # 写入 VersionsInfo
        get_version_info = {}
        for version_info in get_versions["All"]:
            if version_info["id"] == game_version_id:
                get_version_info = version_info
                break
        versions_info = {}
        versions_info_path = game_path / "versions" / "VersionsInfo.json"
        if versions_info_path.is_file():
            versions_info = json.loads(versions_info_path.read_text("utf-8"))
        versions_info.update(
            {
                save_version_name: {
                    "Type": "Fabric",
                    "Version": fabric_version,
                    "VanillaType": get_version_info.get("type", ""),
                    "VanillaVersion": game_version_id,
                }
            }
        )
        versions_info_path.write_text(json.dumps(versions_info, ensure_ascii=False, indent=4), encoding="utf-8")

        # 校验 Fabric 特有的 libraries
        self.files_checker.check_files(game_path, save_version_name, download_max_thread)
        return True

    def get_forge_versions(self, game_version_id: str) -> dict | None:
        url = f"{self.files_checker.api_url.ForgeMeta}/forge/minecraft/{game_version_id}"
        self.output_log(f"请求: {url}")
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            get_versions = response.json()
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            self.output_log(f"获取失败: {e}")
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
        game_path: str | Path,
        game_version_id: str,
        forge_version: str,
        save_version_name: str,
        download_max_thread: int = 32,
    ) -> bool:
        game_path = Path(str(game_path))
        self.output_log(
            f"download: game_path={game_path}, game_version_id={game_version_id}, "
            f"forge_version={forge_version}, save_version_name={save_version_name}"
        )
        # 独立文件夹：versions/{save_version_name}/
        version_dir = game_path / "versions" / save_version_name
        version_dir.mkdir(parents=True, exist_ok=True)

        # 多源 fallback：BMCLAPI 优先，官方源兜底
        jar_path = f"net/minecraftforge/forge/{game_version_id}-{forge_version}/forge-{game_version_id}-{forge_version}-installer.jar"
        installer_urls = [
            f"{self.files_checker.api_url.ForgeMaven}/{jar_path}",
            f"{self.files_checker.api_url.Forge}/{jar_path}",
        ]
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = None
        last_error = None
        for url in installer_urls:
            try:
                response = requests.get(url, timeout=60, headers=headers)
                response.raise_for_status()
                break
            except requests.exceptions.RequestException as e:
                last_error = e
                self.output_log(f"尝试 {url} 失败: {e}")
                continue
        if response is None:
            self.output_log(f"download json failed: 所有源均失败，最后错误: {last_error}")
            return False

        # 从 installer JAR 中提取 Forge JSON 数据
        try:
            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                try:
                    forge_data = json.loads(zf.read("version.json"))
                except KeyError:
                    install_profile = json.loads(zf.read("install_profile.json"))
                    version_info = install_profile.get("versionInfo")
                    if not version_info:
                        self.output_log("install_profile.json 中缺少 versionInfo")
                        return False
                    forge_data = version_info
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as e:
            self.output_log(f"download json failed: {e}")
            return False

        # 下载原版到 Forge 文件夹（JAR + JSON + libraries）
        get_versions = self.get_minecraft_versions()
        if not get_versions:
            return False
        self.download_minecraft(
            game_path,
            game_version_id,
            download_file=True,
            download_max_thread=download_max_thread,
            save_version_name=save_version_name,
            get_versions=get_versions,
        )

        # 读取原版 JSON
        save_json_path = version_dir / f"{save_version_name}.json"
        try:
            vanilla_data = json.loads(save_json_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            vanilla_data = {}

        # 合并原版数据到 Forge JSON
        if vanilla_data:
            # 合并 arguments（原版在前，Forge 在后）
            if "arguments" in vanilla_data:
                for arg_type in ("jvm", "game"):
                    if arg_type in vanilla_data["arguments"]:
                        v_args = vanilla_data["arguments"][arg_type]
                        forge_data.setdefault("arguments", {}).setdefault(arg_type, [])
                        forge_data["arguments"][arg_type] = v_args + forge_data["arguments"][arg_type]

            # 合并 libraries：原版在前
            vanilla_libs = vanilla_data.get("libraries", [])
            if vanilla_libs:
                forge_libs = forge_data.get("libraries", [])
                forge_data["libraries"] = vanilla_libs + forge_libs

            # 合并 assetIndex / assets / mainClass
            for key in ("assetIndex", "assets", "mainClass"):
                if key not in forge_data and key in vanilla_data:
                    forge_data[key] = vanilla_data[key]

        # 移除 inheritsFrom，消除对独立原版文件夹的依赖
        forge_data.pop("inheritsFrom", None)
        forge_data["id"] = save_version_name
        forge_data["vanillaVersion"] = game_version_id

        # 写入合并后的 JSON
        save_json_path.write_text(json.dumps(forge_data, ensure_ascii=False, indent=4), encoding="utf-8")

        # 校验文件
        self.files_checker.check_files(game_path, save_version_name, download_max_thread)

        # 写入 VersionsInfo
        get_version_info = {}
        for version_info in get_versions["All"]:
            if version_info["id"] == game_version_id:
                get_version_info = version_info
                break
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
                    "VanillaType": get_version_info.get("type", ""),
                    "VanillaVersion": game_version_id,
                }
            }
        )
        versions_info_path.write_text(json.dumps(versions_info, ensure_ascii=False, indent=4), encoding="utf-8")
        return True

    def get_quilt_versions(self, game_version_id: str) -> dict | None:
        if self._cached_quilt_versions:
            return self._cached_quilt_versions
        url = f"https://meta.quiltmc.org/v3/versions/loader/{game_version_id}"
        self.output_log(f"请求: {url}")
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            get_versions = response.json()
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            self.output_log(f"获取失败: {e}")
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
                self.output_log(f"跳过格式异常条目: {e} | {json.dumps(version_info, ensure_ascii=False)[:200]}")
                continue
        self.output_log(
            f"解析完成: All={len(all_versions)} Stable={len(stable_versions)} NotStable={len(not_stable_versions)}"
        )
        result = {"All": all_versions, "Stable": stable_versions, "NotStable": not_stable_versions}
        self._cached_quilt_versions = result
        return result

    def download_quilt(self, game_path: str | Path, game_version_id: str, quilt_version: str, save_version_name: str, download_max_thread: int = 32) -> bool:
        game_path = Path(str(game_path))
        self.output_log(
            f"download: game_path={game_path}, game_version_id={game_version_id}, "
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
            self.output_log(f"download json failed: {e}")
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
        self.output_log(f"请求: {url}")
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            root = ET.fromstring(response.text)
        except (requests.exceptions.RequestException, ET.ParseError) as e:
            self.output_log(f"获取失败: {e}")
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
        game_path: str | Path,
        game_version_id: str,
        neoforge_version: str,
        save_version_name: str,
        download_max_thread: int = 32,
    ) -> bool:
        game_path = Path(str(game_path))
        self.output_log(
            f"download: game_path={game_path}, game_version_id={game_version_id}, "
            f"neoforge_version={neoforge_version}, save_version_name={save_version_name}"
        )
        # 独立文件夹：versions/{save_version_name}/
        version_dir = game_path / "versions" / save_version_name
        version_dir.mkdir(parents=True, exist_ok=True)

        # 先下载原版到 NeoForge 文件夹（JAR + JSON + libraries）
        get_versions = self.get_minecraft_versions()
        if not get_versions:
            return False
        self.download_minecraft(
            game_path,
            game_version_id,
            download_file=True,
            download_max_thread=download_max_thread,
            save_version_name=save_version_name,
            get_versions=get_versions,
        )

        # 读取原版 JSON
        save_json_path = version_dir / f"{save_version_name}.json"
        try:
            vanilla_data = json.loads(save_json_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            vanilla_data = {}

        # 构建 NeoForge JSON（合并原版，消除 inheritsFrom）
        neo_data = {
            "id": save_version_name,
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

        # 合并原版数据
        if vanilla_data:
            # 合并 arguments（原版在前）
            if "arguments" in vanilla_data:
                for arg_type in ("jvm", "game"):
                    if arg_type in vanilla_data["arguments"]:
                        v_args = vanilla_data["arguments"][arg_type]
                        neo_data.setdefault("arguments", {}).setdefault(arg_type, [])
                        neo_data["arguments"][arg_type] = v_args + neo_data["arguments"][arg_type]

            # 合并 libraries：原版在前
            vanilla_libs = vanilla_data.get("libraries", [])
            if vanilla_libs:
                neo_data["libraries"] = vanilla_libs + neo_data["libraries"]

            # 合并 assetIndex / assets
            for key in ("assetIndex", "assets"):
                if key in vanilla_data:
                    neo_data[key] = vanilla_data[key]

        # 标记原版版本号
        neo_data["vanillaVersion"] = game_version_id

        # 写入合并后的 JSON
        save_json_path.write_text(json.dumps(neo_data, ensure_ascii=False, indent=4), encoding="utf-8")

        # 校验 NeoForge installer 等文件
        self.files_checker.check_files(game_path, save_version_name, download_max_thread)

        # 写入 VersionsInfo
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
        self.output_log(f"请求: {url}")
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            get_versions = response.json()
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            self.output_log(f"获取失败: {e}")
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
        game_path: str | Path,
        game_version_id: str,
        optifine_version: str,
        optifine_type: str,
        optifine_patch: str,
        save_version_name: str,
        download_max_thread: int = 32,
    ) -> bool:
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
