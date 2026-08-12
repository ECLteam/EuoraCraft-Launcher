from .contracts import PluginAction, PluginActionResult, PluginCommandError
from .discovery import PluginDiscovery
from .lifecycle import PluginLifecycle
from .registry import PluginRegistry
from .storage import PluginStorage


class PluginManager(PluginRegistry, PluginLifecycle, PluginStorage, PluginDiscovery):
    """
    Public plugin fa?ade composed from focused manager capabilities.
    """


__all__ = ["PluginAction", "PluginActionResult", "PluginCommandError", "PluginManager"]
