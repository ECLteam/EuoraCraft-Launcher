from collections import defaultdict
from collections.abc import Callable
from typing import Any

from ECL.Utils.logger import get_logger

EventHandler = Callable[..., None]


class EventBus:
    """
    全局事件总线管理
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.logger = get_logger("EventBus")
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        # 共享实例注册表
        self._services: dict[str, Any] = {}
        self._initialized = True

    def subscribe(self, event: str, handler: EventHandler) -> None:
        """
        订阅事件
        :param event: 事件名称
        :param handler: 回调函数，参数由 emit 时传入
        """
        self._handlers[event].append(handler)

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """
        发射事件，按订阅顺序同步通知所有处理函数
        :param event: 事件名称
        :param args: 传给处理函数的位置参数
        :param kwargs: 传给处理函数的关键字参数
        """
        handlers = self._handlers.get(event)
        if not handlers:
            return
        for handler in handlers:
            handler(*args, **kwargs)

    def unsubscribe(self, event: str, handler: EventHandler) -> None:
        """
        取消订阅
        :param event: 事件名称
        :param handler: 之前注册的处理函数
        """
        handlers = self._handlers.get(event)
        if handlers and handler in handlers:
            handlers.remove(handler)

    def register(self, name: str, instance: Any) -> None:
        """
        注册共享实例，可通过get()进行获取
        :param name: 实例名称
        :param instance: 需要注册的对象实例
        """
        self._services[name] = instance

    def get(self, name: str) -> Any:
        """
        获取已注册的共享实例
        :param name: 实例名称
        :return: 注册的实例，未注册时返回 None
        """
        return self._services.get(name)

    def __getitem__(self, name: str) -> Any:
        """bus["config"] = bus.get("config")"""
        return self._services[name]
