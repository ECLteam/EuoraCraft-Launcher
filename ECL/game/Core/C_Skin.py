import base64
import hashlib
import json
import os
import threading
from configparser import ConfigParser
from io import BytesIO
from pathlib import Path
from typing import Any

from ...common.env import get_runtime_dir

import requests
from PIL import Image

from ...common.logger import get_logger

logger = get_logger("skin")

SKIN_CACHE_DIR_NAME = "ECL_Libs/Cache/Skin"
_SKIN_DOWNLOAD_LOCK = threading.Lock()
_SKIN_INDEX_LOCK = threading.Lock()


def _get_project_root() -> Path:
    return get_runtime_dir()


def _get_default_skin_path(skin_type: str) -> Path:
    ecl_libs_path = _get_project_root() / "ECL_Libs" / "Skins" / f"{skin_type}.png"
    if ecl_libs_path.exists():
        return ecl_libs_path

    ui_dist_path = _get_project_root() / "ui" / "dist" / "Skins" / f"{skin_type}.png"
    if ui_dist_path.exists():
        return ui_dist_path
    dev_path = _get_project_root() / ".." / "EuoraCraft-UI" / "public" / "Skins" / f"{skin_type}.png"
    if dev_path.exists():
        return dev_path

    return ecl_libs_path


def _get_skin_cache_dir() -> Path:
    cache_dir = _get_project_root() / SKIN_CACHE_DIR_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _get_skin_index_path(type_name: str) -> Path:
    skin_dir = _get_skin_cache_dir()
    return skin_dir / f"Index{type_name}.ini"


def _load_skin_index(type_name: str) -> ConfigParser:
    with _SKIN_INDEX_LOCK:
        path = _get_skin_index_path(type_name)
        parser = ConfigParser()
        parser.optionxform = str
        if path.exists():
            parser.read(path, encoding="utf-8")
        if "skins" not in parser.sections():
            parser["skins"] = {}
        return parser


def _save_skin_index(parser: ConfigParser, type_name: str) -> None:
    with _SKIN_INDEX_LOCK:
        path = _get_skin_index_path(type_name)
        with path.open("w", encoding="utf-8") as f:
            parser.write(f)


def _get_cached_skin_address(uuid: str, type_name: str) -> str | None:
    uuid_key = uuid.lower()
    parser = _load_skin_index(type_name)
    return parser["skins"].get(uuid_key)


def _cache_skin_address(uuid: str, type_name: str, skin_url: str) -> None:
    uuid_key = uuid.lower()
    parser = _load_skin_index(type_name)
    parser["skins"][uuid_key] = skin_url
    _save_skin_index(parser, type_name)

_SKIN_DATA = {
    "old": {
        "rightLeg": {"cropBox": (8, 40, 8, 24), "mirror": False},
        "leftLeg": {"cropBox": (8, 40, 8, 24), "mirror": True},
        "rightArm": {"cropBox": (86, 40, 6, 24), "mirror": False},
        "leftArm": {"cropBox": (86, 40, 6, 24), "mirror": True},
        "torso": {"cropBox": (40, 40, 16, 24), "mirror": False},
        "head": {"cropBox": (16, 16, 16, 16), "mirror": False},
        "headSide": {"cropBox": (0, 16, 16, 16), "mirror": False},
        "headOuter": {"cropBox": (80, 16, 16, 16), "mirror": False},
    },
    "new": {
        "rightLeg": {"cropBox": (8, 40, 8, 24), "mirror": False},
        "rightLegOuter": {"cropBox": (8, 72, 8, 24), "mirror": False},
        "leftLeg": {"cropBox": (40, 104, 8, 24), "mirror": False},
        "leftLegOuter": {"cropBox": (8, 104, 8, 24), "mirror": False},
        "rightArm": {"cropBox": (86, 40, 6, 24), "mirror": False},
        "rightArmSide": {"cropBox": (98, 40, 6, 24), "mirror": False},
        "rightArmOuter": {"cropBox": (88, 72, 6, 24), "mirror": False},
        "leftArm": {"cropBox": (74, 104, 6, 24), "mirror": False},
        "leftArmSide": {"cropBox": (92, 40, 6, 24), "mirror": False},
        "leftArmOuter": {"cropBox": (104, 104, 6, 24), "mirror": False},
        "torso": {"cropBox": (40, 40, 16, 24), "mirror": False},
        "torsoOuter": {"cropBox": (40, 72, 16, 24), "mirror": False},
        "head": {"cropBox": (16, 16, 16, 16), "mirror": False},
        "headSide": {"cropBox": (0, 16, 16, 16), "mirror": False},
        "headOuter": {"cropBox": (80, 16, 16, 16), "mirror": False},
    },
}

_MINIMAL_OPERATIONS = {
    "head": [
        (_SKIN_DATA["new"]["head"]["cropBox"], _SKIN_DATA["new"]["head"]["mirror"], 37.5, (200, 200)),
        (_SKIN_DATA["new"]["headOuter"]["cropBox"], _SKIN_DATA["new"]["headOuter"]["mirror"], 41, (175, 175)),
    ],
    "full": {
        "old": [
            (_SKIN_DATA["old"]["torso"]["cropBox"], _SKIN_DATA["old"]["torso"]["mirror"], 8.0625, (437, 561)),
            (_SKIN_DATA["old"]["rightLeg"]["cropBox"], _SKIN_DATA["old"]["rightLeg"]["mirror"], 8.375, (434, 751)),
            (_SKIN_DATA["old"]["leftLeg"]["cropBox"], _SKIN_DATA["old"]["leftLeg"]["mirror"], 8.375, (505, 751)),
            (_SKIN_DATA["old"]["rightArm"]["cropBox"], _SKIN_DATA["old"]["rightArm"]["mirror"], 8.167, (388, 561)),
            (_SKIN_DATA["old"]["leftArm"]["cropBox"], _SKIN_DATA["old"]["leftArm"]["mirror"], 8.167, (566, 561)),
            (_SKIN_DATA["old"]["head"]["cropBox"], _SKIN_DATA["old"]["head"]["mirror"], 26.875, (287, 131)),
            (_SKIN_DATA["old"]["headOuter"]["cropBox"], _SKIN_DATA["old"]["headOuter"]["mirror"], 30.8125, (254, 107)),
        ],
        "new": [
            (_SKIN_DATA["new"]["torso"]["cropBox"], _SKIN_DATA["new"]["torso"]["mirror"], 8.0625, (437, 561)),
            (_SKIN_DATA["new"]["torsoOuter"]["cropBox"], _SKIN_DATA["new"]["torsoOuter"]["mirror"], 8.6575, (432, 555)),
            (_SKIN_DATA["new"]["rightLeg"]["cropBox"], _SKIN_DATA["new"]["rightLeg"]["mirror"], 8.375, (434, 751)),
            (
                _SKIN_DATA["new"]["rightLegOuter"]["cropBox"],
                _SKIN_DATA["new"]["rightLegOuter"]["mirror"],
                9.375,
                (428, 737),
            ),
            (_SKIN_DATA["new"]["leftLeg"]["cropBox"], _SKIN_DATA["new"]["leftLeg"]["mirror"], 8.375, (505, 751)),
            (
                _SKIN_DATA["new"]["leftLegOuter"]["cropBox"],
                _SKIN_DATA["new"]["leftLegOuter"]["mirror"],
                9.375,
                (503, 737),
            ),
            (_SKIN_DATA["new"]["rightArm"]["cropBox"], _SKIN_DATA["new"]["rightArm"]["mirror"], 8.167, (388, 561)),
            (
                _SKIN_DATA["new"]["rightArmOuter"]["cropBox"],
                _SKIN_DATA["new"]["rightArmOuter"]["mirror"],
                9.5,
                (382, 538),
            ),
            (_SKIN_DATA["new"]["leftArm"]["cropBox"], _SKIN_DATA["new"]["leftArm"]["mirror"], 8.167, (566, 561)),
            (
                _SKIN_DATA["new"]["leftArmOuter"]["cropBox"],
                _SKIN_DATA["new"]["leftArmOuter"]["mirror"],
                9.5,
                (564, 538),
            ),
            (_SKIN_DATA["new"]["head"]["cropBox"], _SKIN_DATA["new"]["head"]["mirror"], 26.875, (287, 131)),
            (_SKIN_DATA["new"]["headOuter"]["cropBox"], _SKIN_DATA["new"]["headOuter"]["mirror"], 30.8125, (254, 107)),
        ],
    },
}


def _preprocess_skin_image(skin_img: Image.Image) -> Image.Image:
    w, h = skin_img.size
    if w == 64 and h == 32:
        return skin_img.resize((128, 64), Image.NEAREST)
    return skin_img.resize((128, 128), Image.NEAREST)


def _process_image(
    skin_img: Image.Image,
    crop_box: tuple[int, int, int, int],
    mirror: bool,
    scale_factor: float,
) -> Image.Image:
    x, y, cw, ch = crop_box
    part = skin_img.crop((x, y, x + cw, y + ch))
    new_w = int(cw * scale_factor)
    new_h = int(ch * scale_factor)
    if new_w != cw or new_h != ch:
        part = part.resize((new_w, new_h), Image.NEAREST)
    if mirror:
        part = part.transpose(Image.FLIP_LEFT_RIGHT)
    return part


def _get_operations(avatar_type: str, original_size: tuple[int, int]) -> list:
    if not _MINIMAL_OPERATIONS:
        return []
    if avatar_type == "head":
        return _MINIMAL_OPERATIONS["head"]
    if avatar_type in ("big-head", "big_head"):
        avatar_type = "full"
    skin_version = "old" if original_size == (64, 32) else "new"
    return _MINIMAL_OPERATIONS.get(avatar_type, {}).get(skin_version, [])


def _calculate_canvas_size(operations: list) -> tuple[int, int]:
    max_x = 0
    max_y = 0
    for crop_box, _, scale_factor, (px, py) in operations:
        w = int(crop_box[2] * scale_factor)
        h = int(crop_box[3] * scale_factor)
        max_x = max(max_x, px + w)
        max_y = max(max_y, py + h)
    return max_x, max_y


def _render_avatar_js(skin_img: Image.Image, avatar_type: str, target_size: int) -> Image.Image:
    original_size = skin_img.size
    skin_img = _preprocess_skin_image(skin_img)
    if skin_img.mode != "RGBA":
        skin_img = skin_img.convert("RGBA")

    if avatar_type in ("big-head", "big_head"):
        full_ops = _get_operations("full", original_size)
        canvas_w, canvas_h = _calculate_canvas_size(full_ops)
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        for crop_box, mirror, scale_factor, paste_pos in full_ops:
            part = _process_image(skin_img, crop_box, mirror, scale_factor)
            canvas.paste(part, paste_pos, part)

        big = canvas.resize((int(canvas_w * 1.4), int(canvas_h * 1.4)), Image.NEAREST)
        left = int(canvas_w * 0.2)
        canvas = big.crop((left, 0, left + canvas_w, canvas_h))
    else:
        operations = _get_operations(avatar_type, original_size)
        canvas_w, canvas_h = _calculate_canvas_size(operations)
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        for crop_box, mirror, scale_factor, paste_pos in operations:
            part = _process_image(skin_img, crop_box, mirror, scale_factor)
            canvas.paste(part, paste_pos, part)
    bbox = canvas.getbbox()
    if bbox:
        canvas = canvas.crop(bbox)
    if target_size != canvas.width or target_size != canvas.height:
        canvas = canvas.resize((target_size, target_size), Image.NEAREST)
    return canvas


def _cache_offline_avatar(uuid: str, skin_type: str, size: int, avatar_type: str = "head") -> None:
    cache_dir = _get_skin_cache_dir()
    filename = f"{uuid.lower()}-{skin_type}-{avatar_type}-{size}.png"
    file_path = cache_dir / filename

    if file_path.exists():
        return

    try:
        skin_path = _get_default_skin_path(skin_type)
        if not skin_path.exists():
            return

        with Image.open(skin_path) as skin_img:
            result = _render_avatar_js(skin_img, avatar_type, size)
            result.save(file_path, "PNG")
    except Exception as e:
        logger.warning(f"缓存离线头像失败 {uuid}: {e}")


def _get_cached_avatar(uuid: str, skin_path: Path, avatar_type: str, size: int) -> Path | None:
    cache_dir = _get_skin_cache_dir()
    cache_name = f"{uuid.lower()}-{skin_path.stem}-{avatar_type}-{size}.png"
    cache_path = cache_dir / cache_name
    return cache_path if cache_path.exists() else None


def _cache_online_avatar(uuid: str, skin_path: Path, avatar_type: str, size: int, result: Image.Image) -> None:
    try:
        cache_dir = _get_skin_cache_dir()
        cache_name = f"{uuid.lower()}-{skin_path.stem}-{avatar_type}-{size}.png"
        result.save(cache_dir / cache_name, "PNG")
    except Exception as e:
        logger.warning(f"缓存在线头像失败 {uuid}: {e}")


def _img_to_data_url(img_path: Path) -> str:
    with Image.open(img_path) as img:
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('utf-8')}"


def _build_skin_server_url(type_name: str, custom_server: str | None = None) -> str:
    type_clean = type_name.strip().lower()
    if type_clean in ("mojang", "ms", "microsoft"):
        return "https://sessionserver.mojang.com/session/minecraft/profile/"

    if type_clean == "nide":
        server = custom_server or os.environ.get("ECL_VERSION_SERVER_NIDE") or os.environ.get("ECL_NIDE_SERVER")
        if not server:
            raise ValueError("Nide 服务器地址未配置，请设置 ECL_VERSION_SERVER_NIDE 或 ECL_NIDE_SERVER")
        return f"https://auth.mc-user.com:233/{server.rstrip('/')}/sessionserver/session/minecraft/profile/"

    if type_clean == "auth":
        server = custom_server or os.environ.get("ECL_VERSION_SERVER_AUTH_SERVER") or os.environ.get("ECL_AUTH_SERVER")
        if not server:
            raise ValueError("Auth 服务器地址未配置，请设置 ECL_VERSION_SERVER_AUTH_SERVER 或 ECL_AUTH_SERVER")
        return f"{server.rstrip('/')}/sessionserver/session/minecraft/profile/"

    raise ValueError(f"皮肤地址种类无效：{type_name}")


def _fetch_profile_json(url: str, timeout: int = 10) -> dict[str, Any]:
    headers = {"User-Agent": "EuoraCraft Launcher", "Accept": "application/json"}
    logger.debug(f"请求皮肤URL: {url}")

    response = requests.get(url, timeout=timeout, headers=headers)
    if response.status_code == 204:
        logger.debug("用户不存在")
        raise ValueError("用户不存在或未设置皮肤")

    response.raise_for_status()
    content = response.text
    logger.debug(f"响应状态码: {response.status_code}")
    logger.debug(f"响应内容前200字符: {content[:200]}")

    try:
        data = response.json()
        if not data:
            raise ValueError("皮肤返回值为空，可能是未设置自定义皮肤的用户")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析失败: {e}")
        logger.error(f"完整响应内容: {content}")
        raise


def _parse_skin_url(profile_json: dict[str, Any]) -> str:
    properties = profile_json.get("properties")
    if not isinstance(properties, list):
        raise ValueError("皮肤返回值中不包含皮肤数据项，可能是未设置自定义皮肤的用户")

    texture_value = None
    for item in properties:
        if isinstance(item, dict) and item.get("name") == "textures":
            texture_value = item.get("value")
            break

    if not texture_value:
        raise ValueError("未从皮肤返回值中找到符合条件的 Property")

    try:
        decoded = base64.b64decode(texture_value)
        texture_json = json.loads(decoded.decode("utf-8"))
    except Exception as exc:
        raise ValueError("无法解析皮肤返回数据") from exc

    skin = texture_json.get("textures", {}).get("SKIN", {})
    skin_url = skin.get("url")
    if not skin_url:
        raise ValueError("用户未设置自定义皮肤")

    return skin_url.replace("http://", "https://") if "minecraft.net/" in skin_url else skin_url


def get_skin_address(uuid: str, type_name: str = "Mojang", custom_server: str | None = None) -> str:
    if not uuid:
        raise ValueError("UUID 为空。")

    if uuid.startswith("00000") and type_name.lower() != "auth":
        raise ValueError(f"离线 UUID 无正版皮肤文件：{uuid}")

    cached = _get_cached_skin_address(uuid, type_name)
    if cached:
        return cached

    server_url = _build_skin_server_url(type_name, custom_server)
    profile_json = _fetch_profile_json(f"{server_url}{uuid}")
    skin_url = _parse_skin_url(profile_json)
    _cache_skin_address(uuid, type_name, skin_url)
    return skin_url


def download_skin(address: str) -> Path:
    if not address:
        raise ValueError("皮肤地址不能为空")

    cache_dir = _get_skin_cache_dir()
    filename = f"{hashlib.md5(address.encode('utf-8')).hexdigest()}.png"
    file_path = cache_dir / filename
    tmp_path = cache_dir / (filename + ".tmp")

    with _SKIN_DOWNLOAD_LOCK:
        if file_path.exists():
            return file_path

        headers = {"User-Agent": "EuoraCraft Launcher"}
        with requests.get(address, stream=True, timeout=15, headers=headers) as response:
            response.raise_for_status()

            file_path.parent.mkdir(parents=True, exist_ok=True)
            with tmp_path.open("wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        tmp_path.replace(file_path)
        return file_path


def get_skin_sex(uuid: str) -> str:
    normalized = uuid.replace("-", "")
    if len(normalized) != 32:
        return "Steve"

    try:
        values = [int(normalized[i], 16) for i in (7, 15, 23, 31)]
    except ValueError:
        return "Steve"

    return "Alex" if (values[0] ^ values[1] ^ values[2] ^ values[3]) % 2 else "Steve"


def get_avatar_data_url(
    uuid: str,
    type_name: str = "Mojang",
    custom_server: str | None = None,
    size: int = 64,
    use_default_skin: bool = False,
    avatar_type: str = "head",
) -> str:

    if not uuid:
        raise ValueError("UUID 为空")

    logger.debug(
        f"获取头像参数: uuid={uuid}, type_name={type_name}, avatar_type={avatar_type}, use_default_skin={use_default_skin}"
    )
    if use_default_skin:
        skin_type = get_skin_sex(uuid)
        skin_path = _get_default_skin_path(skin_type)
        logger.debug(f"强制使用默认皮肤路径: {skin_path}")
        if not skin_path.exists():
            raise FileNotFoundError(f"默认皮肤文件不存在: {skin_path}")
        _cache_offline_avatar(uuid, skin_type, size, avatar_type)
        logger.debug(f"强制使用默认皮肤: {uuid} -> {skin_type}")
    elif type_name.lower() in ("mojang", "ms", "microsoft"):
        logger.debug(f"尝试API获取正版用户皮肤: {uuid}")
        try:
            skin_url = get_skin_address(uuid, type_name, custom_server)
            skin_path = download_skin(skin_url)
            logger.debug(f"成功获取正版用户在线皮肤: {uuid}")

            # 检查渲染缓存
            cached = _get_cached_avatar(uuid, skin_path, avatar_type, size)
            if cached:
                logger.debug(f"命中在线皮肤渲染缓存: {cached}")
                return _img_to_data_url(cached)
        except Exception as e:
            logger.warning(f"获取正版用户皮肤失败 {uuid}: {e}，使用默认皮肤")
            skin_type = get_skin_sex(uuid)
            skin_path = _get_default_skin_path(skin_type)
            if not skin_path.exists():
                raise FileNotFoundError(f"默认皮肤文件不存在: {skin_path}") from e
            _cache_offline_avatar(uuid, skin_type, size, avatar_type)
    else:
        skin_type = get_skin_sex(uuid)
        skin_path = _get_default_skin_path(skin_type)
        logger.debug(f"非Mojang服务器使用默认皮肤路径: {skin_path}")
        if not skin_path.exists():
            raise FileNotFoundError(f"默认皮肤文件不存在: {skin_path}")
        _cache_offline_avatar(uuid, skin_type, size, avatar_type)
        logger.debug(f"非Mojang服务器使用默认皮肤: {uuid} -> {skin_type}")

    with Image.open(skin_path) as skin_img:
        result = _render_avatar_js(skin_img, avatar_type, size)

        # 在线皮肤缓存渲染结果
        if not use_default_skin and type_name.lower() in ("mojang", "ms", "microsoft"):
            _cache_online_avatar(uuid, skin_path, avatar_type, size, result)

        buffer = BytesIO()
        result.save(buffer, format="PNG")
        img_data = base64.b64encode(buffer.getvalue()).decode("utf-8")

        return f"data:image/png;base64,{img_data}"
