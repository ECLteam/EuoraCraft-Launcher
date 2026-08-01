import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ECL.Events import EventBus
from ECL.Infrastructure import get_logger

if TYPE_CHECKING:
    from ECL.Plugin.framework import PluginFramework


class Plugin:
    """
    插件基类，所有插件必须继承此类。
    生命周期：on_load → on_enable → on_frontend_ready → on_disable → on_unload

    支持装饰器语法：
        @Plugin.on_event("config:updated")
        def on_config_changed(self, section, data): ...

        @Plugin.on_command("hello", description="返回问候语")
        def cmd_hello(self, name="World"): ...

        @Plugin.on_setting(key="max_count", default=10, type_="number", description="最大数量")
        def _setting_max_count(self): ...

        @Plugin.on_route("/my-plugin", "我的插件", icon="puzzle")
        def _route_my_plugin(self): ...

        @Plugin.on_vue_route("/my-plugin", "我的插件", "my-page", "page.vue", icon="puzzle")
        def _vue_route_my_plugin(self): ...

        @Plugin.on_css("style.css")
        def _css_style(self): ...

        @Plugin.on_html("sidebar-bottom", "sidebar.html")
        def _html_sidebar(self): ...

        @Plugin.on_script("counter.js")
        def _js_counter(self): ...

        @Plugin.on_vue_slot("sidebar-bottom", "my-widget", "widget.vue")
        def _vue_slot_widget(self): ...
    """

    # 每个子类独立持有的装饰器注册表
    # 基类上必须有默认值，因为装饰器在子类体执行期间就被求值（早于 __init_subclass__）
    _event_handlers: list[tuple[str, str]] = []
    _command_handlers: list[tuple[str, str, str]] = []
    _setting_definitions: list[tuple[str, Any, str, str]] = []
    _route_definitions: list[tuple[str, str, str]] = []
    _frontend_injections: list[tuple[str, tuple]] = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # 为每个子类创建独立的注册表副本，避免子类间互相污染
        cls._event_handlers = []
        cls._command_handlers = []
        cls._setting_definitions = []
        cls._route_definitions = []
        cls._frontend_injections = []

    def __init__(self, framework: "PluginFramework", plugin_dir: Path, metadata: dict[str, Any]):
        self.framework = framework
        self.plugin_dir: Path = plugin_dir # 插件根目录，用于读取 resources/
        self.name: str = metadata["name"]
        self.title: str = metadata.get("title", self.name)
        self.version: str = metadata.get("version", "0.0.0")
        self.description: str = metadata.get("description", "")
        self.author: str = metadata.get("author", "")
        self.metadata: dict[str, Any] = metadata
        self.logger = get_logger(f"Plugin.{self.name}")
        # 插件注册的命令映射，framework 调用时查表
        self._commands: dict[str, Callable] = {}
        # 插件的设置项定义，供前端设置页渲染
        self._settings: dict[str, dict[str, Any]] = {}
        # 消费装饰器注册表，绑定到实例
        self._apply_decorators()

    def _apply_decorators(self) -> None:
        """将类级别的装饰器注册表绑定到当前实例"""
        for event, method_name in self._event_handlers:
            handler = getattr(self, method_name)
            self.subscribe(event, handler)
        for cmd_name, method_name, description in self._command_handlers:
            handler = getattr(self, method_name)
            self.register_command(cmd_name, handler, description)
        for key, default, description, type_ in self._setting_definitions:
            self.register_setting(key, default, description, type_)
        # 路由和前端注入在对应生命周期阶段应用，此处仅暂存
        self._routes_to_register = list(self._route_definitions)
        self._injections_to_apply = list(self._frontend_injections)

    @classmethod
    def on_event(cls, event: str) -> Callable:
        """
        装饰器：将方法注册为事件处理器，实例化时自动订阅
        :param event: 事件名称，如 "config:updated"
        """
        def wrapper(func):
            cls._event_handlers.append((event, func.__name__))
            return func
        return wrapper

    @classmethod
    def on_command(cls, name: str, description: str = "") -> Callable:
        """
        装饰器：将方法注册为命令处理器，实例化时自动注册
        :param name: 命令名，调用时格式为 "插件名:命令名"
        :param description: 命令描述
        """
        def wrapper(func):
            cls._command_handlers.append((name, func.__name__, description))
            return func
        return wrapper

    @classmethod
    def on_setting(cls, key: str, default: Any, type_: str = "string", description: str = "") -> Callable:
        """
        装饰器：声明设置项，实例化时自动注册（被装饰的函数体可为空）
        :param key: 设置键名
        :param default: 默认值
        :param type_: 设置类型 bool | string | number | select
        :param description: 设置描述
        """
        def wrapper(func):
            cls._setting_definitions.append((key, default, description, type_))
            return func
        return wrapper

    @classmethod
    def on_route(cls, path: str, title: str, icon: str = "") -> Callable:
        """
        装饰器：声明侧边栏路由，on_enable 时自动注册
        :param path: 路由路径，如 "/my-plugin"
        :param title: 显示名称
        :param icon: 图标名
        """
        def wrapper(func):
            cls._route_definitions.append((path, title, icon))
            return func
        return wrapper

    @classmethod
    def on_css(cls, file_path: str) -> Callable:
        """
        装饰器：声明 CSS 文件，on_frontend_ready 时自动注入到前端
        :param file_path: 相对于插件目录的 CSS 文件路径，如 "style.css"
        """
        def wrapper(func):
            cls._frontend_injections.append(("css", (file_path,)))
            return func
        return wrapper

    @classmethod
    def on_html(cls, slot_id: str, file_path: str) -> Callable:
        """
        装饰器：声明 HTML 文件，on_frontend_ready 时自动注入到指定插槽
        :param slot_id: 插槽 ID
        :param file_path: 相对于插件目录的 HTML 文件路径，如 "sidebar.html"
        """
        def wrapper(func):
            cls._frontend_injections.append(("html", (slot_id, file_path)))
            return func
        return wrapper

    @classmethod
    def on_script(cls, file_path: str) -> Callable:
        """
        装饰器：声明 JS 文件，on_frontend_ready 时自动注入到前端
        :param file_path: 相对于插件目录的 JS 文件路径，如 "counter.js"
        """
        def wrapper(func):
            cls._frontend_injections.append(("script", (file_path,)))
            return func
        return wrapper

    @classmethod
    def on_vue_slot(cls, slot_id: str, component_name: str, file_path: str) -> Callable:
        """
        装饰器：声明 Vue SFC 组件，on_frontend_ready 时自动注册到指定插槽
        :param slot_id: 插槽 ID
        :param component_name: 全局唯一组件名
        :param file_path: 相对于插件目录的 .vue 文件路径，如 "widget.vue"
        """
        def wrapper(func):
            cls._frontend_injections.append(("vue_slot", (slot_id, component_name, file_path)))
            return func
        return wrapper

    @classmethod
    def on_vue_route(cls, path: str, title: str, component_name: str,
                     file_path: str, icon: str = "") -> Callable:
        """
        装饰器：声明 Vue SFC 路由页面，on_enable 时自动注册
        :param path: 路由路径
        :param title: 侧边栏显示名称
        :param component_name: 全局唯一组件名
        :param file_path: 相对于插件目录的 .vue 文件路径，如 "page.vue"
        :param icon: 图标名
        """
        def wrapper(func):
            cls._frontend_injections.append(("vue_route", (path, title, component_name, file_path, icon)))
            return func
        return wrapper

    def on_load(self) -> None:
        """加载资源，此时不应注册路由/命令"""

    def on_enable(self) -> None:
        """注册路由、命令、设置项。子类覆盖时需调用 super().on_enable()"""
        for path, title, icon in self._routes_to_register:
            self.register_route(path, title, icon)

    def on_frontend_ready(self) -> None:
        """前端就绪后注入 CSS/HTML/JS。子类覆盖时需调用 super().on_frontend_ready()"""
        for inj_type, args in self._injections_to_apply:
            if inj_type == "css":
                self.register_css_file(*args)
            elif inj_type == "html":
                self.register_html_file(*args)
            elif inj_type == "script":
                self.register_script_file(*args)
            elif inj_type == "vue_slot":
                self.register_vue_slot_file(*args)
            elif inj_type == "vue_route":
                self.register_vue_route_file(*args)

    def on_disable(self) -> None:
        """清理运行时状态"""

    def on_unload(self) -> None:
        """释放资源"""

    def register_route(self, path: str, title: str, icon: str = "") -> None:
        """
        注册前端侧边栏路由
        :param path: 路由路径，如 "/crash-reports"
        :param title: 显示名称
        :param icon: 图标名
        """
        self.framework._register_route(self, path, title, icon)

    def register_command(self, name: str, handler: Callable, description: str = "") -> None:
        """
        注册插件命令，前端通过 plugin_call_command 调用
        :param name: 命令名，调用时格式为 "插件名:命令名"
        :param handler: 命令处理函数
        :param description: 命令描述
        """
        self._commands[name] = handler

    def register_setting(self, key: str, default: Any, description: str = "", type_: str = "string") -> None:
        """
        注册设置项，前端设置页根据此定义渲染控件
        :param key: 设置键名
        :param default: 默认值
        :param description: 设置描述
        :param type_: 设置类型 bool | string | number | select
        """
        self._settings[key] = {
            "key": key,
            "default": default,
            "description": description,
            "type": type_,
        }

    def inject_css(self, css: str) -> None:
        """
        向宿主前端注入 CSS 样式
        :param css: CSS 样式字符串
        """
        EventBus().emit("plugin:css_injected", self.name, css)

    def inject_html(self, slot_id: str, html: str) -> None:
        """
        向宿主前端注入 HTML 片段
        :param slot_id: 插槽 ID，对应前端 plugin-slot 组件
        :param html: HTML 字符串
        """
        EventBus().emit("plugin:html_injected", self.name, slot_id, html)

    def inject_script(self, script: str) -> None:
        """
        向宿主前端注入 JavaScript 脚本
        :param script: JS 代码字符串
        """
        EventBus().emit("plugin:script_injected", self.name, script)

    def inject_typescript(self, script: str) -> None:
        """
        向宿主前端注入 TypeScript 脚本（前端会通过 sucrase 转译）
        :param script: TS 代码字符串
        """
        EventBus().emit("plugin:typescript_injected", self.name, script)

    def register_html_file(self, slot_id: str, file_path: str) -> None:
        """
        读取插件目录下的 HTML 文件注入到指定插槽
        :param slot_id: 插槽 ID
        :param file_path: 相对于插件目录的文件路径，如 "sidebar.html"
        """
        content = self.load_file(file_path)
        if content:
            self.inject_html(slot_id, content)

    def register_css_file(self, file_path: str) -> None:
        """
        读取插件目录下的 CSS 文件注入到宿主前端
        :param file_path: 相对于插件目录的文件路径，如 "style.css"
        """
        content = self.load_file(file_path)
        if content:
            self.inject_css(content)

    def register_script_file(self, file_path: str) -> None:
        """
        读取插件目录下的 JS 文件注入到宿主前端
        :param file_path: 相对于插件目录的文件路径，如 "counter.js"
        """
        content = self.load_file(file_path)
        if content:
            self.inject_script(content)

    def register_vue_slot_file(self, slot_id: str, component_name: str, file_path: str) -> None:
        """
        读取插件目录下的 Vue SFC 文件，解析后注册到插槽
        :param slot_id: 插槽 ID
        :param component_name: 全局唯一组件名
        :param file_path: 相对于插件目录的 .vue 文件路径，如 "widget.vue"
        """
        content = self.load_file(file_path)
        if content is None:
            return
        parts = self._parse_vue_sfc(content)
        self.register_vue_slot(slot_id, component_name, **parts)

    def register_vue_route_file(self, path: str, title: str, component_name: str,
                                file_path: str, icon: str = "") -> None:
        """
        读取插件目录下的 Vue SFC 文件，解析后注册为独立路由页面
        :param path: 路由路径
        :param title: 侧边栏显示名称
        :param component_name: 全局唯一组件名
        :param file_path: 相对于插件目录的 .vue 文件路径，如 "page.vue"
        :param icon: 图标名
        """
        content = self.load_file(file_path)
        if content is None:
            return
        parts = self._parse_vue_sfc(content)
        self.register_vue_route(path, title, component_name, icon=icon, **parts)

    def register_vue_slot(self, slot_id: str, component_name: str,
                          template: str, script: str = "", style: str = "") -> None:
        """
        注册 Vue 组件到指定插槽，前端收到后动态创建并挂载
        :param slot_id: 插槽 ID
        :param component_name: 全局唯一组件名
        :param template: Vue 模板 HTML
        :param script: 组件选项 JS 代码（data/methods/computed 等，不含 export default）
        :param style: 组件 scoped CSS
        """
        EventBus().emit("plugin:vue_slot_registered", self.name, slot_id,
                        component_name, template, script, style)

    def register_vue_route(self, path: str, title: str, component_name: str,
                           template: str, script: str = "", style: str = "", icon: str = "") -> None:
        """
        注册 Vue 组件作为独立路由页面
        :param path: 路由路径，如 "/crash-reports"
        :param title: 侧边栏显示名称
        :param component_name: Vue 组件名（全局唯一）
        :param template: Vue 模板 HTML
        :param script: 组件选项 JS 代码
        :param style: 组件 scoped CSS
        :param icon: 图标名
        """
        self.framework._register_vue_route(self, path, title, icon,
                                           component_name, template, script, style)

    def emit(self, event: str, payload: Any = None) -> None:
        """
        向全局事件总线发射事件，其他插件或宿主可订阅
        :param event: 事件名称，格式建议 "模块:动作"，如 "crash:detected"
        :param payload: 事件负载数据
        """
        EventBus().emit(event, payload)

    def subscribe(self, event: str, handler: Callable) -> None:
        """
        订阅全局事件
        :param event: 事件名称
        :param handler: 回调函数
        """
        EventBus().subscribe(event, handler)

    def load_file(self, relative_path: str, encoding: str = "utf-8") -> str | None:
        """
        读取插件目录下的文本文件
        :param relative_path: 相对于插件根目录的文件路径，如 "style.css"
        :param encoding: 文件编码
        :return: 文件内容，读取失败返回 None
        """
        path = self.plugin_dir / relative_path
        if not path.is_file():
            return None
        return path.read_text(encoding=encoding)

    def resource_path(self, relative_path: str) -> Path:
        """
        获取插件 resources/ 目录下的文件路径
        :param relative_path: 相对路径
        :return: 绝对路径
        """
        return self.plugin_dir / "resources" / relative_path

    def load_resource(self, relative_path: str, encoding: str = "utf-8") -> str | None:
        """
        读取插件 resources/ 目录下的文本文件
        :param relative_path: 相对路径
        :param encoding: 文件编码
        :return: 文件内容，读取失败返回 None
        """
        path = self.resource_path(relative_path)
        if not path.is_file():
            return None
        return path.read_text(encoding=encoding)

    @staticmethod
    def _parse_vue_sfc(content: str) -> dict[str, str]:
        """
        解析 Vue SFC 文件，提取 template / script / style 区块
        :param content: .vue 文件内容
        :return: {"template": "...", "script": "...", "style": "..."}
        """
        result: dict[str, str] = {"template": "", "script": "", "style": ""}
        for tag in ("template", "script", "style"):
            match = re.search(rf"<{tag}.*?>(.*?)</{tag}>", content, re.DOTALL)
            if match:
                result[tag] = match.group(1).strip()
        return result
