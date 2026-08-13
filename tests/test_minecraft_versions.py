import json

import pytest

from ECL.game import SearchMinecraft
from ECL.services import GameService, VersionScanError


class FakeAccounts:
    pass


def test_neoforge_loader_name_uses_frontend_canonical_mapping() -> None:
    version_json = {
        "libraries": [{"name": "net.neoforged:neoforge:26.2.0.25-beta"}],
        "arguments": {"game": ["--fml.neoForgeVersion", "26.2.0.25-beta"]},
    }

    loader = SearchMinecraft._find_loader_type(version_json)

    assert loader == "NeoForge"
    assert SearchMinecraft._find_loader_version(version_json, loader) == "26.2.0.25-beta"


def _write_version_json(game_path, version_name: str, data: dict) -> None:
    version_path = game_path / "versions" / version_name
    version_path.mkdir(parents=True)
    (version_path / f"{version_name}.json").write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )


def test_version_service_normalizes_scanner_output(tmp_path) -> None:
    game_path = tmp_path / ".minecraft"
    _write_version_json(game_path, "fabric-profile", {"id": "fabric-profile"})
    requested_paths = []

    class FakeSearchMinecraft:
        def __init__(self, path):
            requested_paths.append(path)

        def search_minecraft(self):
            return {
                "fabric-profile": {
                    "VanillaType": "Release",
                    "VanillaVersion": "1.20.1",
                    "VersionPath": str(game_path / "versions" / "fabric-profile"),
                    "RequestJava": "17",
                    "LoaderType": "Fabric",
                    "LoaderVersion": "0.16.14",
                }
            }

    service = GameService(FakeAccounts(), search_factory=FakeSearchMinecraft)

    versions = service.scan_versions([str(game_path), str(game_path / "versions")])

    assert requested_paths == [game_path]
    assert len(versions) == 1
    version = versions[0]
    assert version is not None
    expected = {
        "id": "fabric-profile",
        "versionId": "fabric-profile",
        "versionType": "Release",
        "path": str(game_path),
        "displayName": "fabric-profile",
        "primaryLoader": "Fabric",
        "loaderVersion": "0.16.14",
        "vanillaName": "1.20.1",
        "requiredJava": 17,
        "hasFabric": True,
        "isBroken": False,
        "sourceName": ".minecraft",
    }
    assert expected.items() <= version.items()
    assert version["categoryId"] == "modded"
    assert version["fieldSources"]["alias"] == "auto"
    assert version["launchCount"] == 0


def test_version_service_scans_with_original_search_minecraft(tmp_path) -> None:
    game_path = tmp_path / ".minecraft"
    _write_version_json(
        game_path,
        "1.20.1",
        {
            "id": "1.20.1",
            "type": "release",
            "releaseTime": "2023-06-12T13:00:00+00:00",
            "javaVersion": {"majorVersion": 17},
            "libraries": [],
        },
    )

    versions = GameService(FakeAccounts()).scan_versions(str(game_path))

    assert len(versions) == 1
    assert versions[0]["versionId"] == "1.20.1"
    assert versions[0]["versionType"] == "Release"
    assert versions[0]["primaryLoader"] == "Vanilla"
    assert versions[0]["isBroken"] is False


def test_version_service_skips_missing_versions_directory(tmp_path) -> None:
    service = GameService(FakeAccounts(), search_factory=lambda _path: None)

    assert service.scan_versions(str(tmp_path / "empty-game")) == []


def test_version_service_rejects_invalid_path_payload() -> None:
    service = GameService(FakeAccounts(), search_factory=lambda _path: None)

    with pytest.raises(VersionScanError) as error:
        service.scan_versions({"path": "invalid"})

    assert error.value.error_code == "INVALID_GAME_PATH"
