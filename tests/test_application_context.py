from pathlib import Path
from types import SimpleNamespace

import pytest

import ECL.application as application_module
from ECL.application import ApplicationContext, create_application
from ECL.events import EventBus


class Closable:
    def __init__(self, name: str, order: list[str]) -> None:
        self.name = name
        self.order = order

    def close(self) -> None:
        self.order.append(self.name)


def test_application_context_closes_resources_in_reverse_dependency_order() -> None:
    order: list[str] = []
    events = EventBus()
    events.subscribe("event", lambda: None)
    context = ApplicationContext(
        state=SimpleNamespace(),
        events=events,
        config=SimpleNamespace(),
        environment=SimpleNamespace(),
        http=Closable("http", order),
        accounts=Closable("accounts", order),
        avatars=Closable("avatars", order),
        info_card=SimpleNamespace(),
        game=Closable("game", order),
        plugins=Closable("plugins", order),
    )

    context.close()
    context.close()

    assert order == ["plugins", "game", "avatars", "accounts", "http"]
    assert not events._handlers


def test_event_subscription_returns_unsubscribe_callback() -> None:
    events = EventBus()
    received: list[int] = []
    unsubscribe = events.subscribe("number", received.append)

    events.emit("number", 1)
    unsubscribe()
    events.emit("number", 2)

    assert received == [1]


def test_event_handler_failure_does_not_block_other_handlers() -> None:
    events = EventBus()
    received: list[str] = []

    def fail() -> None:
        raise RuntimeError("boom")

    events.subscribe("event", fail)
    events.subscribe("event", lambda: received.append("ok"))

    events.emit("event")

    assert received == ["ok"]


def test_composition_failure_closes_resources_already_created(monkeypatch, tmp_path: Path) -> None:
    closed: list[str] = []

    class FakeHttp:
        def __init__(self, **_kwargs) -> None:
            pass

        def close(self) -> None:
            closed.append("http")

    class FailingAccounts:
        def __init__(self, *_args, **_kwargs) -> None:
            raise RuntimeError("account initialization failed")

    monkeypatch.setattr(application_module.httpx, "Client", FakeHttp)
    monkeypatch.setattr(application_module, "AccountManager", FailingAccounts)

    with pytest.raises(RuntimeError, match="account initialization failed"):
        create_application(
            {
                "app_path": tmp_path,
                "resource_path": tmp_path,
                "is_frozen": False,
            }
        )

    assert closed == ["http"]
