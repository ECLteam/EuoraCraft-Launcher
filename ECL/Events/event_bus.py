from collections import defaultdict
from collections.abc import Callable
from typing import Any

EventHandler = Callable[..., None]


class EventBus:
    """
    全局事件总线管理

    订阅规则：
    - 启动器代码直接调用 subscribe(event, handler)，无需传入所有者标识。
    - 插件的事件订阅统一由插件管理器（PluginFramework.subscribe_event）注册，
      管理器会自动以插件名作为 owner 传入，插件自身无需指定。
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
        from ECL.Infrastructure.logging import get_logger

        self.logger = get_logger("EventBus")
        # event -> [(handler, owner), ...]
        self._handlers: dict[str, list[tuple[EventHandler, str | None]]] = defaultdict(list)
        # 共享实例注册表
        self._services: dict[str, Any] = {}
        self._initialized = True

    def subscribe(self, event: str, handler: EventHandler, owner: str | None = None) -> None:
        """
        订阅事件
        :param event: 事件名称
        :param handler: 回调函数，参数由 emit 时传入
        :param owner: 订阅者标识，仅供插件管理器统一注册插件时传入插件名；
            启动器代码无需传此参数。
        """
        self._handlers[event].append((handler, owner))

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """
        发射事件，按订阅顺序同步通知所有处理函数。
        单个处理函数异常不会中断后续处理函数。
        :param event: 事件名称
        :param args: 传给处理函数的位置参数
        :param kwargs: 传给处理函数的关键字参数
        """
        handlers = self._handlers.get(event)
        if not handlers:
            return
        for handler, _ in handlers:
            try:
                handler(*args, **kwargs)
            except Exception:
                self.logger.exception("事件 %s 的处理函数执行失败", event)

    def unsubscribe(self, event: str, handler: EventHandler) -> None:
        """
        取消订阅
        :param event: 事件名称
        :param handler: 之前注册的处理函数
        """
        handlers = self._handlers.get(event)
        if not handlers:
            return
        for idx, (h, _) in enumerate(list(handlers)):
            if h is handler:
                handlers.pop(idx)
                return

    def remove_handlers_by_owner(self, owner: str) -> None:
        """
        移除指定所有者订阅的所有事件处理器，由插件管理器在禁用/卸载插件时调用。
        :param owner: 所有者标识
        """
        for event in list(self._handlers.keys()):
            handlers = self._handlers[event]
            handlers[:] = [(h, o) for h, o in handlers if o != owner]
            if not handlers:
                del self._handlers[event]

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
