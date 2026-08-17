from .contracts import PluginAction, PluginActionResult, PluginCommandError
from .discovery import PluginDiscovery
from .lifecycle import PluginLifecycle
from .registry import PluginRegistry
from .storage import PluginStorage


class PluginManager(PluginRegistry, PluginLifecycle, PluginStorage, PluginDiscovery):
    """
    面向插件的统一门面，组合若干职责单一的 Mixin 混合类能力。
    """


__all__ = ["PluginAction", "PluginActionResult", "PluginCommandError", "PluginManager"]
