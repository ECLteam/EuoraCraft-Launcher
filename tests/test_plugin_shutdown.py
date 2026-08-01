from unittest.mock import Mock

import ECL.launcher as launcher_module
from ECL.Events import EventBus
from ECL.Plugin import PluginFramework


def _reset_runtime() -> None:
    EventBus._instance = None
    EventBus._initialized = False
    PluginFramework._instance = None
    PluginFramework._initialized = False


def test_plugin_framework_close_disables_and_unloads_every_plugin() -> None:
    _reset_runtime()
    framework = PluginFramework()
    first = Mock()
    second = Mock()
    framework._plugins = {"first": first, "second": second}
    framework._status = {"first": "enabled", "second": "enabled"}

    bus = EventBus()
    bus.subscribe("plugin:html_injected", framework._on_html_injected)
    bus.subscribe("plugin:vue_slot_registered", framework._on_vue_slot_registered)
    framework._event_handlers_registered = True

    framework.close()
    framework.close()

    first.on_disable.assert_called_once_with()
    first.on_unload.assert_called_once_with()
    second.on_disable.assert_called_once_with()
    second.on_unload.assert_called_once_with()
    assert framework._plugins == {}
    assert framework._status == {}
    assert framework._on_html_injected not in bus._handlers["plugin:html_injected"]
    assert framework._on_vue_slot_registered not in bus._handlers["plugin:vue_slot_registered"]
    _reset_runtime()


def test_launcher_shutdown_closes_plugins_before_backend_services() -> None:
    order = []

    class Closable:
        def __init__(self, name):
            self.name = name

        def close(self):
            order.append(self.name)

    launcher = object.__new__(launcher_module.EuoraCraftLauncher)
    launcher.logger = Mock()
    launcher.plugin_framework_instance = Closable("plugins")
    launcher.service_instances = (Closable("accounts"), Closable("game"))
    launcher._shutdown_complete = False

    launcher._shutdown()
    launcher._shutdown()

    assert order == ["plugins", "game", "accounts"]


def test_main_run_shuts_down_when_adapter_fails(monkeypatch) -> None:
    class FailedAdapter:
        def run_adapter(self):
            raise RuntimeError("adapter failed")

    launcher = object.__new__(launcher_module.EuoraCraftLauncher)
    launcher.logger = Mock()
    launcher.launcher_version = "test"
    launcher.launcher_version_type = "dev"
    launcher._init = Mock(return_value=True)
    launcher._shutdown = Mock()
    monkeypatch.setattr(launcher_module, "Adapter", FailedAdapter)

    assert launcher.main_run() is False
    launcher._shutdown.assert_called_once_with()
