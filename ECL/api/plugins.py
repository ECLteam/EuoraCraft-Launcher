from typing import Any

from ECL.api.contracts import failure
from ECL.plugins.framework import PluginCommandError

from .bridge import _FrontendState


class PluginHandlers(_FrontendState):
    """
    提供插件生命周期、路由、插槽与命令调用的正式 IPC 边界。
    """

    async def plugin_list(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取插件列表。

        :param body: 经过边界校验的 IPC 请求数据
        """
        return {"success": True, "data": self.plugins.list_plugins()}

    async def plugin_info(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取插件信息。

        :param body: 经过边界校验的 IPC 请求数据
        """
        plugin_name = body.get("plugin_name")
        plugin = self.plugins.get_plugin(plugin_name)
        if plugin is None:
            return {"success": False, "message": f"插件不存在: {plugin_name}", "errorCode": "PLUGIN_NOT_FOUND"}
        return {"success": True, "data": plugin.metadata}

    async def plugin_enable(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        启用插件。

        :param body: 经过边界校验的 IPC 请求数据
        """
        plugin_name = body.get("plugin_name")
        result = self.plugins.enable(plugin_name)
        if not result.success:
            return failure(result.message or f"启用插件失败: {plugin_name}", "PLUGIN_ENABLE_FAILED")
        return {"success": True}

    async def plugin_disable(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        禁用插件。

        :param body: 经过边界校验的 IPC 请求数据
        """
        plugin_name = body.get("plugin_name")
        result = self.plugins.disable(plugin_name)
        if not result.success:
            return failure(result.message or f"禁用插件失败: {plugin_name}", "PLUGIN_DISABLE_FAILED")
        return {"success": True}

    async def plugin_unload(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        卸载并删除用户插件。

        :param body: 经过边界校验的 IPC 请求数据
        """
        plugin_name = body.get("plugin_name")
        result = self.plugins.uninstall(plugin_name)
        if not result.success:
            return failure(result.message or f"卸载插件失败: {plugin_name}", "PLUGIN_UNLOAD_FAILED")
        return {"success": True}

    async def plugin_reload(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        重新加载插件。

        :param body: 经过边界校验的 IPC 请求数据
        """
        plugin_name = body.get("plugin_name")
        result = self.plugins.reload(plugin_name)
        if not result.success:
            return failure(result.message or f"重载插件失败: {plugin_name}", "PLUGIN_RELOAD_FAILED")
        return {"success": True}

    async def plugin_install(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        安装插件。

        :param body: 经过边界校验的 IPC 请求数据
        """
        plugin_path = body.get("plugin_path")
        result = self.plugins.install(plugin_path)
        if not result.success:
            return failure(result.message or "安装插件失败", "PLUGIN_INSTALL_FAILED")
        return {"success": True}

    async def plugin_get_routes(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取插件路由。

        :param body: 经过边界校验的 IPC 请求数据
        """
        return {"success": True, "data": self.plugins.get_routes()}

    async def plugin_get_slots(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取插件插槽。

        :param body: 经过边界校验的 IPC 请求数据
        """
        return {"success": True, "data": self.plugins.get_slots()}

    async def plugin_get_vue_slots(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取插件 Vue 插槽。

        :param body: 经过边界校验的 IPC 请求数据
        """
        return {"success": True, "data": self.plugins.get_vue_slots()}

    async def plugin_get_vue_components(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取插件 Vue 组件。

        :param body: 经过边界校验的 IPC 请求数据
        """
        return {"success": True, "data": self.plugins.get_vue_components()}

    async def plugin_call_command(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        调用插件命令。

        :param body: 经过边界校验的 IPC 请求数据
        """
        command = body.get("command")
        try:
            result = self.plugins.call_command(command, body.get("params", {}))
        except PluginCommandError as exc:
            return {"success": False, "message": str(exc), "errorCode": "PLUGIN_COMMAND_FAILED"}
        return {"success": True, "data": result}

    async def plugin_get_settings(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        获取插件设置。

        :param body: 经过边界校验的 IPC 请求数据
        """
        plugin_name = body.get("plugin_name")
        return {"success": True, "data": self.plugins.get_settings(plugin_name)}

    async def plugin_update_setting(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        更新插件设置。

        :param body: 经过边界校验的 IPC 请求数据
        """
        plugin_name = body.get("plugin_name")
        key = body.get("key")
        result = self.plugins.update_setting(plugin_name, key, body.get("value"))
        if not result.success:
            return failure(result.message or "更新设置失败", "SETTING_UPDATE_FAILED")
        return {"success": True}

    async def plugin_notify_sidebar_state(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        通知插件侧栏的折叠状态。

        :param body: 经过边界校验的 IPC 请求数据
        """
        collapsed = body.get("collapsed")
        if not isinstance(collapsed, bool):
            return failure("侧栏状态必须是布尔值", "INVALID_SIDEBAR_STATE")
        self.plugins.set_sidebar_state(collapsed)
        return {"success": True}
