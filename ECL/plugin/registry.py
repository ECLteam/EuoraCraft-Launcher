import threading
from collections.abc import Callable
from typing import Any

from ..common.logger import get_logger

logger = get_logger("plugin.registry")


class ServiceRegistry:
    def __init__(self):
        self._services: dict[str, tuple[Any, str]] = {}
        self._lock = threading.Lock()

    def register(self, name: str, handler: Callable, provider: str = "") -> None:
        with self._lock:
            self._services[name] = (handler, provider)

    def unregister(self, name: str) -> None:
        with self._lock:
            self._services.pop(name, None)

    def get(self, name: str) -> Any | None:
        with self._lock:
            entry = self._services.get(name)
            return entry[0] if entry else None

    def list_services(self) -> list[dict[str, Any]]:
        with self._lock:
            return [{"name": name, "provider": provider} for name, (_, provider) in self._services.items()]

    def unregister_by_provider(self, provider: str) -> None:
        with self._lock:
            to_remove = [n for n, (_, p) in self._services.items() if p == provider]
            for n in to_remove:
                self._services.pop(n, None)


class EventInfo:
    __slots__ = ("description", "name", "params", "plugin_name")

    def __init__(self, name: str, plugin_name: str, description: str = "", params: list[str] | None = None):
        self.name = name
        self.plugin_name = plugin_name
        self.description = description
        self.params = params or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "plugin_name": self.plugin_name,
            "description": self.description,
            "params": self.params,
        }


class EventRegistry:
    def __init__(self):
        self._events: dict[str, EventInfo] = {}
        self._subscribers: dict[str, list[tuple[Callable, str, bool]]] = {}
        self._lock = threading.RLock()
        self._pending_tasks: set = set()

    def register_event(
        self, event_name: str, plugin_name: str, description: str = "", params: list[str] | None = None
    ) -> None:
        with self._lock:
            self._events[event_name] = EventInfo(event_name, plugin_name, description, params)

    def unregister_event(self, event_name: str) -> None:
        with self._lock:
            self._events.pop(event_name, None)

    def subscribe(self, event: str, handler: Callable, subscriber: str = "", async_handler: bool = False) -> None:
        with self._lock:
            if event not in self._subscribers:
                self._subscribers[event] = []
            self._subscribers[event].append((handler, subscriber, async_handler))

    def unsubscribe(self, event: str, subscriber: str = "") -> None:
        with self._lock:
            if event not in self._subscribers:
                return
            if subscriber:
                self._subscribers[event] = [(h, s, a) for h, s, a in self._subscribers[event] if s != subscriber]
            else:
                self._subscribers[event] = []

    def unsubscribe_all(self, subscriber: str) -> None:
        with self._lock:
            for event in list(self._subscribers.keys()):
                self._subscribers[event] = [(h, s, a) for h, s, a in self._subscribers[event] if s != subscriber]

    def emit(self, event: str, *args: Any, **kwargs: Any) -> list[Any]:
        with self._lock:
            handlers = list(self._subscribers.get(event, []))
        results = []
        for handler, subscriber, is_async in handlers:
            try:
                if is_async:
                    import asyncio

                    try:
                        loop = asyncio.get_running_loop()
                        task = loop.create_task(handler(*args, **kwargs))
                        self._pending_tasks.add(task)
                        task.add_done_callback(self._pending_tasks.discard)
                    except RuntimeError:
                        logger.warning(f"异步事件处理器 [{event}@{subscriber}] 无法在无事件循环环境中执行")
                    continue
                results.append(handler(*args, **kwargs))
            except (RuntimeError, OSError, ValueError, TypeError) as e:
                logger.error(f"事件处理器异常 [{event}@{subscriber}]: {e}")
        return results

    async def emit_async(self, event: str, *args: Any, **kwargs: Any) -> list[Any]:
        with self._lock:
            handlers = list(self._subscribers.get(event, []))
        results = []
        for handler, subscriber, is_async in handlers:
            try:
                if is_async:
                    results.append(await handler(*args, **kwargs))
                else:
                    results.append(handler(*args, **kwargs))
            except (RuntimeError, OSError, ValueError, TypeError) as e:
                logger.error(f"事件处理器异常 [{event}@{subscriber}]: {e}")
        return results

    def list_events(self) -> list[dict[str, Any]]:
        with self._lock:
            return [e.to_dict() for e in self._events.values()]

    def get_provided_by_plugin(self, plugin_name: str) -> list[str]:
        with self._lock:
            return [name for name, info in self._events.items() if info.plugin_name == plugin_name]

    def unregister_by_plugin(self, plugin_name: str) -> None:
        with self._lock:
            to_remove = [n for n, info in self._events.items() if info.plugin_name == plugin_name]
            for n in to_remove:
                self._events.pop(n, None)
            self.unsubscribe_all(plugin_name)
