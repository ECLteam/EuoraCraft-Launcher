from __future__ import annotations

import importlib
import io
import subprocess

from ECL.game import InstancesManager


class FakeProcess:
    def __init__(self, *, times_out: bool = False) -> None:
        self.times_out = times_out
        self.running = True
        self.terminate_calls = 0
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

    def terminate(self) -> None:
        self.terminate_calls += 1
        self.running = False

    def kill(self) -> None:
        self.kill_calls += 1
        self.running = False


def _manager_with_process(process: FakeProcess) -> InstancesManager:
    manager = InstancesManager()
    manager.instances["minecraft"] = {"Instance": process}
    return manager


def test_stop_instance_terminates_then_waits() -> None:
    process = FakeProcess()
    manager = _manager_with_process(process)

    exited_normally = manager.stop_instance("minecraft", wait_timeout=3.0)

    assert exited_normally is True
    assert process.terminate_calls == 1
    assert process.wait_timeouts == [3.0]
    assert process.kill_calls == 0


def test_stop_instance_forces_process_only_after_timeout() -> None:
    process = FakeProcess(times_out=True)
    manager = _manager_with_process(process)

    exited_normally = manager.stop_instance("minecraft", wait_timeout=3.0)

    assert exited_normally is False
    assert process.terminate_calls == 1
    assert process.wait_timeouts == [3.0, None]
    assert process.kill_calls == 1


def test_stop_instance_kills_when_forced() -> None:
    process = FakeProcess()
    manager = _manager_with_process(process)

    exited_normally = manager.stop_instance("minecraft", force=True, wait_timeout=None)

    assert exited_normally is True
    assert process.kill_calls == 1
    assert process.terminate_calls == 0


def test_create_instance_does_not_lose_immediate_exit_callback(monkeypatch) -> None:
    module = importlib.import_module("ECL.game.Core.InstancesManager")

    class ImmediateProcess:
        stdout = io.StringIO("")
        stderr = io.StringIO("")

        def wait(self) -> int:
            return 1

    class SynchronousThread:
        def __init__(self, *, target, args, daemon):
            self.target = target
            self.args = args

        def start(self) -> None:
            self.target(*self.args)

    monkeypatch.setattr(module.subprocess, "Popen", lambda *_args, **_kwargs: ImmediateProcess())
    monkeypatch.setattr(module.threading, "Thread", SynchronousThread)
    manager = InstancesManager()
    exits = []

    instance_id, _process = manager.create_instance(
        "instant-failure",
        "Minecraft",
        ["java", "broken"],
        exit_callback=lambda code, name: exits.append((code, name)),
    )

    assert exits == [(1, instance_id)]
