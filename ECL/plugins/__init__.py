from ECL.plugins.connector import (
    ConnectorExtensionRegistry,
    ConnectorProtocolRequest,
    ConnectorProtocolResponse,
    ConnectorSessionContext,
)
from ECL.plugins.framework import PluginAction, PluginActionResult, PluginManager
from ECL.plugins.instance_compat import (
    ExternalInstanceMetadata,
    InstanceCompatibilityContext,
    InstanceCompatibilityRegistry,
)
from ECL.plugins.plugin import Plugin

PluginFramework = PluginManager

__all__ = [
    "ConnectorExtensionRegistry",
    "ConnectorProtocolRequest",
    "ConnectorProtocolResponse",
    "ConnectorSessionContext",
    "ExternalInstanceMetadata",
    "InstanceCompatibilityContext",
    "InstanceCompatibilityRegistry",
    "Plugin",
    "PluginAction",
    "PluginActionResult",
    "PluginFramework",
    "PluginManager",
]
