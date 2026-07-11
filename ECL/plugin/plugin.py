from __future__ import annotations

import asyncio
import enum
import functools
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .framework import PluginFramework


class PluginStatus(enum.Enum):
    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    ENABLING = "enabling"
    ENABLED = "enabled"
    DISABLING = "disabling"
    DISABLED = "disabled"
    UNLOADING = "unloading"
    ERROR = "error"


def _get_event_loop() -> asyncio.AbstractEventLoop | None:
    """返回当前运行的事件循环，若无则返回 None。"""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


class Plugin:
    # 类级别待处理事件处理器和事件定义，按 qualname 存储
    _pending_handlers: dict[str, list[tuple[str, bool]]] = {}
    _pending_provided_events: dict[str, list[tuple[str, str, list[str]]]] = {}

    def __init__(self, framework: PluginFramework):
        self._framework = framework
        self._name = ""
        self._version = ""
        self._status = PluginStatus.UNLOADED
        self._error = None
        self._services: dict[str, Any] = {}
        self._event_handlers: dict[str, list] = {}
        self._meta: dict[str, Any] = {}


    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "",
            "version": "0.0.0",
            "title": "",
            "description": "",
            "author": "",
            "dependencies": {"third_party": {}, "plugins": {}},
            "events": {"provided": [], "required": []},
        }

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._version

    @property
    def status(self) -> PluginStatus:
        return self._status

    @property
    def meta(self) -> dict[str, Any]:
        return self._meta

    @property
    def services(self) -> dict[str, Any]:
        return self._services

    @property
    def framework(self) -> PluginFramework:
        return self._framework

    def register_service(self, name: str, handler: Any) -> None:
        self._services[name] = handler
        self._framework._service_registry.register(name, handler, self._name)

    def unregister_service(self, name: str) -> None:
        self._services.pop(name, None)
        self._framework._service_registry.unregister(name)

    def get_service(self, name: str) -> Any | None:
        return self._framework._service_registry.get(name)

    def register_settings(self, schema: dict[str, Any]) -> None:
        self._framework._register_plugin_settings(self._name, schema)

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self._framework._get_plugin_setting(self._name, key, default)

    def update_setting(self, key: str, value: Any) -> None:
        self._framework._update_plugin_setting(self._name, key, value)

    def inject_css(self, css: str) -> None:
        from ..api.events import emit

        emit("plugin:css_injected", {"plugin": self._name, "css": css})

    def inject_html(self, slot: str, html: str) -> None:
        self._framework._inject_html(self._name, slot, html)

    def register_route(self, path: str, title: str, icon: str = "plugin") -> None:
        self._framework._register_route(self._name, path, title, icon)

    def unregister_route(self, path: str) -> None:
        self._framework._unregister_route(self._name, path)

    def register_command(self, name: str, handler: Any, description: str = "") -> None:
        self._framework._register_command(self._name, name, handler, description)

    def inject_script(self, js: str) -> None:
        from ..api.events import emit

        emit("plugin:script_injected", {"plugin": self._name, "script": js})

    def inject_typescript(self, ts: str) -> None:
        from ..api.events import emit

        emit("plugin:typescript_injected", {"plugin": self._name, "script": ts})

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        if self._framework._shutting_down:
            return
        self._framework._event_registry.emit(event, *args, **kwargs)

    def emit_async(self, event: str, *args: Any, **kwargs: Any) -> None:
        if self._framework._shutting_down:
            return
        loop = _get_event_loop()
        if loop is not None:
            _ = asyncio.create_task(self._framework._event_registry.emit_async(event, *args, **kwargs))  # noqa: RUF006

    @staticmethod
    def provide_event(name: str, desc: str = "", params: list[str] | None = None):
        def decorator(func):
            Plugin._pending_provided_events.setdefault(func.__qualname__, []).append((name, desc, params or []))

            @functools.wraps(func)
            def wrapper(*a, **kw):
                return func(*a, **kw)

            return wrapper

        return decorator

    def require(self, package_name: str):
        return self._framework._importer.import_package(package_name, self._name)

    @staticmethod
    def on(event: str, async_handler: bool = False):
        def decorator(func):
            Plugin._pending_handlers.setdefault(func.__qualname__, []).append((event, async_handler))

            @functools.wraps(func)
            def wrapper(*a, **kw):
                return func(*a, **kw)

            return wrapper

        return decorator

    def on_load(self) -> None:
        pass

    async def async_on_load(self) -> None:
        pass

    def on_enable(self) -> None:
        pass

    async def async_on_enable(self) -> None:
        pass

    def on_frontend_ready(self) -> None:
        pass

    async def async_on_frontend_ready(self) -> None:
        pass

    def on_disable(self) -> None:
        pass

    async def async_on_disable(self) -> None:
        pass

    def on_unload(self) -> None:
        pass

    async def async_on_unload(self) -> None:
        pass

    def get_provided_events(self) -> list[str]:
        return self._framework._event_registry.get_provided_by_plugin(self._name)

    def get_subscribed_events(self) -> list[str]:
        return list(self._event_handlers.keys())

    def get_available_events(self) -> list[dict[str, Any]]:
        return self._framework._event_registry.list_events()


    def _provide_event(self, name: str, desc: str = "", params: list[str] | None = None):
        def decorator(func):
            self._framework._event_registry.register_event(
                event_name=name,
                plugin_name=self._name,
                description=desc,
                params=params or [],
            )

            @functools.wraps(func)
            def wrapper(*a, **kw):
                return func(*a, **kw)

            return wrapper

        return decorator

    def _on(self, event: str, async_handler: bool = False):
        def decorator(func):
            self._framework._event_registry.subscribe(event, func, self._name, async_handler)
            self._event_handlers.setdefault(event, []).append(func)

            @functools.wraps(func)
            def wrapper(*a, **kw):
                return func(*a, **kw)

            return wrapper

        return decorator

    def _bind_pending_handlers(self) -> None:
        class_prefix = self.__class__.__qualname__ + "."
        to_remove_handlers = []
        for qualname, entries in Plugin._pending_handlers.items():
            if not qualname.startswith(class_prefix):
                continue
            method_name = qualname.rsplit(".", 1)[-1]
            actual = getattr(self, method_name, None)
            if actual is not None and callable(actual):
                for event, async_h in entries:
                    self._framework._event_registry.subscribe(event, actual, self._name, async_h)
                    self._event_handlers.setdefault(event, []).append(actual)
            to_remove_handlers.append(qualname)
        for key in to_remove_handlers:
            Plugin._pending_handlers.pop(key, None)

        to_remove_events = []
        for qualname, entries in Plugin._pending_provided_events.items():
            if not qualname.startswith(class_prefix):
                continue
            for name, desc, params in entries:
                self._framework._event_registry.register_event(
                    event_name=name,
                    plugin_name=self._name,
                    description=desc,
                    params=params,
                )
            to_remove_events.append(qualname)
        for key in to_remove_events:
            Plugin._pending_provided_events.pop(key, None)
