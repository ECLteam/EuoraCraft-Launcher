import ECL.Services.services as services
from ECL.Events import EventBus


class FakeService:
    def __init__(self, path, **options):
        self.path = path
        self.options = options
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _reset_event_bus() -> None:
    EventBus._instance = None
    EventBus._initialized = False


def test_register_services_builds_and_registers_all_services(tmp_path, monkeypatch) -> None:
    _reset_event_bus()
    monkeypatch.setattr(services, "AccountManager", FakeService)
    monkeypatch.setattr(services, "AvatarManager", FakeService)
    monkeypatch.setattr(services, "InfoCardManager", FakeService)
    monkeypatch.setattr(services, "GameService", lambda accounts: FakeService("game"))

    accounts, avatars, info_card, game_service = services.register_services(
        tmp_path / "ECL_data",
        tmp_path / "resources",
    )

    bus = EventBus()
    assert bus["accounts"] is accounts
    assert bus["avatars"] is avatars
    assert bus["info_card"] is info_card
    assert bus["game"] is game_service
    assert accounts.path == tmp_path / "ECL_data"
    assert avatars.path == tmp_path / "resources"
    assert info_card.path == tmp_path / "ECL_data"
    assert game_service.path == "game"
    _reset_event_bus()


def test_register_services_passes_microsoft_client_id_from_environment(tmp_path, monkeypatch) -> None:
    _reset_event_bus()

    class FakeEnv:
        def get_value(self, *keys):
            assert keys == ("MICROSOFT_CLIENT_ID",)
            return "environment-client-id"

    bus = EventBus()
    bus.register("env", FakeEnv())
    monkeypatch.setattr(services, "AccountManager", FakeService)
    monkeypatch.setattr(services, "AvatarManager", FakeService)
    monkeypatch.setattr(services, "InfoCardManager", FakeService)
    monkeypatch.setattr(services, "GameService", lambda accounts: FakeService("game"))

    accounts, _, _, _ = services.register_services(tmp_path / "ECL_data", tmp_path / "resources")

    assert accounts.options["microsoft_client_id"] == "environment-client-id"
    _reset_event_bus()


def test_register_services_closes_created_services_on_failure(tmp_path, monkeypatch) -> None:
    _reset_event_bus()
    created_services = []

    class TrackedService(FakeService):
        def __init__(self, path, **_options):
            super().__init__(path)
            created_services.append(self)

    class FailingInfoCard:
        def __init__(self, path):
            raise RuntimeError("info card failed")

    monkeypatch.setattr(services, "AccountManager", TrackedService)
    monkeypatch.setattr(services, "AvatarManager", TrackedService)
    monkeypatch.setattr(services, "InfoCardManager", FailingInfoCard)

    try:
        services.register_services(tmp_path / "ECL_data", tmp_path / "resources")
    except RuntimeError as exc:
        assert str(exc) == "info card failed"
    else:
        raise AssertionError("register_services should propagate initialization errors")

    assert len(created_services) == 2
    assert all(service.closed for service in created_services)
    assert EventBus().get("accounts") is None
    assert EventBus().get("avatars") is None
    assert EventBus().get("info_card") is None
    _reset_event_bus()
