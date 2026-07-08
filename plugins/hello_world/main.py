from ECL.plugin.plugin import Plugin


class HelloWorldPlugin(Plugin):
    def on_enable(self):
        # 初始化内部状态、注册服务等
        pass

    def on_frontend_ready(self):
        # 前端加载完成后向前端发送通知
        from ECL.api.events import emit

        emit("launcher:notify", {"message": "你好世界", "type": "info"})

    @Plugin.on("plugin:pre_disable")
    def on_pre_disable(self, payload):
        # 返回 False 可阻止禁用操作
        return None

    @Plugin.on("plugin:pre_reload")
    def on_pre_reload(self, payload):
        # 返回 False 可阻止重载操作
        return None
