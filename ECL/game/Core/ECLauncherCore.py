from dataclasses import dataclass, asdict, fields
from shutil import rmtree
from pathlib import Path
import platform
import json
import Libs
import re

class JvmArgumentBuilder:
    """构建 JVM 参数字符串"""
    def __init__(
        self,
        java_path: Path | str,
        version_name: str,
        use_ram: int,
        use_gc: str = "G1GC"
    ):
        """
        初始化
        :param java_path: Java 可执行文件路径
        :param version_name: 版本名称
        :param use_ram: 分配给 Minecraft 的内存(MB)
        :param use_gc: Jvm 使用什么 GC, 如 "G1GC" 或 "ZGC"
        """
        self.java_path = Path(java_path)
        self.version_name = version_name
        self.use_ram = use_ram
        self.use_gc = use_gc

        self.system = platform.system()
        self.args = []

        self._add_base_args()

    def _add_base_args(self) -> None:
        self.args.extend([
            f'"{self.java_path}"',
            f"-Xms{self.use_ram}M",
            f"-Xmx{self.use_ram}M",
            "-Dstderr.encoding=UTF-8",
            "-Dstdout.encoding=UTF-8",
            "-Dfile.encoding=UTF-8",
            f"-XX:+Use{self.use_gc}",
            "-XX:-UseAdaptiveSizePolicy",
            "-XX:-OmitStackTraceInFastThrow",
            "-Dlog4j2.formatMsgNoLookups=true",
            "-Dfml.ignoreInvalidMinecraftCertificates=True",
            "-Dfml.ignorePatchDiscrepancies=True"
        ])
        if self.system == "Windows":
            self.args.append("-XX:HeapDumpPath=MojangTricksIntelDriversForPerformance_javaw.exe_minecraft.exe.heapdump")
        elif self.system == "Darwin":
            self.args.append("-XstartOnFirstThread")

    def add_from_version_json(self, version_json: dict) -> "JvmArgumentBuilder":
        """
        读取 Meta Json 内容添加相应 Jvm 参数
        :param version_json: Meta Json
        :return: 返回实例自身
        """
        if "arguments" in version_json:
            if "jvm" in version_json["arguments"]:
                for arguments_jvm in version_json["arguments"]["jvm"]:
                    if type(arguments_jvm) is not str:
                        continue
                    if arguments_jvm in self.args:
                        continue
                    self.args.append(arguments_jvm)
            if "game" in version_json["arguments"]:
                for arguments_game in version_json["arguments"]["game"]:
                    if type(arguments_game) is not str:
                        continue
                    if arguments_game in self.args:
                        continue
                    self.args.append(arguments_game)
        elif "minecraftArguments" in version_json:
            ex_args = [
                "-Djava.library.path=${natives_directory}",
                "-cp ${classpath}",
                version_json["minecraftArguments"]
            ]
            for arg in ex_args:
                if arg in self.args:
                    continue
                self.args.append(arg)
        return self

    def add_custom(self, custom_args: list[str]) -> "JvmArgumentBuilder":
        """
        添加自定义 Jvm 参数(把握好添加时机,参数位置不对可能导致崩溃)
        :param custom_args: 参数列表 ["..."]
        :return: 返回实例自身
        """
        if custom_args:
            self.args.extend(custom_args)
        return self

    def get_args(self) -> list[str]:
        """
        获取 Jvm 参数列表
        :return: Jvm 参数列表
        """
        return self.args

    def build(self) -> str:
        """
        构建 Jvm 参数为单条指令
        :return: 初始指令(未替换占位符)
        """
        self.args.extend([
            "--width ${resolution_width}",
            "--height ${resolution_height}",
        ])
        return " ".join(self.args)

class ClasspathBuilder:
    """构建 ClassPath，包含 ASM 版本过滤"""
    def __init__(self, game_path: Path | str):
        """
        初始化
        :param game_path: .minecraft 路径
        """
        self.game_path = Path(game_path)
        self.classpath = []
        self.asm_versions = []
        self.natives = []

    def add_libraries(self, version_json: dict) -> "ClasspathBuilder":
        """
        读取 Meta Json 内容添加相应 Libraries
        :param version_json: Meta Json
        :return: 返回实例自身
        """
        for lib in version_json.get("libraries", []):
            r_path = Libs.name_to_path(lib["name"])
            if not r_path:
                continue
            lib_path = self.game_path / "libraries" / r_path
            if str(lib_path) in self.classpath:
                continue
            # ASM 版本过滤
            if re.search(r"asm-\d+(?:\.\d+)*", lib_path.stem):
                self.asm_versions.append(lib_path)
                continue
            self.classpath.append(str(lib_path))
            if "classifiers" not in lib.get("downloads", {}):
                continue  # 查找natives
            for classifiers in lib["downloads"]["classifiers"].values():
                natives_path = self.game_path / "libraries" / classifiers["path"]
                if natives_path in self.natives:
                    continue  # 防止重复添加
                self.natives.append(natives_path)
        return self

    def add_version_jar(self, jar_path: Path) -> "ClasspathBuilder":
        """
        添加游戏本体 Jar, 这个需要最后执行(在构建 Classpath 之前)
        :param jar_path: 游戏本体 Jar 文件路径
        :return: 返回实例自身
        """
        self._select_best_asm()
        self.classpath.append(str(jar_path))
        return self

    def _select_best_asm(self):
        """选择最高版本的 ASM，避免重复加载"""
        if not self.asm_versions:
            return
        # 使用 packaging.version 或简单数值比较
        best = max(self.asm_versions, key=lambda p: self._parse_asm_version(p.stem))
        self.classpath.append(str(best))

    @staticmethod
    def _parse_asm_version(stem: str) -> tuple[int, ...]:
        # "asm-9.4.1" -> (9, 4, 1)
        parts = stem.replace("asm-", "").split(".")
        return tuple(int(x) for x in parts)

    def get_natives(self) -> list[str]:
        """
        获取 Natives 原生库列表(需要解压)
        :return: Natives 原生库列表
        """
        return self.natives

    def get_classpath(self) -> list[str]:
        """
        获取 Classpath 列表
        :return: Classpath 列表
        """
        return self.classpath

    def build(self, cp_delimiter:str = ":") -> str:
        """
        构建 Classpath 字符串
        :param cp_delimiter: Classpath 分隔符, 通常系统为 ":", Windows 为 ";"
        :return: 构建好的 Classpath 字符串
        """
        return cp_delimiter.join(self.classpath)


@dataclass(frozen=True)
class LaunchConfig:
    """启动游戏所需的所有变量，避免散落在各处"""
    java_path: str | Path
    """Java 可执行文件路径"""
    game_path: str | Path
    """.minecraft 路径"""
    version_name: str
    """游戏版本名称"""
    use_ram: int
    """分配给 Minecraft 的内存(MB)"""
    player_name: str
    """玩家昵称"""
    auth_uuid: str
    """登录的 UUID(UUID3)"""
    user_type: str = "legacy"
    """用户类型, "legacy" 为离线登录, "msa" 为 Microsoft 登录"""
    access_token: str = "None"
    """user_type 非 "legacy" 登录需要添加 Token 令牌"""
    use_gc: str = "G1GC"
    """Jvm 使用什么 GC, 如 "G1GC" 或 "ZGC" """
    launcher_name: str = "ECL"
    """启动器名称"""
    launcher_version: str = "0.11.45"
    """启动器版本号(似乎没啥用)"""
    custom_jvm_params: list[str] | None = None
    """添加额外的 Jvm 参数"""
    version_isolation: bool = False
    """是否隔离版本, 不推荐不隔离"""
    window_width: int | str = "${resolution_width}"
    """Minecraft 窗口宽度(px)"""
    window_height: int | str = "${resolution_height}"
    """Minecraft 窗口高度(px)"""

    def get(self, key_name: str) -> str | None:
        """
        通过元素名称查找值
        :param key_name: 元素名称
        :return: 对应值
        """
        return getattr(self, key_name, None)

    def to_dict(self) -> dict[str, str]:
        """
        转为字典
        :return: {"API": "URL"}
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, api_url_dict: dict) -> "LaunchConfig":
        """
        从字典创建实例, 不存在的键值则默认
        :param api_url_dict: {"API": "URL"}
        :return: ApiUrlConfig 实例
        """
        kw = {}
        for api_name in fields(cls):
            if api_name.name in api_url_dict: kw.update({api_name.name: api_url_dict[api_name.name].strip("/")})
        return cls(**kw)

    def update_from_dict(self, api_url_dict: dict) -> None:
        """
        从字典中更新元素值
        :param api_url_dict: {"API": "URL"}
        :return: Nome
        """
        for api_name in fields(self):
            if api_name.name in api_url_dict: setattr(self, api_name.name, api_url_dict[api_name.name].strip("/"))


class PlaceholderReplacer:
    """占位符替换器"""
    def __init__(
        self,
        config: LaunchConfig,
        classpath: str,
        main_class: str,
        index_id: str,
        natives_dir: Path | str,
        version_jar_path: Path | str,
        cp_delimiter:str = ":",
        version_isolation: bool = False
    ):
        """
        初始化
        :param config: LaunchConfig 实例
        :param classpath: 构建好的 Classpath 字符串
        :param main_class: Java 程序入口
        :param index_id: 资源引索 ID
        :param natives_dir: Natives 原生库路径
        :param version_jar_path: 游戏本体 Jar 文件路径
        :param cp_delimiter: Classpath 分隔符, 通常系统为 ":", Windows 为 ";"
        :param version_isolation: 是否隔离版本, 不推荐不隔离
        """
        self.config = config
        self.classpath = classpath
        self.main_class = main_class
        self.index_id = index_id
        self.natives_dir = natives_dir
        self.version_jar_path = version_jar_path
        self.cp_delimiter = cp_delimiter
        self.version_isolation = version_isolation

    def _build_standard_replacements(self) -> dict[str, str]:
        """构建除 classpath 和 version_name 外的所有占位符映射"""
        game_dir = Path(self.config.game_path) / "versions"
        if not self.version_isolation:
            game_dir = game_dir / self.config.version_name
        return {
            "library_directory": str(Path(self.config.game_path) / "libraries"),
            "assets_root": str(Path(self.config.game_path) / "assets"),
            "assets_index_name": self.index_id,
            "natives_directory": str(self.natives_dir),
            "game_directory": str(game_dir),
            "launcher_name": self.config.launcher_name,
            "launcher_version": self.config.launcher_version,
            "version_type": self.config.launcher_name,
            "auth_player_name": self.config.player_name,
            "user_type": self.config.user_type,
            "auth_uuid": self.config.auth_uuid,
            "auth_access_token": self.config.access_token,
            "user_properties": "{}",
            "classpath_separator": self.cp_delimiter,
            "primary_jar_name": str(Path(self.version_jar_path).name),
            "resolution_width": str(self.config.window_width),
            "resolution_height": str(self.config.window_height),
        }

    @staticmethod
    def _replace_last(text: str, old: str, new: str) -> str:
        """
        只替换字符串中最后一次出现的 old
        等价于原 C_Libs.replace_last 的逻辑
        """
        return new.join(text.rsplit(old, 1))

    def replace(self, raw_command: str) -> str:
        """
        替换掉占位符
        :param raw_command: 初始指令(未替换占位符)
        :return: 替换好的指令
        """
        result = raw_command

        for key, value in self._build_standard_replacements().items():
            result = result.replace(f"${{{key}}}", f'"{value}"')

        version = self.config.version_name
        result = (
            self._replace_last(result, "${version_name}", f'"{version}"')
                .replace("${version_name}", version)
                .replace("${classpath}", f'"{self.classpath}" "{self.main_class}"')
        )
        result = result

        return result


def build_minecraft_cmd(config: LaunchConfig) -> str:
    """
    准备启动 Minecraft 并构建启动指令
    :param config: LaunchConfig 实例
    :return: 构建好的启动指令
    """

    jvm_builder = JvmArgumentBuilder(
        java_path=config.java_path,
        version_name=config.version_name,
        use_ram=config.use_ram,
        use_gc=config.use_gc
    )

    version_json = json.loads(
        (
            Path(config.game_path) / "versions" / config.version_name / f"{config.version_name}.json"
        ).read_text("utf-8")
    )

    jvm_builder.add_from_version_json(version_json)

    cp_builder = ClasspathBuilder(config.game_path)
    cp_builder.add_libraries(version_json)

    version_jar = Path(config.game_path) / "versions" / config.version_name / f"{config.version_name}.jar"
    index_id = ""
    if "id" in version_json.get("assetIndex", {}):
        index_id = version_json["assetIndex"]["id"]

    game_json = Libs.find_version(version_json, config.game_path)
    if game_json:
        jvm_builder.add_from_version_json(game_json[0])
        cp_builder.add_libraries(game_json[0])
        index_id = game_json[0].get("assetIndex", {}).get("id", index_id)

        if not version_jar.is_file():
            version_jar = game_json[1] / f"{game_json[1].name}.jar"

    if config.custom_jvm_params:
        jvm_builder.add_custom(config.custom_jvm_params)

    cp_builder.add_version_jar(version_jar)
    cp_delimiter = ":" if platform.system() != "Windows" else ";"

    natives_path = Path(config.game_path) / "versions" / config.version_name / "natives"
    if natives_path.is_dir():
        try:
            rmtree(natives_path)
        except OSError:
            pass
        natives_path.mkdir(parents=True, exist_ok=True)
    else:
        natives_path.mkdir(parents=True, exist_ok=True)
    for native in cp_builder.get_natives():
        Libs.unzip(native, natives_path)

    cmd = PlaceholderReplacer(
        config=config,
        classpath=cp_builder.build(cp_delimiter),
        main_class=version_json["mainClass"],
        index_id=index_id,
        natives_dir=natives_path,
        version_jar_path=version_jar,
        cp_delimiter=cp_delimiter
    )

    return cmd.replace(jvm_builder.build())