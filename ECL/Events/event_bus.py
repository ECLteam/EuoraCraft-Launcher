from collections import defaultdict
from collections.abc import Callable
from typing import Any

EventHandler = Callable[..., None]

LAUNCHER_OWNER = "__launcher__"


class EventBus:
    """
    全局事件总线管理

    安全规则：
    - 启动器代码订阅事件时应传入 owner=LAUNCHER_OWNER，这些事件受保护，
      普通插件无法再次订阅。
    - 普通插件可订阅其他插件的事件，但不能订阅启动器保护的事件。
    - 系统插件不受上述限制。
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
        # 系统插件名集合
        self._system_owners: set[str] = set()
        self._initialized = True

    def register_system_plugin(self, name: str) -> None:
        """
        注册系统插件名，使其拥有与启动器代码同等的事件订阅权限。
        :param name: 插件名
        """
        self._system_owners.add(name)

    def _is_protected(self, event: str) -> bool:
        """判断事件是否已被启动器代码订阅并受保护。"""
        return any(owner == LAUNCHER_OWNER for _, owner in self._handlers.get(event, []))

    def subscribe(self, event: str, handler: EventHandler, owner: str | None = None) -> None:
        """
        订阅事件
        :param event: 事件名称
        :param handler: 回调函数，参数由 emit 时传入
        :param owner: 订阅者标识；启动器代码使用 LAUNCHER_OWNER，插件使用插件名
        """
        if (
            owner
            and owner != LAUNCHER_OWNER
            and owner not in self._system_owners
            and self._is_protected(event)
        ):
            raise PermissionError(f"事件 {event} 已被启动器保护，插件 {owner} 无法订阅")
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

    def unsubscribe(self, event: str, handler: EventHandler, owner: str | None = None) -> None:
        """
        取消订阅
        :param event: 事件名称
        :param handler: 之前注册的处理函数
        :param owner: 订阅者标识；插件只能取消自己注册的 handler
        """
        handlers = self._handlers.get(event)
        if not handlers:
            return
        for idx, (h, o) in enumerate(list(handlers)):
            if h is handler and (owner is None or o == owner):
                handlers.pop(idx)
                return

    def remove_handlers_by_owner(self, owner: str) -> None:
        """
        移除指定所有者订阅的所有事件处理器。
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
