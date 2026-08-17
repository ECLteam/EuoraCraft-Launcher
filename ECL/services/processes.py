from __future__ import annotations

from collections import deque
from threading import RLock
from typing import TYPE_CHECKING, Any

from ECL.game.Core.InstancesManager import InstancesManager

if TYPE_CHECKING:
    from ECL.events.event_bus import EventBus


class ProcessService:
    """
    面向插件的通用子进程实例注册表，负责生命周期、输出缓冲与标准输入交互。

    内部复用 :class:`InstancesManager` 启动子进程并逐行读取输出；本类按实例标识
    维护元数据与最近输出环形缓冲，并通过事件总线推送 ``process:instance_log``
    与 ``process:instances_changed`` 事件供前端实例视图消费。

    :param event_bus: 承载子进程事件的事件总线
    """

    BUFFER_LIMIT = 300

    def __init__(self, event_bus: EventBus) -> None:
        self._events = event_bus
        self._manager = InstancesManager()
        self._manager.set_log_callback(self._on_log)
        self._manager.set_exit_callback(self._on_exit)
        self._lock = RLock()
        self._meta: dict[str, dict[str, Any]] = {}
        self._buffers: dict[str, deque[str]] = {}
        # 同名实例可能并发存在，退出回调仅携带实例名称；按名称排队标识以定位实例。
        self._alive: dict[str, deque[str]] = {}

    def spawn(
        self,
        name: str,
        type_: str,
        args: str | list[str],
        cwd: str | None = None,
        stdin: bool = False,
    ) -> str:
        """
        启动一个子进程实例并登记内部元数据。

        :param name: 实例名称，供列表与退出回调辨认
        :param type_: 实例类型（建议使用 ``plugin:<用途>`` 前缀）
        :param args: 可执行文件及参数
        :param cwd: 可选的工作目录
        :param stdin: 是否开启标准输入管道
        :raises ValueError: 名称、类型或参数为空时
        :return: 生成的实例标识
        """
        if not name or not type_ or not args:
            raise ValueError("实例名称、类型与启动参数不能为空")
        instance_id = self._manager.create_instance(
            instance_name=name,
            instance_type=type_,
            args=args,
            cwd=cwd,
            only_stdout=True,
            std_in=stdin,
        )
        with self._lock:
            self._meta[instance_id] = {"name": name, "type": type_, "stdin": stdin}
            self._buffers[instance_id] = deque(maxlen=self.BUFFER_LIMIT)
            self._alive.setdefault(name, deque()).append(instance_id)
        self._events.emit("process:instances_changed", self.list())
        return instance_id

    def send_stdin(self, instance_id: str, data: str) -> bool:
        """
        向指定实例的标准输入管道写入一行数据。

        :param instance_id: 目标实例标识
        :param data: 写入的数据
        :return: 实例存在且开启标准输入时返回 True
        """
        with self._lock:
            meta = self._meta.get(instance_id)
            if meta is None or not meta["stdin"]:
                return False
        payload = data if data.endswith("\n") else data + "\n"
        self._manager.send_stdin(instance_id, payload)
        return True

    def stop(self, instance_id: str, force: bool = False, wait_timeout: float | None = None) -> bool:
        """
        停止指定实例对应的子进程。

        :param instance_id: 目标实例标识
        :param force: True 直接杀死，False 发送终止信号
        :param wait_timeout: 等待进程结束的秒数，None 表示不等待
        :return: 进程是否已结束
        """
        return self._manager.stop_instance(instance_id, force=force, wait_timeout=wait_timeout)

    def list(self) -> list[dict[str, Any]]:
        """
        返回当前登注册表的实例信息列表。

        每条信息包含唯一标识、名称、类型、进程号、标准输入支持情况、运行状态，
        以及该实例最近的输出行（最多 ``BUFFER_LIMIT`` 条），供前端实例视图初始化。

        :return: 实例信息列表
        """
        with self._lock:
            items: list[dict[str, Any]] = []
            for iid, meta in self._meta.items():
                proc = self._manager.instances.get(iid, {}).get("Instance")
                pid = proc.pid if proc is not None else None
                running = proc.poll() is None if proc is not None else False
                items.append(
                    {
                        "id": iid,
                        "name": meta["name"],
                        "type": meta["type"],
                        "pid": pid,
                        "stdin": meta["stdin"],
                        "running": running,
                        "lines": list(self._buffers.get(iid, ()))[: self.BUFFER_LIMIT],
                    }
                )
            return items

    def close(self) -> None:
        """终止全部运行中的实例并清理读取线程。"""
        self._manager.shutdown_all()

    def _on_log(self, line: str, instance_id: str) -> None:
        """
        处理 InstancesManager 逐行回读的输出，写入缓冲并推送实时事件。

        :param line: 读到的单行输出
        :param instance_id: 产生输出的实例标识
        """
        with self._lock:
            meta = self._meta.get(instance_id)
            if meta is None:
                return
            self._buffers[instance_id].append(line)
            name, type_ = meta["name"], meta["type"]
        self._events.emit(
            "process:instance_log",
            {"instanceId": instance_id, "name": name, "type": type_, "line": line},
        )

    def _on_exit(self, exit_code: int, instance_name: str) -> None:
        """
        处理子进程退出事件，回收内部登记并推送实例列表变更。

        退出回调只携带实例名称，因此按名称队列取最早登记且仍存活的实例标识。

        :param exit_code: 子进程退出码
        :param instance_name: 实例名称
        """
        with self._lock:
            names = self._alive.get(instance_name)
            if not names:
                return
            instance_id = names.popleft()
            self._meta.pop(instance_id, None)
            self._buffers.pop(instance_id, None)
            if not names:
                self._alive.pop(instance_name, None)
        self._events.emit("process:instances_changed", self.list())


__all__ = ["ProcessService"]
