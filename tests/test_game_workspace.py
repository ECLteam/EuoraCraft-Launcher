from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from ECL.services.game.base import GameServiceError
from ECL.services.game.workspace import (
    WorkspaceCoordinator,
    resolve_instance_target,
    resolve_relative_id,
    safe_extract_zip,
)
from ECL.services.game.worlds import WorldCoordinator
from ECL.utils.nbt import Byte, Compound, File, Int, Long, String, load


def test_resolve_instance_target_matches_current_isolation_semantics(tmp_path: Path) -> None:
    shared = resolve_instance_target(tmp_path, "1.21.8", True)
    isolated = resolve_instance_target(tmp_path, "1.21.8", False)

    assert shared.data_path == tmp_path / "versions"
    assert isolated.data_path == tmp_path / "versions" / "1.21.8"


@pytest.mark.parametrize("relative_id", ["../secret", "/absolute", "a/../../b", ""])
def test_resolve_relative_id_rejects_escape(tmp_path: Path, relative_id: str) -> None:
    with pytest.raises(GameServiceError, match="资源 ID"):
        resolve_relative_id(tmp_path, relative_id, must_exist=False)


def test_safe_extract_zip_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("../escaped.txt", "bad")

    with pytest.raises(GameServiceError) as raised:
        safe_extract_zip(archive, tmp_path / "output")

    assert raised.value.error_code == "ZIP_PATH_TRAVERSAL"
    assert not (tmp_path / "escaped.txt").exists()


def test_safe_extract_zip_rejects_excessive_file_count(tmp_path: Path) -> None:
    archive = tmp_path / "many.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("one.txt", "1")
        output.writestr("two.txt", "2")

    with pytest.raises(GameServiceError) as raised:
        safe_extract_zip(archive, tmp_path / "output", max_files=1)

    assert raised.value.error_code == "ZIP_BOMB_DETECTED"


def _write_level_dat(path: Path) -> None:
    path.mkdir(parents=True)
    document = File(
        {
            "Data": Compound(
                {
                    "LevelName": String("测试世界"),
                    "GameType": Int(0),
                    "Difficulty": Byte(2),
                    "DifficultyLocked": Byte(0),
                    "allowCommands": Byte(0),
                    "RandomSeed": Long(123456),
                    "LastPlayed": Long(1_700_000_000_000),
                    "Version": Compound({"Name": String("1.21.8")}),
                    "EclUnknownField": String("keep-me"),
                }
            )
        },
        gzipped=True,
    )
    document.save(path / "level.dat", gzipped=True)


class _WorldHarness(WorldCoordinator, WorkspaceCoordinator):
    def __init__(self, data_path: Path) -> None:
        self._data_path = data_path

    def list_instances(self) -> list[dict[str, object]]:
        return []


def test_world_patch_preserves_unknown_nbt_and_creates_backup(tmp_path: Path) -> None:
    version = tmp_path / "versions" / "test"
    _write_level_dat(version / "saves" / "world")
    harness = _WorldHarness(tmp_path / "app-data")

    result = harness.patch_world(
        tmp_path,
        "test",
        "world",
        {"difficulty": 3, "allowCommands": True, "difficultyLocked": True},
    )

    loaded = load(version / "saves" / "world" / "level.dat")
    assert str(loaded["Data"]["EclUnknownField"]) == "keep-me"
    assert int(loaded["Data"]["Difficulty"]) == 3
    assert result["allowCommands"] is True
    assert len(list((tmp_path / "ECLBackups" / "test" / "world").glob("*.zip"))) == 1


def test_instance_profile_cover_field_is_preserved(tmp_path: Path) -> None:
    profile = tmp_path / "versions" / "test" / ".ecl" / "instance.json"
    profile.parent.mkdir(parents=True)
    profile.write_text(json.dumps({"schemaVersion": 1, "cover": {"type": "local", "value": "cover.png"}}), encoding="utf-8")

    from ECL.services.game.instance_profiles import InstanceProfileStore
    from ECL.services.game.version_stats import VersionStatsStore

    store = InstanceProfileStore(tmp_path / "data", VersionStatsStore())
    assert store.read_profile(tmp_path, "test")["cover"]["value"] == "cover.png"
