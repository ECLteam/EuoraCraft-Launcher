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

import gzip
from pathlib import Path
from typing import Any

from ECL.utils.nbt import Compound, IntArray, List, load

from .base import GameServiceError
from .resources import RESOURCE_DIRECTORIES
from .workspace import resolve_relative_id

# 面向 3D 预览返回的体素上限，超出部分按轴向均匀降采样以保证载荷与渲染可控。
_MAX_VOXELS = 262144
# 每个方向允许的独立轴长上限；超出视为文件异常。
_MAX_AXIS = 1024
# 内置调色板之外的块使用统一的占位色，避免每个未知块配色不一致。
_UNKNOWN_COLOR = (140, 140, 140)

# 常用方块的近似显示色（R, G, B）。用于原理图体素着色的静态近似表，
# 不追求与原版材质逐像素一致，仅保证预览可辨认主要结构。
_BLOCK_COLORS: dict[str, tuple[int, int, int]] = {
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
        color = _BLOCK_COLORS.get(candidate)
        if color is not None:
            return color
        for key, value in _BLOCK_COLORS.items():
            if candidate.startswith(key):
                return value
    return _UNKNOWN_COLOR


def _normalize(index: int, size: int, axis: int) -> int:
    # 将待降采样坐标映射回目标轴长内的采样坐标（对应步长对齐）。
    if size <= 1:
        return 0
    return min(index * axis // size, axis - 1)


class LitematicaRegion:
    __slots__ = ("block_colors", "indices", "mask_bits", "name", "position", "size")

    def __init__(self, name: str, region: Compound) -> None:
        self.name = name
        self.size = [int(v) for v in (region.get("Size") or [1, 1, 1])]
        self.position = [int(v) for v in (region.get("Position") or [0, 0, 0])]
        palette_tag = region.get("BlockStatePalette") or List()
        self.block_colors = [
            _block_color(str(item.get("Name") or "air")) for item in palette_tag if isinstance(item, dict)
        ]
        # Minecraft 调色板位宽最小为 4，超过位宽后再按调色板大小进位，保证与 BlockStates 编码一致。
        self.mask_bits = max(4, (max(1, len(self.block_colors)) - 1).bit_length())
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
                "palette": region_obj.block_colors,
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
    color_map = [_block_color("air")] * (len(palette) + 1)
    for key, value in palette.items():
        color_map[int(value)] = _block_color(str(key))
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

    def _schematic_root(self, game_path: Any, version_id: Any, resource_id: Any, version_isolation: Any) -> Path:
        target = self.resolve_instance(game_path, version_id, version_isolation)
        root = target.data_path / RESOURCE_DIRECTORIES["schematic"]
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
        # 体素总量超过上限时沿各轴均匀降采样，仍需保证每轴不长于 _MAX_AXIS。
        size = region["size"]
        sx, sy, sz = size[0], size[1], size[2]
        if sx <= 0 or sy <= 0 or sz <= 0:
            raise GameServiceError("原理图区域尺寸非法", "SCHEMATIC_INVALID")
        scale_x = max(1, (sx + _MAX_AXIS - 1) // _MAX_AXIS)
        scale_y = max(1, (sy + _MAX_AXIS - 1) // _MAX_AXIS)
        scale_z = max(1, (sz + _MAX_AXIS - 1) // _MAX_AXIS)
        while sx * sy * sz // (scale_x * scale_y * scale_z) > _MAX_VOXELS:
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
