import json
import sys
from unittest.mock import Mock, call

from ECL.common import get_runtime_info
from ECL.events import EventBus
from ECL.plugins import PluginFramework


def _reset_plugin_runtime() -> None:
    EventBus._instance = None
    EventBus._initialized = False
    PluginFramework._instance = None
    PluginFramework._initialized = False


def test_frozen_runtime_separates_executable_and_resource_paths(tmp_path, monkeypatch) -> None:
    executable_path = tmp_path / "program" / "EuoraCraft Launcher.exe"
    extracted_path = tmp_path / "_MEI12345"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(extracted_path), raising=False)
    monkeypatch.setattr(sys, "executable", str(executable_path))

    runtime_info = get_runtime_info()

    assert runtime_info["is_frozen"] is True
    assert runtime_info["app_path"] == executable_path.parent.resolve()
    assert runtime_info["resource_path"] == extracted_path.resolve()


def test_plugin_framework_uses_data_path_for_user_plugins(tmp_path) -> None:
    _reset_plugin_runtime()
    data_path = tmp_path / "ECL_data"
    resource_path = tmp_path / "_MEI12345"
    framework = PluginFramework()
    framework._collect_candidates = Mock(return_value=[])
    framework._load_plugins_in_order = Mock()
    framework._enable_all = Mock()

    framework.initialize(data_path, resource_path)

    assert framework._plugin_dir == data_path / "plugins"
    assert framework._plugin_config_dir == data_path / "plugin_config"
    assert framework._plugin_dir.is_dir()
    assert framework._plugin_config_dir.is_dir()
    framework._collect_candidates.assert_has_calls(
        [
            call(data_path / "plugins", is_system=False),
            call(resource_path / "resources" / "system_plugins", is_system=True),
        ]
    )


def test_plugin_install_targets_data_path(tmp_path) -> None:
    _reset_plugin_runtime()
    data_path = tmp_path / "ECL_data"
    framework = PluginFramework()
    framework._collect_candidates = Mock(return_value=[])
    framework._load_plugins_in_order = Mock()
    framework._enable_all = Mock()
    framework.initialize(data_path, tmp_path / "resources")

    source_path = tmp_path / "source_plugin"
    source_path.mkdir()
    (source_path / "plugin.json").write_text(json.dumps({"name": "example"}), encoding="utf-8")
    (source_path / "main.py").write_text(
        "from ECL.plugins import Plugin\nclass Plugin(Plugin): pass\n", encoding="utf-8"
    )

    assert framework.install(str(source_path)).success is True
    installed_path = data_path / "plugins" / "example"
    assert (installed_path / "plugin.json").is_file()
    assert "example" in framework._plugins
