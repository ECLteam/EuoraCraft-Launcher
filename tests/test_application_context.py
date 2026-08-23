import os
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
        wardrobe=SimpleNamespace(),
        info_card=SimpleNamespace(),
        game=Closable("game", order),
        connector=SimpleNamespace(),
        plugins=Closable("plugins", order),
        processes=Closable("processes", order),
    )

    context.close()
    context.close()

    assert order == ["plugins", "processes", "game", "accounts", "http"]
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


def test_composition_reports_loaded_state_before_services_are_created(monkeypatch, tmp_path: Path) -> None:
    observed: list[tuple[bool, bool]] = []

    class FakeConfigStore:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def get_config(self) -> dict:
            return {"launcher": {"debug": True}}

    class FakeEnvironment:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def apply_to_config(self, config: dict) -> dict:
            return config

        def get_value(self, _key: str) -> None:
            return None

    class StopComposition:
        def __init__(self, *_args, **_kwargs) -> None:
            raise RuntimeError("stop after state callback")

    monkeypatch.setattr(application_module, "ConfigStore", FakeConfigStore)
    monkeypatch.setattr(application_module, "Environment", FakeEnvironment)
    monkeypatch.setattr(application_module.httpx, "Client", StopComposition)

    with pytest.raises(RuntimeError, match="stop after state callback"):
        create_application(
            {
                "app_path": tmp_path,
                "resource_path": tmp_path,
                "is_frozen": False,
            },
            on_state_ready=lambda state: observed.append((state.debug, bool(state.config))),
        )

    assert observed == [(True, True)]


def test_proxy_mode_migrates_legacy_ignore_proxy() -> None:
    proxy_mode = application_module._proxy_mode
    assert proxy_mode({"proxy_mode": "none"}) == "none"
    assert proxy_mode({"proxy_mode": "system"}) == "system"
    assert proxy_mode({"proxy_mode": "custom"}) == "custom"
    assert proxy_mode({"ignore_proxy": True}) == "none"
    assert proxy_mode({"ignore_proxy": False}) == "system"
    assert proxy_mode({}) == "none"
    # 新配置优先于旧字段
    assert proxy_mode({"proxy_mode": "custom", "ignore_proxy": True}) == "custom"


def test_resolve_proxy_url_system_mode_reads_system_proxy(monkeypatch) -> None:
    monkeypatch.setattr(
        application_module,
        "getproxies",
        lambda: {"http": "http://proxy.example:8080", "https": "http://proxy.example:8443"},
    )
    assert application_module._resolve_proxy_url("system", "") == "http://proxy.example:8080"
    # 自定义地址不影响 system 模式
    assert application_module._resolve_proxy_url("system", "http://custom:9") == "http://proxy.example:8080"


def test_resolve_proxy_url_skips_socks_and_missing_proxy(monkeypatch) -> None:
    monkeypatch.setattr(
        application_module,
        "getproxies",
        lambda: {"http": "socks5://127.0.0.1:1080", "https": "http://https-proxy:3128"},
    )
    assert application_module._resolve_proxy_url("system", "") == "http://https-proxy:3128"
    monkeypatch.setattr(application_module, "getproxies", lambda: {})
    assert application_module._resolve_proxy_url("system", "") is None


def test_resolve_proxy_url_custom_and_none_modes() -> None:
    assert application_module._resolve_proxy_url("custom", "http://127.0.0.1:7890") == "http://127.0.0.1:7890"
    assert application_module._resolve_proxy_url("custom", "") is None
    assert application_module._resolve_proxy_url("none", "") is None
    assert application_module._resolve_proxy_url("none", "http://ignored:1") is None


def test_none_proxy_mode_sets_no_proxy_env(monkeypatch, tmp_path: Path) -> None:
    class FakeConfigStore:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def get_config(self) -> dict:
            return {"launcher": {"proxy_mode": "none"}}

    class FakeEnvironment:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def apply_to_config(self, config: dict) -> dict:
            return config

        def get_value(self, _key: str) -> None:
            return None

    class CaptureHttp:
        def __init__(self, **kwargs) -> None:
            self.transport = kwargs.get("transport")
            raise RuntimeError("stop after http client")

    monkeypatch.setattr(application_module, "ConfigStore", FakeConfigStore)
    monkeypatch.setattr(application_module, "Environment", FakeEnvironment)
    monkeypatch.setattr(application_module.httpx, "Client", CaptureHttp)
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)

    with pytest.raises(RuntimeError, match="stop after http client"):
        create_application(
            {
                "app_path": tmp_path,
                "resource_path": tmp_path,
                "is_frozen": False,
            }
        )

    assert os.environ.get("NO_PROXY") == "*"
    assert os.environ.get("no_proxy") == "*"


def test_system_proxy_mode_does_not_force_no_proxy(monkeypatch, tmp_path: Path) -> None:
    class FakeConfigStore:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def get_config(self) -> dict:
            return {"launcher": {"proxy_mode": "system"}}

    class FakeEnvironment:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def apply_to_config(self, config: dict) -> dict:
            return config

        def get_value(self, _key: str) -> None:
            return None

    class CaptureHttp:
        def __init__(self, **kwargs) -> None:
            self.transport = kwargs.get("transport")
            raise RuntimeError("stop after http client")

    monkeypatch.setattr(application_module, "ConfigStore", FakeConfigStore)
    monkeypatch.setattr(application_module, "Environment", FakeEnvironment)
    monkeypatch.setattr(application_module.httpx, "Client", CaptureHttp)
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")

    with pytest.raises(RuntimeError, match="stop after http client"):
        create_application(
            {
                "app_path": tmp_path,
                "resource_path": tmp_path,
                "is_frozen": False,
            }
        )

    # system 模式不应主动把 NO_PROXY 置为 *（保持系统代理可用）
    assert os.environ.get("NO_PROXY") == ""
    assert os.environ.get("no_proxy") == ""
