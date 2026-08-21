from ECL.plugins.auth_providers import AuthField, AuthProvider, AuthProviderRegistry
from ECL.plugins.connector import (
    ConnectorExtensionRegistry,
    ConnectorProtocolRequest,
    ConnectorProtocolResponse,
    ConnectorSessionContext,
)
from ECL.plugins.crash_extensions import CrashAnalysisContext, CrashAnalysisExtensionRegistry
from ECL.plugins.framework import PluginAction, PluginActionResult, PluginManager
from ECL.plugins.instance_compat import (
    ExternalInstanceMetadata,
    InstanceCompatibilityContext,
    InstanceCompatibilityRegistry,
)
from ECL.plugins.launch_hooks import LaunchContext, LaunchHookRegistry
from ECL.plugins.network import PluginHttpError, PluginHttpResponse
from ECL.plugins.plugin import Plugin

__all__ = [
    "AuthField",
    "AuthProvider",
    "AuthProviderRegistry",
    "ConnectorExtensionRegistry",
    "ConnectorProtocolRequest",
    "ConnectorProtocolResponse",
    "ConnectorSessionContext",
    "CrashAnalysisContext",
    "CrashAnalysisExtensionRegistry",
    "ExternalInstanceMetadata",
    "InstanceCompatibilityContext",
    "InstanceCompatibilityRegistry",
    "LaunchContext",
    "LaunchHookRegistry",
    "Plugin",
    "PluginAction",
    "PluginActionResult",
    "PluginHttpError",
    "PluginHttpResponse",
    "PluginManager",
]
