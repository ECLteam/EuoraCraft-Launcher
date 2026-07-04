import json
import platform
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from shutil import rmtree

from ...common.logger import get_logger
from . import C_Downloader, C_FilesChecker, C_Libs, InstancesManager

logger = get_logger("core")


class ECLauncherCore:
    def __init__(self):
        self.output_launcher_log: Callable[[str], None] = print
        self.output_jvm_params: Callable[[str], None] = print

        self.api_url = C_Libs.ApiUrl()
        self.downloader = C_Downloader.Downloader()
        self.files_checker = C_FilesChecker.FilesChecker(self.api_url, self.downloader)
        self.instances_manager = InstancesManager.InstancesManager()

        self.system_type = platform.system()  # 获取系统类型
        self._cancel_launch = False  # 启动取消标志

    def set_api_url(self, api_url_dict: dict):  # 等价于 api_url.update_from_dict
        self.api_url.update_from_dict(api_url_dict)

    def set_output_launcher_log(self, output_function: Callable[[str], None]) -> None:
        self.output_launcher_log = output_function

        """
        {
            "Name": "Name",  # 实例名称
            "ID": "ID",  # 实例ID
            "Type": "MinecraftClient/MinecraftServer/Other",  # 实例类型(不局限于这三个)
            "StdIn": True,  # 是否支持输入管道, 默认支持输出和错误管道
            "Instance": subprocess.Popen  # 进程管道实例
        }
        """

    def set_output_jvm_params(self, output_function: Callable[[str], None]) -> None:
        self.output_jvm_params = output_function

    def cancel_launch(self) -> None:
        """取消当前启动流程，并终止已创建的游戏实例。"""
        self._cancel_launch = True
        self.downloader.cancel_all_downloads()
        threading.Thread(target=self.instances_manager.shutdown_all, args=(True,), daemon=True).start()

    def reset_cancel(self) -> None:
        """重置取消标志（每次启动前调用）。"""
        self._cancel_launch = False
        self.downloader.set_download_status(True)

    def is_canceled(self) -> bool:
        return self._cancel_launch

    def _pause_with_cancel(self, seconds: float, message: str) -> bool:
        """暂停指定秒数，每 0.1 秒检查取消标志。返回 True 表示已取消"""
        self.output_launcher_log(message)
        steps = int(seconds * 10)
        for _ in range(steps):
            if self._cancel_launch:
                self.output_launcher_log("启动已取消")
                return True
            time.sleep(0.1)
        return False

    def launch_minecraft(
        self,
        java_path: str | Path,
        game_path: str | Path,
        version_name: str,
        max_use_ram: int,
        player_name: str,
        user_type: str = "legacy",
        auth_uuid: str = "",
        access_token: str = "None",
        first_set_lang: str = "zh_CN",
        set_lang: str = "",
        launcher_name: str = "ECL",
        launcher_version: str = "0.1145",
        default_version_type: bool = False,
        custom_jvm_params: list[str] | None = None,
        window_width: int | str = "${resolution_width}",
        window_height: int | str = "${resolution_height}",
        completes_file: bool = True,
        download_max_thread: int = 32,
        output_jvm_params: bool = False,
        write_run_script: bool = False,
        run_script_path: str | Path = ".",
    ):
        if re.search(r"[^a-zA-Z0-9\-_+.]", player_name):  # 检测用户名是否合法
            error_meg = "玩家名称不能包含数字、减号、下划线、加号或英文句号(小数点)以外的字符"
            self.output_launcher_log(error_meg)
            raise ValueError(error_meg)

        if auth_uuid != "" and not C_Libs.is_uuid3(auth_uuid):  # 检测是否定义了UUID3,是否合法
            error_msg = "错误的 UUID, UUID 必须是 UUID3"
            self.output_launcher_log(error_msg)
            raise ValueError(error_msg)

        java_path = Path(java_path)
        game_path = Path(game_path)
        version_json = game_path / "versions" / version_name / f"{version_name}.json"

        if not java_path.is_file():
            error_msg = f"未找到 Java 可执行文件 {java_path}"
            self.output_launcher_log(error_msg)
            raise FileNotFoundError(error_msg)

        if not version_json.is_file():
            error_msg = f"未找到游戏 {version_name}"
            self.output_launcher_log(error_msg)
            raise FileNotFoundError(error_msg)

        if max_use_ram < 256:
            max_use_ram = 256

        if completes_file:
            self.files_checker.check_files(game_path, version_name, download_max_thread)
            if self.is_canceled():
                self.output_launcher_log("启动已取消")
                return
            if self._pause_with_cancel(2.0, "文件校验完成，即将构建启动参数..."):
                return

        jvm_params_list = []
        cp_delimiter = ":"  # ClassPath分隔符
        run_script_suffix = ".sh"
        self.output_launcher_log(f"系统平台 {self.system_type}")

        if self.system_type == "Windows":  # 判断是否为Windows
            run_script_suffix = ".bat"
            cp_delimiter = ";"
            jvm_params_list.append(
                "-XX:HeapDumpPath=MojangTricksIntelDriversForPerformance_javaw.exe_minecraft.exe.heapdump"
            )
        elif self.system_type == "Darwin":  # 判断是否为MacOS(OSX)
            run_script_suffix = ".command"
            jvm_params_list.append("-XstartOnFirstThread")

        jvm_params_list.extend(
            [
                "-Xms256M",
                f"-Xmx{max_use_ram}M",
                "-Dstderr.encoding=UTF-8",
                "-Dstdout.encoding=UTF-8",
                "-Dfile.encoding=UTF-8",
                "-XX:+UseG1GC",
                "-XX:-UseAdaptiveSizePolicy",
                "-XX:-OmitStackTraceInFastThrow",
                "-Dlog4j2.formatMsgNoLookups=true",
                "-Dfml.ignoreInvalidMinecraftCertificates=True",
                "-Dfml.ignorePatchDiscrepancies=True",
            ]
        )

        if custom_jvm_params:
            jvm_params_list.extend(custom_jvm_params)  # 添加自定义Jvm

        version_data = json.loads(version_json.read_text("utf-8"))

        if "arguments" in version_data:
            if "jvm" in version_data["arguments"]:
                for arguments_jvm in version_data["arguments"]["jvm"]:  # 遍历Json中的Jvm参数
                    if type(arguments_jvm) is not str:
                        continue
                    if "${classpath_separator}" in arguments_jvm:  # 这个判断针对NeoForged的,为-p参数的依赖两边加双引号
                        jvm_params_list.append(f'"{arguments_jvm.replace(" ", "")}"')
                    else:
                        jvm_params_list.append(arguments_jvm.replace(" ", ""))
            if "game" in version_data["arguments"]:
                for arguments_game in version_data["arguments"]["game"]:  # 遍历Json中的Jvm参数
                    if type(arguments_game) is not str:
                        continue
                    jvm_params_list.append(arguments_game.replace(" ", ""))
        elif "minecraftArguments" in version_data:
            jvm_params_list.extend(
                ["-Djava.library.path=${natives_directory}", "-cp ${classpath}", version_data["minecraftArguments"]]
            )

        if window_width != "${resolution_width}" or window_height != "${resolution_height}":
            jvm_params_list.append(f"--width {window_width} --height {window_height}")
        class_path_list = []
        asm_versions = []  # Fuck ASM!!!
        natives_path_list = []

        for libraries in version_data.get("libraries", []):  # 遍历依赖
            get_path = C_Libs.name_to_path(libraries.get("name"))
            if not get_path:
                continue
            libraries_path = game_path / "libraries" / get_path
            if str(libraries_path) in class_path_list:
                continue  # 防止重复添加
            if re.search(r"asm-\d+(?:\.\d+)*", libraries_path.stem):  # Fuck ASM!!!
                asm_versions.append(libraries_path)
                continue
            class_path_list.append(str(libraries_path))
            if "classifiers" not in libraries.get("downloads", {}):
                continue  # 查找natives
            for classifiers in libraries["downloads"]["classifiers"].values():
                natives_path = game_path / "libraries" / classifiers["path"]
                if natives_path in natives_path_list:
                    continue  # 防止重复添加
                natives_path_list.append(natives_path)

        version_jar = game_path / "versions" / version_name / f"{version_name}.jar"
        asset_index_id = ""

        if "id" in version_data.get("assetIndex", {}):
            asset_index_id = version_data["assetIndex"]["id"]

        game_json = C_Libs.find_version(version_data, game_path)

        if game_json:
            game_json, version_path = game_json
            if "arguments" in game_json:
                if "jvm" in game_json["arguments"]:
                    for arguments_jvm in game_json["arguments"]["jvm"]:  # 遍历Json中的Jvm参数
                        if type(arguments_jvm) is not str:
                            continue
                        arguments_jvm = arguments_jvm.replace(" ", "")
                        if arguments_jvm in jvm_params_list:
                            continue  # 防止重复添加
                        jvm_params_list.append(arguments_jvm)
                if "game" in game_json["arguments"]:
                    for arguments_game in game_json["arguments"]["game"]:  # 遍历Json中的Jvm参数
                        if type(arguments_game) is not str:
                            continue
                        arguments_game = arguments_game.replace(" ", "")
                        if arguments_game in jvm_params_list:
                            continue  # 防止重复添加
                        jvm_params_list.append(arguments_game)
            elif "minecraftArguments" not in version_data and "minecraftArguments" in game_json:
                jvm_params_list.extend(
                    ["-Djava.library.path=${natives_directory}", "-cp ${classpath}", game_json["minecraftArguments"]]
                )

            for libraries in game_json.get("libraries", []):  # 遍历依赖
                get_path = C_Libs.name_to_path(libraries.get("name"))
                if not get_path:
                    continue
                libraries_path = game_path / "libraries" / get_path
                if str(libraries_path) in class_path_list:
                    continue  # 防止重复添加
                if (
                    re.search(r"asm-\d+(?:\.\d+)*", libraries_path.stem) and libraries_path not in asm_versions
                ):  # Fuck ASM!!!
                    asm_versions.append(libraries_path)
                    continue
                class_path_list.append(str(libraries_path))
                if "classifiers" not in libraries.get("downloads", {}):
                    continue  # 查找natives
                for classifiers in libraries["downloads"]["classifiers"].values():
                    natives_path = game_path / "libraries" / classifiers["path"]
                    if natives_path in natives_path_list:
                        continue  # 防止重复添加
                    natives_path_list.append(natives_path)

            if not version_jar.is_file():
                version_jar = version_path / f"{version_path.name}.jar"

            if not asset_index_id:
                asset_index_id = game_json.get("assetIndex", {}).get("id", asset_index_id)

        asm_version = (0,)
        asm_path = ""

        for get_asm in asm_versions:  # Fuck ASM!!!
            asm_ver = get_asm.stem.replace("asm-", "")
            asm_parts = tuple(int(x) for x in asm_ver.split("."))  # 按版本号分段比较，避免 float 对三段版本号失败
            if asm_parts > asm_version:
                asm_version = asm_parts
                asm_path = str(get_asm)
        if asm_path:
            class_path_list.append(asm_path)

        class_path_list.append(str(version_jar))
        jvm_params = f'"{java_path}" {" ".join(jvm_params_list)}'
        class_path = f'"{cp_delimiter.join(class_path_list)}" {version_data["mainClass"]}'
        if self._pause_with_cancel(2.0, "启动参数构建完成，即将解压原生库..."):
            return
        natives_path = game_path / "versions" / version_name / "natives"
        is_set_lang = False

        if natives_path.is_dir():
            try:
                rmtree(natives_path)
            except OSError as e:
                logger.warning(f"删除 natives 目录失败: {e}")
            natives_path.mkdir(parents=True, exist_ok=True)
        else:
            is_set_lang = True
            natives_path.mkdir(parents=True, exist_ok=True)

        self.output_launcher_log(f"需要解压 {len(natives_path_list)} 个文件")
        for a_natives in natives_path_list:
            if self.is_canceled():  # 解压前检查取消标志
                return
            C_Libs.unzip(a_natives, natives_path)

        if self._pause_with_cancel(2.0, "原生库解压完成，即将启动游戏..."):
            return

        if is_set_lang or set_lang:  # 设置游戏语言
            options_contents = lang = f"lang:{set_lang}" if set_lang else f"lang:{first_set_lang}"
            options_path = game_path / "versions" / version_name / "options.txt"
            if options_path.is_file():
                options_contents = options_path.read_text("utf-8")
                options_contents = re.sub(r"^lang:\S+$", lang, options_contents, flags=re.MULTILINE)
            options_path.write_text(options_contents, "utf-8")
            self.output_launcher_log(f"设置游戏语言为 {lang}")

        if user_type == "legacy":  # 离线模式设置唯一标识id
            auth_uuid = C_Libs.name_to_uuid(player_name).hex
            self.output_launcher_log(f"未设置 UUID, 生成 UUID 为 {auth_uuid}")

        jvm_params = C_Libs.replace_last(
            jvm_params.replace("${classpath}", class_path)  # 把-cp参数内容换成拼接好的依赖路径
            .replace("${library_directory}", f'"{game_path / "libraries"}"', 1)  # 依赖文件夹路径
            .replace("${assets_root}", f'"{game_path / "assets"}"')  # 资源文件夹路径
            .replace("${assets_index_name}", asset_index_id)  # 资源索引id
            .replace("${natives_directory}", f'"{natives_path}"')  # 依赖库文件夹路径
            .replace("${game_directory}", f'"{game_path / "versions" / version_name}"')  # 游戏文件存储路径
            .replace("${launcher_name}", f'"{launcher_name}"')  # 启动器名字
            .replace("${launcher_version}", f'"{launcher_version}"')  # 启动器版本
            # .replace("${version_name}", f'"{version_name}"', -1)
            .replace(
                "${version_type}",
                f'"{version_data.get("type", launcher_name)}"' if default_version_type else f'"{launcher_name}"',
            )  # 版本类型
            .replace("${auth_player_name}", f'"{player_name}"')  # 玩家名字
            .replace("${user_type}", user_type)  # 登录方式
            .replace("${auth_uuid}", auth_uuid)
            .replace("${auth_access_token}", access_token)  # 正版登录令牌
            .replace("${user_properties}", "{}")  # 老版本的用户配置项
            .replace("${classpath_separator}", cp_delimiter)  # NeoForged的占位符,替换为ClassPath的分隔符
            .replace("${library_directory}", f"{game_path / 'libraries'}")  # NeoForged的占位符,获取依赖文件夹路径
            .replace("${primary_jar_name}", version_jar.name),  # NeoForged的占位符,替换为游戏本体Jar文件名
            "${version_name}",
            f'"{version_name}"',  # 版本名字
        ).replace("${version_name}", version_name)  # 特殊处理占位符,替换为游戏版本名称

        if self.is_canceled():
            self.output_launcher_log("启动已取消")
            return

        if self._pause_with_cancel(2.0, "即将启动游戏进程..."):
            return

        if write_run_script:
            run_script_path = Path(run_script_path) / f"run{run_script_suffix}"
            self.output_launcher_log(f"生成的启动脚本在 {run_script_path}")
            run_script_path.write_text(jvm_params, "utf-8")
        if output_jvm_params:
            self.output_launcher_log("输出启动参数")
            self.output_jvm_params(jvm_params)
        else:
            if self.is_canceled():
                self.output_launcher_log("启动已取消")
                return
            self.output_launcher_log(f"正在启动游戏 [{version_name}]")
            self.instances_manager.create_instance(
                instance_name=version_name,
                instance_type="MinecraftClient",
                args=jvm_params,
                cwd=(game_path / "versions" / version_name),
                only_stdout=True,
            )  # 启动游戏
