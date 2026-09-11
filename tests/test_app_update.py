import json

import pytest

from ECL.services.app_update import (
    PENDING_UPDATE_FILE,
    StagedUpdate,
    UpdateApplier,
    clear_stale_pending_update,
)


def _applier(tmp_path, *, is_frozen=True, version_type="release", platform="win32") -> UpdateApplier:
    return UpdateApplier(
        app_path=tmp_path / "app",
        data_path=tmp_path / "data",
        is_frozen=is_frozen,
        version_type=version_type,
        current_version="1.4.1",
        platform=platform,
    )


def _asset(name: str, *, size: int = 0) -> dict:
    return {
        "name": name,
        "browser_download_url": f"https://github.com/ECLteam/euoracraft/releases/download/v1.4.2/{name}",
        "size": size,
    }


def _release(*names: str) -> dict:
    return {"tag_name": "v1.4.2", "assets": [_asset(name) for name in names]}


def test_enabled_depends_on_frozen_and_channel(tmp_path) -> None:
    assert _applier(tmp_path, version_type="release").enabled() is True
    assert _applier(tmp_path, version_type="beta").enabled() is True
    assert _applier(tmp_path, version_type="rc").enabled() is True
    assert _applier(tmp_path, version_type="alpha").enabled() is False
    assert _applier(tmp_path, is_frozen=False, version_type="release").enabled() is False


@pytest.mark.parametrize(
    ("platform", "preferred", "foreign"),
    [
        ("win32", "EuoraCraft-Launcher-Setup-1.4.2.exe", "EuoraCraft-Launcher-1.4.2-mac.dmg"),
        ("darwin", "EuoraCraft-Launcher-1.4.2.dmg", "EuoraCraft-Launcher-1.4.2-win.exe"),
        ("linux", "EuoraCraft-Launcher-1.4.2.AppImage", "EuoraCraft-Launcher-1.4.2-mac.dmg"),
        ("linux", "EuoraCraft-Launcher-1.4.2-x86_64.AppImage", "EuoraCraft-Launcher-1.4.2-win.exe"),
    ],
)
def test_matching_asset_selects_platform(tmp_path, platform: str, preferred: str, foreign: str) -> None:
    release = _release(preferred, foreign, "EuoraCraft-Launcher-1.4.2.sha256")
    asset = _applier(tmp_path, platform=platform).matching_asset(release)
    assert asset is not None
    assert asset.name == preferred


def test_matching_asset_excludes_sidecars_but_prefers_executable(tmp_path) -> None:
    release = _release(
        "EuoraCraft-Launcher-1.4.2-win.zip",
        "EuoraCraft-Launcher-1.4.2.exe",
        "EuoraCraft-Launcher-1.4.2.exe.sha256",
        "checksums.sha512",
    )
    asset = _applier(tmp_path, platform="win32").matching_asset(release)
    assert asset is not None
    assert asset.name == "EuoraCraft-Launcher-1.4.2.exe"


def test_matching_asset_returns_none_without_suitable_asset(tmp_path) -> None:
    release = _release("EuoraCraft-Launcher-1.4.2-mac.dmg", "EuoraCraft-Launcher-1.4.2.sha256")
    assert _applier(tmp_path, platform="win32").matching_asset(release) is None


def test_stage_writes_pending_marker(tmp_path) -> None:
    applier = _applier(tmp_path)
    binary = tmp_path / "download" / "EuoraCraft-Launcher.exe"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"new-launcher")
    version = "1.4.2"
    release = _release("EuoraCraft-Launcher.exe")
    release["tag_name"] = f"v{version}"
    target = tmp_path / "app" / "EuoraCraft-Launcher.exe"
    target.parent.mkdir(parents=True)

    staged, new_binary = applier.stage(
        release,
        downloaded=binary,
        target=target,
        stage_dir=tmp_path / "data" / "updates" / version,
    )

    assert staged.version == version
    assert new_binary.resolve() == binary.resolve()
    pending = tmp_path / "data" / PENDING_UPDATE_FILE
    assert pending.is_file()
    marker = json.loads(pending.read_text(encoding="utf-8"))
    assert marker["version"] == version
    assert marker["new_binary"] == str(binary)
    assert marker["target"] == str(target)


def test_stage_raises_when_asset_missing(tmp_path) -> None:
    applier = _applier(tmp_path)
    with pytest.raises(Exception) as exc_info:
        applier.stage(_release())
    assert "未找到与当前系统匹配的安装包" in str(exc_info.value)


def test_load_pending_returns_marker(tmp_path) -> None:
    applier = _applier(tmp_path)
    pending = tmp_path / "data" / PENDING_UPDATE_FILE
    pending.parent.mkdir(parents=True)
    target = tmp_path / "app" / "launcher.exe"
    new_binary = tmp_path / "updates" / "launcher.exe"
    backup = tmp_path / "updates" / "launcher.old.exe"
    pending.write_text(
        json.dumps(
            {"version": "1.4.2", "new_binary": str(new_binary), "target": str(target), "backup": str(backup)},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    staged = applier.load_pending()

    assert staged == StagedUpdate(
        version="1.4.2",
        new_binary=new_binary,
        target=target,
        backup=backup,
    )


def test_load_pending_returns_none_for_corrupt_marker(tmp_path) -> None:
    applier = _applier(tmp_path)
    pending = tmp_path / "data" / PENDING_UPDATE_FILE
    pending.parent.mkdir(parents=True)
    pending.write_text("{not-json", encoding="utf-8")

    assert applier.load_pending() is None


def test_clear_stale_pending_update_removes_marker_and_backup(tmp_path) -> None:
    data_dir = tmp_path / "data"
    (data_dir / "updates").mkdir(parents=True)
    backup = data_dir / "updates" / "launcher.old.exe"
    backup.write_bytes(b"old")
    (data_dir / PENDING_UPDATE_FILE).write_text(
        json.dumps({"backup": str(backup), "version": "1.4.2"}),
        encoding="utf-8",
    )

    assert clear_stale_pending_update(data_dir) is True
    assert not (data_dir / PENDING_UPDATE_FILE).exists()
    assert not backup.exists()


def test_clear_stale_pending_update_returns_false_without_marker(tmp_path) -> None:
    assert clear_stale_pending_update(tmp_path / "data") is False
