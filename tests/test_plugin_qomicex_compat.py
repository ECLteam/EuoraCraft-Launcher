"""验证 qomicex_compat 系统插件的设置卡片注入与索引解析命令。"""

import shutil
from pathlib import Path

from ECL.plugins import PluginManager


def _load_qomicex_plugin(tmp_path: Path) -> PluginManager:
    """加载 resources/system_plugins 下的 qomicex_compat 系统插件。"""
    source = Path(__file__).parent.parent / "resources" / "system_plugins" / "qomicex_compat"
    target = tmp_path / "resources" / "resources" / "system_plugins" / "qomicex_compat"
    shutil.copytree(source, target)
    framework = PluginManager()
    framework.initialize(tmp_path / "data", tmp_path / "resources")
    assert framework.get_plugin("qomicex-compat") is not None
    return framework


def test_qomicex_compat_registers_vue_settings_slot_on_frontend_ready(tmp_path: Path) -> None:
    framework = _load_qomicex_plugin(tmp_path)
    framework.on_frontend_ready()

    entries = framework.get_vue_slots().get("plugin-slot-settings-launcher-section-after", [])
    assert len(entries) == 1
    assert entries[0]["plugin"] == "qomicex-compat"
    assert entries[0]["component_name"] == "QomicExInstanceCompatSettings"
    assert "QomicEX" in entries[0]["template"]
    assert "qomicex-compat:resolve" in entries[0]["script"]


def test_qomicex_resolve_command_returns_manual_path_when_valid(tmp_path: Path) -> None:
    framework = _load_qomicex_plugin(tmp_path)
    index = tmp_path / "instances.json"
    index.write_text("{}", encoding="utf-8")

    result = framework.call_command("qomicex-compat:resolve", {"instances_path": str(index)})

    assert result["path"] == str(index.resolve())
    assert result["valid"] is True
    assert result["manual"] == str(index)


def test_qomicex_resolve_command_reports_invalid_manual_path(tmp_path: Path, monkeypatch) -> None:
    framework = _load_qomicex_plugin(tmp_path)
    monkeypatch.delenv("QOMICEX_HOME", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    missing = tmp_path / "nope" / "instances.json"

    result = framework.call_command("qomicex-compat:resolve", {"instances_path": str(missing)})

    assert result["manual"] == str(missing)
    assert result["path"] is None
    assert result["valid"] is False


def test_qomicex_resolve_command_returns_none_when_nothing_found(tmp_path: Path, monkeypatch) -> None:
    framework = _load_qomicex_plugin(tmp_path)
    monkeypatch.delenv("QOMICEX_HOME", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    result = framework.call_command("qomicex-compat:resolve", {"instances_path": ""})

    assert result["path"] is None
    assert result["valid"] is False
    assert result["manual"] is None
