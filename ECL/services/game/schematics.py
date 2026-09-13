# ============================================================
# EuoraCraft Launcher
# ECLTeam © 2026 GPL-3.0 License
# https://github.com/ECLTeam/EuoraCraft-Launcher
#
# 文件作用：原理图服务：litematic/schem 解析为体素预览数据。
#
# 公开接口：
#   - class LitematicaRegion
#   - class SchematicCoordinator — 解析原理图文件为适合 3D 预览的体素模型数据。
#       - schematic_preview(game_path, version_id, resource_id, version_isolation=…) -> dict[str, Any] — 读取并解析指定原理图，返回体素模型数据供前端渲染。
# ============================================================

from __future__ import annotations

import base64
import gzip
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

from ECL.utils import atomic_write_text
from ECL.utils.nbt import Compound, IntArray, List, load

from .base import GameServiceError
from .resources import ResourceCatalogPolicy
from .workspace import resolve_relative_id


class SchematicPalette:
    """
    原理图预览的内置方块调色板。

    颜色为可辨认主要结构的近似值，不追求与原版材质逐像素一致。
    """

    unknown_color = (140, 140, 140)
    block_colors: dict[str, tuple[int, int, int]] = {
        "air": (0, 0, 0),
        "cave_air": (0, 0, 0),
        "void_air": (0, 0, 0),
        "stone": (124, 124, 124),
        "cobblestone": (128, 128, 136),
        "gravel": (136, 124, 118),
        "dirt": (124, 94, 70),
        "grass_block": (86, 148, 74),
        "sand": (219, 211, 164),
        "sandstone": (212, 199, 146),
        "red_sand": (192, 130, 74),
        "clay": (156, 168, 182),
        "granite": (148, 118, 108),
        "diorite": (178, 178, 178),
        "andesite": (140, 140, 140),
        "deepslate": (75, 73, 78),
        "bedrock": (62, 60, 60),
        "water": (54, 101, 210),
        "lava": (214, 108, 36),
        "obsidian": (24, 16, 32),
        "snow_block": (238, 240, 242),
        "ice": (150, 194, 230),
        "packed_ice": (139, 168, 190),
        "coal_ore": (110, 110, 110),
        "iron_ore": (142, 120, 104),
        "gold_ore": (150, 140, 70),
        "diamond_ore": (128, 200, 196),
        "emerald_ore": (90, 190, 128),
        "redstone_ore": (150, 70, 70),
        "lapis_ore": (70, 100, 190),
        "iron_block": (212, 212, 216),
        "gold_block": (246, 198, 62),
        "diamond_block": (104, 224, 214),
        "emerald_block": (64, 202, 118),
        "redstone_block": (168, 42, 34),
        "lapis_block": (50, 84, 200),
        "coal_block": (46, 46, 48),
        "oak_log": (94, 74, 44),
        "spruce_log": (62, 46, 32),
        "birch_log": (208, 196, 164),
        "jungle_log": (94, 76, 40),
        "acacia_log": (106, 66, 44),
        "dark_oak_log": (54, 42, 30),
        "oak_planks": (178, 148, 96),
        "spruce_planks": (140, 112, 76),
        "birch_planks": (206, 192, 156),
        "jungle_planks": (150, 114, 74),
        "acacia_planks": (176, 132, 76),
        "dark_oak_planks": (104, 82, 54),
        "oak_leaves": (74, 128, 62),
        "spruce_leaves": (54, 104, 54),
        "birch_leaves": (118, 158, 80),
        "jungle_leaves": (78, 122, 66),
        "acacia_leaves": (120, 148, 86),
        "dark_oak_leaves": (58, 94, 52),
        "glass": (190, 216, 218),
        "stained_glass_white": (190, 216, 218),
        "glass_pane": (190, 216, 218),
        "smooth_stone": (150, 150, 152),
        "bricks": (152, 92, 82),
        "stone_bricks": (130, 130, 134),
        "mossy_stone_bricks": (116, 130, 106),
        "cracked_stone_bricks": (116, 114, 118),
        "netherrack": (96, 46, 44),
        "nether_bricks": (54, 32, 36),
        "netherite_block": (70, 66, 74),
        "soul_sand": (78, 62, 54),
        "end_stone": (214, 216, 160),
        "purpur_block": (168, 128, 168),
        "magma_block": (140, 84, 40),
        "sea_lantern": (206, 220, 214),
        "wool_white": (216, 216, 216),
        "wool_orange": (226, 126, 38),
        "wool_magenta": (178, 76, 216),
        "wool_light_blue": (102, 153, 216),
        "wool_yellow": (226, 214, 40),
        "wool_lime": (94, 180, 42),
        "wool_pink": (216, 130, 152),
        "wool_gray": (76, 76, 76),
        "wool_light_gray": (158, 156, 158),
        "wool_cyan": (40, 128, 152),
        "wool_purple": (126, 60, 180),
        "wool_blue": (52, 66, 172),
        "wool_brown": (90, 62, 40),
        "wool_green": (66, 124, 52),
        "wool_red": (162, 44, 42),
        "wool_black": (26, 22, 22),
        "terracotta": (150, 90, 56),
        "white_terracotta": (208, 174, 133),
        "orange_terracotta": (156, 88, 44),
        "red_terracotta": (146, 60, 42),
        "cyan_terracotta": (82, 104, 106),
        "light_blue_terracotta": (106, 128, 146),
        "lime_terracotta": (104, 118, 66),
        "pink_terracotta": (144, 96, 106),
        "gray_terracotta": (76, 68, 64),
        "light_gray_terracotta": (132, 122, 110),
        "magenta_terracotta": (142, 70, 108),
        "yellow_terracotta": (164, 126, 62),
        "blue_terracotta": (72, 82, 132),
        "brown_terracotta": (86, 60, 42),
        "green_terracotta": (78, 96, 62),
        "purple_terracotta": (112, 66, 108),
        "black_terracotta": (58, 36, 34),
        "mud": (134, 112, 84),
        "mud_bricks": (136, 112, 78),
        "cut_copper": (178, 100, 106),
        "exposed_cut_copper": (150, 122, 112),
        "weathered_cut_copper": (108, 136, 118),
        "oxidized_cut_copper": (80, 132, 118),
        "waxed_cut_copper": (178, 100, 106),
    }


def _block_color(name: str) -> tuple[int, int, int]:
    # 去掉命名空间、属性和方块状态后缀，逐级回退匹配基础方块名。
    base = name.split(":", 1)[-1]
    for candidate in (base, base.split("[", 1)[0]):
        color = SchematicPalette.block_colors.get(candidate)
        if color is not None:
            return color
        for key, value in SchematicPalette.block_colors.items():
            if candidate.startswith(key):
                return value
    return SchematicPalette.unknown_color


def _normalize(index: int, size: int, axis: int) -> int:
    # 将待降采样坐标映射回目标轴长内的采样坐标（对应步长对齐）。
    if size <= 1:
        return 0
    return min(index * axis // size, axis - 1)


def _read_litematica_vector(value: Any, field_name: str) -> list[int]:
    """
    读取 Litematica 的三维 NBT 坐标，并兼容旧的三元素数组表示。

    标准 Litematica 把 ``Size`` 与 ``Position`` 编码为含 ``x/y/z`` 的复合标签；
    历史测试数据和少数第三方导出则可能使用整数数组。解析失败统一转换为领域错误，
    避免底层 ``ValueError`` 直接暴露到 IPC 边界。

    :param value: NBT 标签中的坐标值
    :param field_name: 用于错误信息的字段名
    :return: 按 x、y、z 顺序排列的三个整数
    :raises GameServiceError: 坐标字段缺失、维度不完整或包含非整数值时抛出
    """
    if isinstance(value, Mapping):
        try:
            coordinates = [value[axis] for axis in ("x", "y", "z")]
        except KeyError as exc:
            raise GameServiceError(f"原理图 {field_name} 坐标不完整", "SCHEMATIC_INVALID") from exc
    elif isinstance(value, (list, tuple)):
        coordinates = list(value)
    else:
        raise GameServiceError(f"原理图 {field_name} 坐标格式无效", "SCHEMATIC_INVALID")
    if len(coordinates) != 3 or any(isinstance(item, bool) or not isinstance(item, int) for item in coordinates):
        raise GameServiceError(f"原理图 {field_name} 坐标格式无效", "SCHEMATIC_INVALID")
    return [int(item) for item in coordinates]


def _block_palette_entry(value: Any) -> dict[str, Any]:
    """
    将 NBT 方块状态转换为前端纹理渲染所需的稳定色板条目。

    :param value: ``BlockStatePalette`` 中的单个复合标签
    :return: 包含方块标识、状态属性和颜色回退值的字典
    """
    entry = value if isinstance(value, Mapping) else {}
    name = str(entry.get("Name") or "minecraft:air")
    properties_tag = entry.get("Properties")
    properties = (
        {str(key): str(item) for key, item in properties_tag.items()}
        if isinstance(properties_tag, Mapping)
        else {}
    )
    return {"name": name, "properties": properties, "color": list(_block_color(name))}


class LitematicaRegion:
    __slots__ = ("block_palette", "indices", "mask_bits", "name", "position", "size")

    def __init__(self, name: str, region: Compound) -> None:
        self.name = name
        raw_size = _read_litematica_vector(region.get("Size"), "Size")
        raw_position = _read_litematica_vector(region.get("Position"), "Position")
        if any(axis == 0 for axis in raw_size):
            raise GameServiceError("原理图区域尺寸不能为零", "SCHEMATIC_INVALID")
        self.size = [abs(axis) for axis in raw_size]
        # 负尺寸表示区域从 Position 向负轴延伸；预览坐标使用该区域的实际最小边界。
        self.position = [
            position if size > 0 else position + size + 1 for position, size in zip(raw_position, raw_size, strict=True)
        ]
        palette_tag = region.get("BlockStatePalette") or List()
        self.block_palette = [_block_palette_entry(item) for item in palette_tag]
        # Minecraft 调色板位宽最小为 4，超过位宽后再按调色板大小进位，保证与 BlockStates 编码一致。
        self.mask_bits = max(4, (max(1, len(self.block_palette)) - 1).bit_length())
        self.indices = self._decode_indices(region.get("BlockStates") or IntArray())

    def _decode_indices(self, storage: IntArray) -> list[int]:
        # 依据 litematic BlockStates 的紧凑位数组解码每个方块对应的调色板索引。
        bits = self.mask_bits
        per_word = 64 // bits
        mask = (1 << bits) - 1
        total = self.size[0] * self.size[1] * self.size[2]
        result: list[int] = []
        for position_index in range(total):
            word_index = position_index // per_word
            offset = (position_index % per_word) * bits
            word = storage[word_index] if word_index < len(storage) else 0
            result.append((word >> offset) & mask)
        return result


def _decode_litematic(root: Compound) -> list[dict[str, Any]]:
    # 遍历 litematic Regions 下的全部区域，解析为统一的结构化体素块。
    regions = root.get("Regions") or Compound()
    result: list[dict[str, Any]] = []
    for name, region in regions.items():
        if not isinstance(region, dict):
            continue
        region_obj = LitematicaRegion(str(name or f"region{len(result)}"), region)
        if region_obj.size[0] <= 0 or region_obj.size[1] <= 0 or region_obj.size[2] <= 0:
            continue
        result.append(
            {
                "name": region_obj.name,
                "size": region_obj.size,
                "position": region_obj.position,
                "indices": region_obj.indices,
                "maskBits": region_obj.mask_bits,
                "palette": region_obj.block_palette,
            }
        )
    return result


def _decode_schematic(root: Compound, size_tag, blocks_tag) -> dict[str, Any]:
    # 解析 Sponge 格式 .schem：Palette 映射块名->索引，Blocks 为 z 优先坐标的联合数组。
    size = [int(v) for v in size_tag] if size_tag else []
    blocks = list(blocks_tag) if blocks_tag is not None else []
    if not size or len(size) != 3 or not blocks:
        raise GameServiceError("原理图缺少尺寸或方块数据", "SCHEMATIC_INVALID")
    palette = root.get("Palette") or Compound()
    color_map: list[dict[str, Any]] = [_block_palette_entry({"Name": "minecraft:air"})] * (len(palette) + 1)
    for key, value in palette.items():
        color_map[int(value)] = _block_palette_entry({"Name": str(key)})
    indices = [0] * len(blocks)
    for index, value in enumerate(blocks):
        indices[index] = int(value)
    return {"size": size, "indices": indices, "palette": color_map}


class SchematicCoordinator:
    """
    解析原理图文件为适合 3D 预览的体素模型数据。

    支持 Litematica（.litematic）与 Sponge（.schem）两种主流格式，
    输出尺寸、调色板颜色与沿坐标轴排列的方块索引数组。
    """

    max_voxels = 262144
    max_axis = 1024
    max_asset_blocks = 512
    max_asset_bytes = 24 * 1024 * 1024

    def _schematic_root(self, game_path: Any, version_id: Any, resource_id: Any, version_isolation: Any) -> Path:
        target = self.resolve_instance(game_path, version_id, version_isolation)
        root = target.data_path / ResourceCatalogPolicy.directories["schematic"]
        return resolve_relative_id(root, resource_id)

    def schematic_preview(
        self,
        game_path: Any,
        version_id: Any,
        resource_id: Any,
        version_isolation: Any = False,
    ) -> dict[str, Any]:
        """
        读取并解析指定原理图，返回体素模型数据供前端渲染。

        :return: 包含 type/size/regions（名称、尺寸、位置、色板）的字典
        """
        path = self._schematic_root(game_path, version_id, resource_id, version_isolation)
        if not path.is_file():
            raise GameServiceError("原理图文件不存在", "SCHEMATIC_NOT_FOUND")
        try:
            root = load(path)
        except (OSError, ValueError, gzip.BadGzipFile) as exc:
            raise GameServiceError("原理图解析失败或格式不受支持", "SCHEMATIC_INVALID") from exc
        if "Regions" in root:
            regions = _decode_litematic(root)
            if not regions:
                raise GameServiceError("原理图中没有可解析的区域", "SCHEMATIC_EMPTY")
            return {
                "type": "litematic",
                "size": self._bounding_size(regions),
                "regions": [self._downsample_region(region) for region in regions],
            }
        if "Palette" in root or "Blocks" in root:
            payload = _decode_schematic(root, root.get("Size"), root.get("Blocks"))
            return {
                "type": "schem",
                "size": payload["size"],
                "regions": [
                    {
                        "name": "schem",
                        "size": payload["size"],
                        "position": [0, 0, 0],
                        "palette": payload["palette"],
                        "indices": payload["indices"],
                    }
                ],
            }
        raise GameServiceError("无法识别的原理图格式", "SCHEMATIC_INVALID")

    def schematic_assets(
        self, game_path: Any, version_id: Any, blocks: list[str], version_isolation: Any = False
    ) -> dict[str, Any]:
        """
        从用户本机游戏 Jar 按需读取原理图涉及的原版方块资源。

        提取结果仅包含请求色板使用的 blockstate、模型闭包和 PNG 纹理，并缓存到
        启动器数据目录；不会随程序分发或写入游戏目录。无法解析的模组方块会列入
        ``missingBlocks``，由前端使用回退渲染。

        :param game_path: Minecraft 根目录
        :param version_id: 当前实例版本标识
        :param blocks: 原理图调色板中的方块命名空间标识
        :param version_isolation: 实例隔离状态
        :return: 可直接传给 WebGL 渲染器的资源包
        :raises GameServiceError: 版本资源不存在、请求非法或 Jar 损坏时抛出
        """
        requested = self._normalize_asset_blocks(blocks)
        target = self.resolve_instance(game_path, version_id, version_isolation)
        jar_path = self._resolve_asset_jar(target.game_path, target.version_id)
        cache_path = self._asset_cache_path(jar_path, requested)
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = None
        if isinstance(cached, dict):
            return cached
        bundle = self._extract_assets(jar_path, requested)
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(cache_path, json.dumps(bundle, ensure_ascii=False, separators=(",", ":")))
        except OSError:
            self.logger.warning("原理图资源缓存写入失败，将在下次预览重新提取")
        return bundle

    def _normalize_asset_blocks(self, blocks: list[str]) -> list[str]:
        """
        校验方块资源标识，阻止调用方构造 Jar 内路径穿越。

        :param blocks: 前端提供的方块标识列表
        :return: 去重、排序后的合法标识列表
        :raises GameServiceError: 标识数量或格式不符合约束时抛出
        """
        if len(blocks) > self.max_asset_blocks:
            raise GameServiceError("原理图方块类型过多", "SCHEMATIC_ASSETS_TOO_LARGE")
        normalized: set[str] = set()
        for block in blocks:
            if not isinstance(block, str) or ":" not in block:
                raise GameServiceError("原理图方块标识无效", "SCHEMATIC_ASSETS_INVALID")
            namespace, name = block.split(":", 1)
            if not namespace.replace("_", "").replace("-", "").isalnum() or not name or any(
                part in {"", ".", ".."} for part in name.split("/")
            ):
                raise GameServiceError("原理图方块标识无效", "SCHEMATIC_ASSETS_INVALID")
            normalized.add(f"{namespace}:{name}")
        if not normalized:
            raise GameServiceError("原理图没有可渲染方块", "SCHEMATIC_ASSETS_INVALID")
        return sorted(normalized)

    def _resolve_asset_jar(self, game_path: Path, version_id: str) -> Path:
        """
        沿版本继承链定位携带原版资源的客户端 Jar。

        :param game_path: Minecraft 根目录
        :param version_id: 起始版本标识
        :return: 可读取 ``assets/minecraft`` 的 Jar 路径
        :raises GameServiceError: 找不到 Jar 或继承链损坏时抛出
        """
        current = version_id
        visited: set[str] = set()
        for _ in range(16):
            if current in visited:
                break
            visited.add(current)
            version_dir = game_path / "versions" / current
            jar_path = version_dir / f"{current}.jar"
            if jar_path.is_file():
                return jar_path
            try:
                version_json = json.loads((version_dir / f"{current}.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                break
            parent = version_json.get("inheritsFrom") if isinstance(version_json, dict) else None
            if not isinstance(parent, str) or not parent:
                break
            current = parent
        raise GameServiceError("未找到当前版本的游戏资源 Jar，请先完成游戏安装", "SCHEMATIC_ASSETS_NOT_FOUND")

    def _asset_cache_path(self, jar_path: Path, blocks: list[str]) -> Path:
        stat = jar_path.stat()
        digest = hashlib.sha256(f"{jar_path}:{stat.st_mtime_ns}:{stat.st_size}:{','.join(blocks)}".encode()).hexdigest()
        return self._data_path / "schematic-assets" / f"{digest}.json"

    def _extract_assets(self, jar_path: Path, blocks: list[str]) -> dict[str, Any]:
        """读取 Jar 中的 JSON 与 PNG 资源，并限制总输出体积。"""
        blockstates: dict[str, Any] = {}
        models: dict[str, Any] = {}
        textures: dict[str, str] = {}
        missing: set[str] = set()
        pending_models: set[str] = set()
        pending_textures: set[str] = set()
        total_bytes = 0
        try:
            with ZipFile(jar_path) as archive:
                for block in blocks:
                    namespace, name = block.split(":", 1)
                    payload = self._read_json_asset(archive, namespace, f"blockstates/{name}.json")
                    if payload is None:
                        missing.add(block)
                        continue
                    blockstates[block] = payload
                    pending_models.update(self._json_references(payload, "model", namespace))
                while pending_models:
                    model = pending_models.pop()
                    if model in models:
                        continue
                    namespace, name = model.split(":", 1)
                    payload = self._read_json_asset(archive, namespace, f"models/{name}.json")
                    if payload is None:
                        continue
                    models[model] = payload
                    pending_models.update(self._json_references(payload, "parent", namespace))
                    pending_textures.update(self._json_references(payload, "texture", namespace))
                for texture in pending_textures:
                    namespace, name = texture.split(":", 1)
                    try:
                        data = archive.read(f"assets/{namespace}/textures/{name}.png")
                    except KeyError:
                        continue
                    total_bytes += len(data)
                    if total_bytes > self.max_asset_bytes:
                        raise GameServiceError("原理图纹理资源过大", "SCHEMATIC_ASSETS_TOO_LARGE")
                    textures[texture] = base64.b64encode(data).decode("ascii")
        except (BadZipFile, OSError) as exc:
            raise GameServiceError("游戏资源 Jar 无法读取", "SCHEMATIC_ASSETS_INVALID") from exc
        return {
            "blockstates": blockstates,
            "models": models,
            "textures": textures,
            "missingBlocks": sorted(missing),
        }

    @staticmethod
    def _read_json_asset(archive: ZipFile, namespace: str, path: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(archive.read(f"assets/{namespace}/{path}").decode("utf-8"))
        except (KeyError, UnicodeDecodeError, ValueError):
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _json_references(value: Any, key: str, namespace: str) -> set[str]:
        references: set[str] = set()
        if isinstance(value, dict):
            for item_key, item in value.items():
                if item_key == key and isinstance(item, str) and not item.startswith("#"):
                    references.add(item if ":" in item else f"{namespace}:{item}")
                elif key == "texture" and item_key == "textures" and isinstance(item, dict):
                    for texture in item.values():
                        if isinstance(texture, str) and not texture.startswith("#"):
                            references.add(texture if ":" in texture else f"{namespace}:{texture}")
                else:
                    references.update(SchematicCoordinator._json_references(item, key, namespace))
        elif isinstance(value, list):
            for item in value:
                references.update(SchematicCoordinator._json_references(item, key, namespace))
        return references

    @staticmethod
    def _bounding_size(regions: list[dict[str, Any]]) -> list[int]:
        # 计算包含全部区域的位置关系的整体包围尺寸。
        max_x = max_y = max_z = 0
        for region in regions:
            position = region.get("position") or [0, 0, 0]
            size = region.get("size") or [0, 0, 0]
            max_x = max(max_x, position[0] + size[0])
            max_y = max(max_y, position[1] + size[1])
            max_z = max(max_z, position[2] + size[2])
        return [max(1, max_x), max(1, max_y), max(1, max_z)]

    def _downsample_region(self, region: dict[str, Any]) -> dict[str, Any]:
        # 体素总量超过上限时沿各轴均匀降采样，仍需保证每轴不长于 max_axis。
        size = region["size"]
        sx, sy, sz = size[0], size[1], size[2]
        if sx <= 0 or sy <= 0 or sz <= 0:
            raise GameServiceError("原理图区域尺寸非法", "SCHEMATIC_INVALID")
        scale_x = max(1, (sx + self.max_axis - 1) // self.max_axis)
        scale_y = max(1, (sy + self.max_axis - 1) // self.max_axis)
        scale_z = max(1, (sz + self.max_axis - 1) // self.max_axis)
        while sx * sy * sz // (scale_x * scale_y * scale_z) > self.max_voxels:
            if scale_x >= scale_y and scale_x >= scale_z:
                scale_x += 1
            elif scale_y >= scale_z:
                scale_y += 1
            else:
                scale_z += 1
        # 当降采样因子超过 1 时，线性取步进位置的索引，避免连接临近体素产生非线性形变。
        step_x, step_y, step_z = scale_x, scale_y, scale_z
        ax = (sx + scale_x - 1) // scale_x
        ay = (sy + scale_y - 1) // scale_y
        az = (sz + scale_z - 1) // scale_z
        indices = region["indices"]
        sampled: list[int] = []
        for z in range(0, sz, step_z):
            for y in range(0, sy, step_y):
                for x in range(0, sx, step_x):
                    index = (y * sz + z) * sx + x
                    sampled.append(indices[index])
        result_region = {
            "name": region["name"],
            "size": [ax, ay, az],
            "position": region["position"],
            "palette": region["palette"],
            "indices": sampled,
        }
        return result_region
