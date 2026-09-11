from __future__ import annotations

from pathlib import Path

import pytest

from ECL.services.game.base import GameServiceError
from ECL.services.game.schematics import SchematicCoordinator, _block_color
from ECL.services.game.workspace import WorkspaceCoordinator
from ECL.utils.nbt import ByteArray, Compound, File, Int, IntArray, List, LongArray, String


class _SchematicHarness(SchematicCoordinator, WorkspaceCoordinator):
    def __init__(self, data_path: Path) -> None:
        self._data_path = data_path

    def list_instances(self) -> list[dict[str, object]]:
        return []


def _schematic_root(tmp_path: Path) -> Path:
    root = tmp_path / "versions" / "iso" / "schematics"
    root.mkdir(parents=True)
    return root


def _write_litematic(path: Path, width: int = 4, height: int = 3, length: int = 3) -> None:
    # BlockStatePalette 有 3 个方块（air/dirt/stone），MC 调色板位宽最小为 4。
    entries = [
        Compound({"Name": String("minecraft:air")}),
        Compound({"Name": String("minecraft:dirt")}),
        Compound({"Name": String("minecraft:stone")}),
    ]
    per_word = 64 // 4
    total = width * height * length
    words = [0] * ((total + per_word - 1) // per_word)

    def set_index(index: int, palette_id: int) -> None:
        word_index = index // per_word
        offset = (index % per_word) * 4
        words[word_index] |= palette_id << offset

    # x 最内层；把 (0,0,0) 设为 dirt、(1,0,0) 设为 stone，其余默认为 air。
    set_index(0, 1)
    set_index(1, 2)
    region = Compound(
        {
            "Size": IntArray([width, height, length]),
            "Position": IntArray([1, 2, 3]),
            "BlockStatePalette": List(entries),
            "BlockStates": LongArray(words),
        }
    )
    document = File({"Regions": Compound({"main": region})}, gzipped=True)
    document.save(path, gzipped=True)


def _write_schem(path: Path) -> None:
    palette = Compound(
        {
            "minecraft:air": Int(0),
            "minecraft:grass_block": Int(1),
            "minecraft:stone": Int(2),
        }
    )
    # Sponge 索引 = (y * length + z) * width + x；size[2,2,1] 共 4 格。
    blocks = ByteArray(bytes([1, 0, 2, 0]))
    document = File(
        {
            "Version": Int(2),
            "DataVersion": Int(2586),
            "Width": Int(2),
            "Height": Int(2),
            "Length": Int(1),
            "Size": IntArray([2, 2, 1]),
            "Palette": palette,
            "Blocks": blocks,
        },
        gzipped=True,
    )
    document.save(path, gzipped=True)


def test_block_color_resolves_base_name_and_falls_back() -> None:
    assert _block_color("minecraft:stone") == (124, 124, 124)
    assert _block_color("minecraft:oak_log[axis=y]") == (94, 74, 44)
    assert _block_color("minecraft:air") == (0, 0, 0)


def test_schematic_preview_rejects_missing_file(tmp_path: Path) -> None:
    _schematic_root(tmp_path)
    harness = _SchematicHarness(tmp_path / "app-data")
    with pytest.raises(GameServiceError) as raised:
        harness.schematic_preview(tmp_path, "iso", "nonexistent.schem", True)
    # 路径解析统一复用资源层语义，缺失文件归入资源未找到。
    assert raised.value.error_code == "RESOURCE_NOT_FOUND"


def test_schematic_preview_invalid_content_fails_gracefully(tmp_path: Path) -> None:
    root = _schematic_root(tmp_path)
    (root / "bad.schem").write_bytes(b"not-a-schematic")
    harness = _SchematicHarness(tmp_path / "app-data")
    with pytest.raises(GameServiceError) as raised:
        harness.schematic_preview(tmp_path, "iso", "bad.schem", True)
    assert raised.value.error_code == "SCHEMATIC_INVALID"


def test_litematic_preview_returns_palette_and_regions(tmp_path: Path) -> None:
    _write_litematic(_schematic_root(tmp_path) / "build.litematic")
    harness = _SchematicHarness(tmp_path / "app-data")

    result = harness.schematic_preview(tmp_path, "iso", "build.litematic", True)

    assert result["type"] == "litematic"
    assert result["size"] == [5, 5, 6]  # position [1,2,3] + size [4,3,3]
    region = result["regions"][0]
    assert region["name"] == "main"
    assert region["size"] == [4, 3, 3]
    assert region["position"] == [1, 2, 3]
    assert region["palette"] == [(0, 0, 0), (124, 94, 70), (124, 124, 124)]
    assert len(region["indices"]) == 36
    assert region["indices"][0] == 1
    assert region["indices"][1] == 2


def test_schem_preview_parses_sponge_layout(tmp_path: Path) -> None:
    _write_schem(_schematic_root(tmp_path) / "build.schem")
    harness = _SchematicHarness(tmp_path / "app-data")

    result = harness.schematic_preview(tmp_path, "iso", "build.schem", True)

    assert result["type"] == "schem"
    assert result["size"] == [2, 2, 1]
    region = result["regions"][0]
    assert region["size"] == [2, 2, 1]
    assert len(region["indices"]) == 4
    assert region["indices"][0] == 1  # grass_block
    assert region["indices"][2] == 2  # stone


def test_downsample_caps_voxel_count(tmp_path: Path) -> None:
    harness = _SchematicHarness(tmp_path / "app-data")
    huge = {
        "name": "big",
        "size": [128, 128, 128],
        "position": [0, 0, 0],
        "indices": [0] * (128 * 128 * 128),
        "palette": [(10, 10, 10)],
        "maskBits": 4,
    }
    sampled = harness._downsample_region(huge)
    assert sampled["size"][0] <= 64
    assert len(sampled["indices"]) <= 262144
