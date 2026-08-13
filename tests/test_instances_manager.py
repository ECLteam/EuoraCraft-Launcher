from __future__ import annotations

import subprocess

from ECL.game import InstancesManager


class FakeProcess:
    def __init__(self, *, times_out: bool = False) -> None:
        self.times_out = times_out
        self.running = True
        self.kill_calls = 0
        self.wait_timeouts: list[float | int | None] = []

    def poll(self) -> int | None:
        return None if self.running else 0

    def wait(self, timeout: float | int | None = None) -> int:
        self.wait_timeouts.append(timeout)
        if self.times_out and self.kill_calls == 0:
            raise subprocess.TimeoutExpired("java", timeout)
        self.running = False
        return 0

    def kill(self) -> None:
        self.kill_calls += 1
        self.running = False


def _manager_with_process(process: FakeProcess) -> InstancesManager:
    manager = InstancesManager()
    manager.instances["minecraft"] = {"Instance": process}
    return manager


def test_request_instance_exit_notifies_before_waiting(monkeypatch) -> None:
    process = FakeProcess()
    manager = _manager_with_process(process)
    notifications = []
    monkeypatch.setattr(manager, "_notify_process_exit", lambda target: notifications.append(target) or True)

    exited_normally = manager.request_instance_exit("minecraft", wait_timeout=3.0)

    assert exited_normally is True
    assert notifications == [process]
    assert process.wait_timeouts == [3.0]
    assert process.kill_calls == 0


def test_request_instance_exit_forces_process_only_after_timeout(monkeypatch) -> None:
    process = FakeProcess(times_out=True)
    manager = _manager_with_process(process)
    monkeypatch.setattr(manager, "_notify_process_exit", lambda _target: True)

    exited_normally = manager.request_instance_exit("minecraft", wait_timeout=3.0)

    assert exited_normally is False
    assert process.wait_timeouts == [3.0, None]
    assert process.kill_calls == 1
