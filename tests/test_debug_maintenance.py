import json

import pytest

from ECL.services.maintenance import (
    PENDING_MAINTENANCE_FILE,
    DebugMaintenanceError,
    apply_pending_debug_maintenance,
    schedule_debug_maintenance,
)


def _write(path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_reset_launcher_data_deletes_only_declared_targets(tmp_path) -> None:
    data_path = tmp_path / "ECL_data"
    home_dir = tmp_path / "home"
    _write(data_path / "setting.json", "{}")
    _write(data_path / "info_card.json", "{}")
    _write(data_path / "notice.json", "{}")
    _write(data_path / "accounts" / "legacy.json", "{}")
    _write(data_path / "plugins" / "example" / "plugin.json", "{}")
    _write(data_path / "logs" / "launcher.log")
    _write(home_dir / ".ECL" / "accounts" / "accounts.json", "{}")

    scheduled = schedule_debug_maintenance(data_path, "reset_launcher_data")
    results = apply_pending_debug_maintenance(data_path, home_dir=home_dir)

    assert scheduled.restart_required is True
    assert results[0].action == "reset_launcher_data"
    assert set(results[0].removed_targets) == {
        "setting.json",
        "info_card.json",
        "notice.json",
        str((home_dir / ".ECL" / "accounts").resolve()),
    }
    assert not (data_path / "setting.json").exists()
    assert not (data_path / "info_card.json").exists()
    assert not (data_path / "notice.json").exists()
    assert (data_path / "accounts" / "legacy.json").is_file()
    assert (data_path / "plugins" / "example" / "plugin.json").is_file()
    assert (data_path / "logs" / "launcher.log").is_file()
    assert not (home_dir / ".ECL" / "accounts").exists()
    assert not (data_path / PENDING_MAINTENANCE_FILE).exists()


def test_clear_plugins_can_be_scheduled_with_data_reset(tmp_path) -> None:
    data_path = tmp_path / "ECL_data"
    _write(data_path / "setting.json", "{}")
    _write(data_path / "plugins" / "example" / "plugin.json", "{}")
    _write(data_path / "plugin_config" / "example.json", "{}")

    schedule_debug_maintenance(data_path, "reset_launcher_data")
    schedule_debug_maintenance(data_path, "clear_plugins")
    marker = json.loads((data_path / PENDING_MAINTENANCE_FILE).read_text(encoding="utf-8"))

    assert marker["actions"] == ["reset_launcher_data", "clear_plugins"]

    results = apply_pending_debug_maintenance(data_path)

    assert [result.action for result in results] == ["reset_launcher_data", "clear_plugins"]
    assert not (data_path / "plugins").exists()
    assert not (data_path / "plugin_config").exists()


def test_unknown_debug_maintenance_action_is_rejected(tmp_path) -> None:
    with pytest.raises(DebugMaintenanceError):
        schedule_debug_maintenance(tmp_path / "ECL_data", "../../outside")
