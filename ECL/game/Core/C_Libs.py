import hashlib
import json
import zipfile
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID


def replace_last(text: str, old: str, new: str) -> str:  # 替换字符串最后一个匹配项, 到底是为什么适配的呢?好难猜啊
    return new.join(text.rsplit(old, 1))


def name_to_path(name: str) -> str | None:  # 将文件名字转换为路径函数
    at_index = name.find("@")
    if at_index != -1:
        suffix = name[at_index + 1 :]
        name = name[0:at_index]
    else:
        suffix = "jar"
    parts = name.split(":")
    if len(parts) == 4:
        return f"{parts[0].replace('.', '/')}/{parts[1]}/{parts[2]}/{parts[1]}-{parts[2]}-{parts[3]}.{suffix}"
    elif len(parts) == 3:
        return f"{parts[0].replace('.', '/')}/{parts[1]}/{parts[2]}/{parts[1]}-{parts[2]}.{suffix}"
    else:
        return None


def name_to_uuid(name: str) -> UUID:  # 将玩家昵称转换为UUID3函数
    return UUID(bytes=hashlib.md5(f"OfflinePlayer:{name}".encode()).digest()[:16], version=3)


def is_uuid3(uuid_string: str) -> bool:  # 检测一个字符串是否为UUID3函数
    try:
        return UUID(uuid_string, version=3).version == 3
    except ValueError:
        return False


def unzip(zip_path: str | Path, unzip_path: str | Path) -> bool:  # 解压文件函数
    try:
        with zipfile.ZipFile(zip_path) as zip_object:
            for file in zip_object.namelist():
                # 检查路径安全，防止 Zip Slip
                target = Path(unzip_path) / file
                if not str(target.resolve()).startswith(str(Path(unzip_path).resolve())):
                    continue  # 跳过不安全路径
                zip_object.extract(file, unzip_path)
    except (zipfile.BadZipFile, FileNotFoundError) as e:
        print(f"解压失败: {e}")
        return False
    return True


def get_file_sha1(file_path: str | Path) -> str:  # 获取文件 Sha1
    sha1 = hashlib.sha1()
    if Path(file_path).is_file():
        with Path(file_path).open("rb") as open_file:
            for file_part in iter(lambda: open_file.read(8192), b""):
                sha1.update(file_part)
    return sha1.hexdigest()


def find_version(version_json: dict, game_path: Path) -> tuple[dict, Path] | None:
    if "inheritsFrom" in version_json:  # 若有Mod加载器则寻找原版游戏
        inherits_from = version_json["inheritsFrom"]
        for version_path in (
            game_path / "versions"
        ).iterdir():  # 通过版本Json内的id键查找是否为对应的游戏版本, 而不是根据Json的名字判断
            if not version_path.is_dir():
                continue
            game_json_path = version_path / f"{version_path.name}.json"
            if not game_json_path.is_file():
                continue
            try:
                game_json = json.loads(game_json_path.read_text("utf-8"))
            except json.JSONDecodeError:
                continue
            if game_json.get("id") != inherits_from:
                continue
            return game_json, version_path
        version_path = game_path / "versions" / inherits_from
        if (version_path / f"{inherits_from}.json").is_file():  # 如果没找到则尝试直接找inheritsFrom对应的版本
            return json.loads((version_path / f"{inherits_from}.json").read_text("utf-8")), version_path
        return None
    return None


@dataclass
class ApiUrl:  # Api数据结构
    Meta: str = "https://launchermeta.mojang.com"
    Data: str = "https://launcher.mojang.com"
    Libraries: str = "https://libraries.minecraft.net"
    Assets: str = "https://resources.download.minecraft.net"
    Forge: str = "https://files.minecraftforge.net/maven"
    ForgeMeta: str = "https://bmclapi2.bangbang93.com"  # BMCLAPI 镜像（Forge/OptiFine 版本列表）
    Fabric: str = "https://maven.fabricmc.net"
    FabricMeta: str = "https://meta.fabricmc.net"
    NeoForged: str = "https://maven.neoforged.net/releases"
    OptiFine: str = "https://bmclapi2.bangbang93.com"  # OptiFine 下载（BMCLAPI）
    Quilt: str = "https://maven.quiltmc.org"
    QuiltMeta: str = "https://meta.quiltmc.org"

    def get(self, key_name: str) -> dict[str, str] | None:
        return getattr(self, key_name, None)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, api_url_dict: dict):
        kw = {}
        for api_name in fields(cls):
            if api_name.name in api_url_dict:
                kw.update({api_name.name: api_url_dict[api_name.name].strip("/")})
        return cls(**kw)

    def update_from_dict(self, api_url_dict: dict):
        for api_name in fields(self):
            if api_name.name in api_url_dict:
                setattr(self, api_name.name, api_url_dict[api_name.name].strip("/"))


def parse_datetime(time_str: str):  # 前端不建议用
    """
    解析时间字符串，提取日期、时间、时区，并转换为UTC+8(偏移8h)

    Args:
        time_str: ISO格式时间字符串，如 "2025-12-16T12:42:29+00:00"(Minecraft 26.1-snapshot-1)

    Returns:
       dict[str, dict[str, datetime | date | time | tzinfo | None | str | timedelta]]
    """
    # 解析时间字符串
    original_dt = datetime.fromisoformat(time_str)
    # 转换为UTC+8时间
    converted_dt = original_dt.astimezone(timezone(timedelta(hours=8)))
    return {
        "Original": {
            "Datetime": original_dt,
            "Date": original_dt.date(),  # 日期
            "Time": original_dt.time(),  # 时间
            "Timezone": original_dt.tzinfo,  # 时区
            "Iso": original_dt.isoformat(),  # ISO格式时间
            "Offset": original_dt.utcoffset(),  # 偏移
        },
        "Converted": {
            "Datetime": converted_dt,
            "Date": converted_dt.date(),
            "Time": converted_dt.time(),
            "Timezone": converted_dt.tzinfo,
            "Iso": converted_dt.isoformat(),
            "Offset": converted_dt.utcoffset(),
        },
    }
