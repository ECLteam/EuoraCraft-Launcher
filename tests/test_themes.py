from __future__ import annotations

import json
import zipfile

import pytest

from ECL.events import EventBus
from ECL.services.themes import ThemeRevisionConflict, ThemeService, normalize_preset, sanitize_svg
from ECL.utils.config import ConfigStore


def create_service(tmp_path):
    events = EventBus()
    config = ConfigStore(tmp_path, events)
    config.get_config()
    return ThemeService(tmp_path, config, events)


def test_design_session_revision_undo_and_commit(tmp_path):
    service = create_service(tmp_path)
    started = service.start_session(restore=False)

    changed = service.patch(
        started["sessionId"],
        started["revision"],
        [{"op": "set", "path": "/tokens/primary", "value": "#ff0066"}],
    )
    assert changed["draft"]["tokens"]["primary"] == "#ff0066"
    assert changed["basePreset"]["tokens"]["primary"] != "#ff0066"
    assert changed["canUndo"] is True

    with pytest.raises(ThemeRevisionConflict) as conflict:
        service.patch(started["sessionId"], started["revision"], [{"op": "remove", "path": "/tokens/primary"}])
    assert conflict.value.snapshot["revision"] == changed["revision"]

    undone = service.undo(started["sessionId"], changed["revision"])
    assert undone["draft"]["tokens"]["primary"] != "#ff0066"
    redone = service.redo(started["sessionId"], undone["revision"])
    committed = service.commit(started["sessionId"])
    assert redone["draft"]["tokens"]["primary"] == "#ff0066"
    assert committed["dirty"] is False
    assert service.active_preset()["tokens"]["primary"] == "#ff0066"


def test_slot_overlay_is_shared_without_dirtying_or_revising_theme(tmp_path):
    service = create_service(tmp_path)
    started = service.start_session(restore=False)

    changed = service.set_overlay(
        started["sessionId"],
        show_slots=True,
        slot_hosts=[{"slotId": "plugin-slot-content-top", "contextKey": None, "occupied": False}],
    )

    assert changed["showSlots"] is True
    assert changed["revision"] == started["revision"]
    assert changed["dirty"] is False
    assert changed["slotHosts"] == [
        {"slotId": "plugin-slot-content-top", "contextKey": None, "occupied": False}
    ]
    assert service.get_session(started["sessionId"])["showSlots"] is True


def test_patch_rejects_readonly_and_dangerous_root(tmp_path):
    service = create_service(tmp_path)
    started = service.start_session(restore=False)
    with pytest.raises(ValueError):
        service.patch(
            started["sessionId"],
            started["revision"],
            [{"op": "set", "path": "/id", "value": "builtin.overwrite"}],
        )


def test_folia_is_a_readonly_builtin_and_copies_as_an_editable_skin(tmp_path):
    service = create_service(tmp_path)

    summaries = {item["id"]: item for item in service.list_presets()}
    assert summaries["builtin.folia"]["readonly"] is True
    assert service.get_preset("builtin.folia")["uiSkin"] == "folia"

    service.activate("builtin.folia")
    started = service.start_session(restore=False)
    assert started["draft"]["id"].startswith("user.")
    assert started["draft"]["uiSkin"] == "folia"


def test_theme_skin_defaults_to_classic_and_rejects_unknown_values():
    legacy = {
        "schemaVersion": 1,
        "id": "user.legacy",
        "meta": {"name": "Legacy"},
        "schemes": {},
        "tokens": {},
        "background": {},
        "componentOverrides": {},
        "nodeOverrides": {},
        "effects": [],
        "assets": {},
        "pluginDependencies": [],
        "extensions": {},
    }
    assert normalize_preset(legacy)["uiSkin"] == "classic"
    legacy["uiSkin"] = "untrusted"
    with pytest.raises(ValueError, match="skin"):
        normalize_preset(legacy)


def test_exporting_and_importing_folia_creates_a_local_copy(tmp_path):
    service = create_service(tmp_path)
    archive = service.export_preset("builtin.folia", tmp_path / "folia.ecltheme")

    imported = service.import_preset(archive)
    assert imported["originalId"] == "builtin.folia"
    assert imported["importedId"].startswith("user.")
    assert imported["preset"]["uiSkin"] == "folia"


@pytest.mark.parametrize("property_name", ["position", "zIndex", "pointerEvents", "width", "height"])
def test_theme_protocol_rejects_dangerous_style_properties(property_name):
    value = {
        "schemaVersion": 1,
        "id": "user.unsafe",
        "meta": {"name": "Unsafe"},
        "schemes": {},
        "tokens": {},
        "background": {},
        "componentOverrides": {"card": {"properties": {property_name: "1"}}},
        "nodeOverrides": {},
        "instanceOverrides": {},
        "effects": [],
        "assets": {},
        "pluginDependencies": [],
        "extensions": {},
    }
    with pytest.raises(ValueError, match="不允许修改"):
        normalize_preset(value)


def test_svg_sanitizer_removes_scripts_events_and_external_links():
    raw = b'''<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script><rect onclick="run()" width="10"/><image href="https://example.com/x.png"/></svg>'''
    safe = sanitize_svg(raw).decode("utf-8")
    assert "script" not in safe
    assert "onclick" not in safe
    assert "https://" not in safe


def test_theme_archive_roundtrip_sanitizes_svg(tmp_path):
    service = create_service(tmp_path)
    preset = service.active_preset()
    preset["id"] = "user.roundtrip"
    preset["meta"]["name"] = "Roundtrip"
    service.save_preset(preset)
    asset = tmp_path / "themes" / "user.roundtrip" / "assets" / "shape.svg"
    asset.parent.mkdir(parents=True)
    asset.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect width="10"/></svg>', encoding="utf-8")

    archive = service.export_preset("user.roundtrip", tmp_path / "roundtrip.ecltheme")
    service.delete_preset("user.roundtrip")
    imported = service.import_preset(archive)

    assert imported["importedId"] == "user.roundtrip"
    assert (tmp_path / "themes" / "user.roundtrip" / "assets" / "shape.svg").is_file()
    resource = service.asset_data_url("user.roundtrip", "assets/shape.svg")
    assert resource["mime"] == "image/svg+xml"
    assert resource["dataUrl"].startswith("data:image/svg+xml;base64,")


def test_theme_import_rejects_path_traversal(tmp_path):
    service = create_service(tmp_path)
    archive = tmp_path / "bad.ecltheme"
    theme = service.active_preset()
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("theme.json", json.dumps(theme))
        package.writestr("manifest.json", json.dumps({"checksums": {}}))
        package.writestr("../escape.svg", "<svg/>")
    with pytest.raises(ValueError, match="不安全路径"):
        service.import_preset(archive)
