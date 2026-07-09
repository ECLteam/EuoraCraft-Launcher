import json
from collections.abc import Callable
from pathlib import Path

import requests

from . import C_Downloader, C_Libs


class FilesChecker:
    def __init__(self, api_url: C_Libs.ApiUrl | None = None, downloader: C_Downloader.Downloader | None = None):
        self.downloader = downloader or C_Downloader.Downloader()
        self.output_log: Callable[[str], None] = print
        self.api_url = api_url or C_Libs.ApiUrl()
        self.cancel_check: Callable[[], bool] = lambda: False

    def set_output_log(self, output_function: Callable[[str], None]) -> None:
        self.output_log = output_function

    def set_cancel_check(self, callback: Callable[[], bool]) -> None:
        self.cancel_check = callback

    def set_api_url(self, api_url_dict: dict):
        self.api_url.update_from_dict(api_url_dict)

    def __find_api(self, get_url: str, get_path: str) -> str:  # 判断获取下载根地址
        api_url = self.api_url.Libraries
        if "fabric" in get_url or "fabric" in get_path:
            api_url = self.api_url.Fabric
        elif "neoforged" in get_url or "neoforged" in get_path:
            api_url = self.api_url.NeoForged
        elif "forge" in get_url or "forge" in get_path:
            api_url = self.api_url.Forge
        elif "quilt" in get_url or "quilt" in get_path:
            api_url = self.api_url.Quilt
        return api_url

    def __check_game_jar(
        self, game_path: Path, version_name: str, version_json: dict
    ) -> list[tuple[str, str]]:  # 检查游戏本体
        download_list = []
        if "client" in version_json.get("downloads", {}):
            self.output_log("检查游戏本体...")
            game_jar_path = game_path / "versions" / version_name / f"{version_name}.jar"
            if C_Libs.get_file_sha1(game_jar_path) != version_json["downloads"]["client"]["sha1"]:
                download_list.append(
                    (
                        f"{self.api_url.Data}/v1/objects/{version_json['downloads']['client']['sha1']}/client.jar",
                        str(game_jar_path),
                    )
                )
            self.output_log(f"需要下载 {len(download_list)} 个文件")
        return download_list

    def __check_libraries(self, game_path: Path, version_json: dict) -> list[tuple[str, str]]:  # 检查依赖库的完整性
        download_list = []
        self.output_log("检查依赖库完整性...")
        for libraries in version_json.get("libraries", []):  # 检测补全libraries
            if self.cancel_check():
                self.output_log("文件校验已取消")
                return download_list
            if "classifiers" in libraries.get("downloads", {}):  # 补全natives
                for classifiers in libraries["downloads"]["classifiers"].values():
                    natives_path = game_path / "libraries" / classifiers["path"]
                    if C_Libs.get_file_sha1(natives_path) == classifiers["sha1"]:
                        continue
                    download_list.append(
                        (
                            f"{self.__find_api(classifiers['url'], classifiers['path'])}/{classifiers['path']}",
                            str(natives_path),
                        )
                    )
            get_path = C_Libs.name_to_path(libraries.get("name"))
            if not get_path:
                continue
            libraries_path = game_path / "libraries" / get_path
            file_sha1 = ""
            if "sha1" in libraries:
                file_sha1 = libraries["sha1"]
            elif "sha1" in libraries.get("downloads", {}).get("artifact", {}):
                file_sha1 = libraries["downloads"]["artifact"]["sha1"]
            if (not file_sha1 and libraries_path.is_file()) or C_Libs.get_file_sha1(libraries_path) == file_sha1:
                continue
            get_url = ""
            if "url" in libraries:
                get_url = libraries["url"]
            elif libraries.get("downloads", {}).get("artifact", {}).get("url"):
                get_url = libraries["downloads"]["artifact"]["url"]
            download_list.append((f"{self.__find_api(get_url, get_path)}/{get_path}", str(libraries_path)))
        self.output_log(f"需要下载 {len(download_list)} 个文件")
        return download_list

    def __check_assets(self, game_path: Path, version_json: dict) -> list[tuple[str, str]]:
        download_list = []
        self.output_log("检查资源完整性...")
        if "assetIndex" not in version_json:
            return download_list
        asset_id = version_json["assetIndex"]["id"]
        asset_index_path = game_path / "assets" / "indexes" / f"{asset_id}.json"
        index_file_sha1 = version_json["assetIndex"]["sha1"]
        if C_Libs.get_file_sha1(asset_index_path) != index_file_sha1:
            try:
                response = requests.get(
                    f"{self.api_url.Meta}/v1/packages/{index_file_sha1}/{asset_id}.json", timeout=30
                )
                response.raise_for_status()
                asset_index_path.parent.mkdir(parents=True, exist_ok=True)
                asset_index_path.write_text(response.text, encoding="utf-8")
            except requests.exceptions.RequestException as e:
                self.output_log(f"获取 asset index 失败: {e}")
        if not asset_index_path.is_file():
            return download_list
        api_url = self.api_url.Assets
        try:
            asset_index_json = json.loads(asset_index_path.read_text("utf-8"))
        except json.JSONDecodeError as e:
            self.output_log(f"解析 asset index 失败: {e}")
            return download_list
        for assets in asset_index_json["objects"].values():
            if self.cancel_check():
                self.output_log("文件校验已取消")
                return download_list
            asset_file_sha1 = assets["hash"]
            get_asset_path = f"{asset_file_sha1[:2]}/{asset_file_sha1}"
            asset_path = game_path / "assets" / "objects" / get_asset_path
            if C_Libs.get_file_sha1(asset_path) == asset_file_sha1:
                continue
            download_list.append((f"{api_url}/{get_asset_path}", str(asset_path)))
        self.output_log(f"需要下载 {len(download_list)} 个文件")
        return download_list

    def check_files(self, game_path: str | Path, version_name: str, download_max_thread: int):
        game_path = Path(game_path)
        self.output_log("正在检查文件请稍后...")
        if self.cancel_check():
            self.output_log("文件校验已取消")
            return
        if not (game_path / "versions" / version_name / f"{version_name}.json").is_file():
            self.output_log(f"未找到游戏 {version_name}")
            return
        download_list = []
        try:
            version_json = json.loads(
                (game_path / "versions" / version_name / f"{version_name}.json").read_text("utf-8")
            )
        except json.JSONDecodeError as e:
            self.output_log(f"解析版本 json 失败: {e}")
            return
        if self.cancel_check():
            self.output_log("文件校验已取消")
            return
        download_list.extend(self.__check_game_jar(game_path, version_name, version_json))
        if self.cancel_check():
            self.output_log("文件校验已取消")
            return
        download_list.extend(self.__check_libraries(game_path, version_json))
        if self.cancel_check():
            self.output_log("文件校验已取消")
            return
        download_list.extend(self.__check_assets(game_path, version_json))
        game_json = C_Libs.find_version(version_json, game_path)
        if game_json:
            download_list.extend(self.__check_game_jar(game_path, game_json[1].name, game_json[0]))
            if self.cancel_check():
                self.output_log("文件校验已取消")
                return
            download_list.extend(self.__check_libraries(game_path, game_json[0]))
            if self.cancel_check():
                self.output_log("文件校验已取消")
                return
            download_list.extend(self.__check_assets(game_path, game_json[0]))
        self.output_log(f"共有 {len(download_list)} 个文件需要下载")
        if len(download_list) < 1:
            return
        if self.cancel_check():
            self.output_log("文件校验已取消")
            return
        self.output_log("开始下载文件...")
        return self.downloader.download_manager(download_list, download_max_thread)
