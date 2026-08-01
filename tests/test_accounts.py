from __future__ import annotations

import time
from typing import Any

import pytest

import ECL.Services.accounts as accounts_service
from ECL.Events import EventBus
from ECL.Services import AccountManager


class FakeMicrosoftManager:
    def __init__(self):
        self.on_device_code = None
        self.accounts: dict[str, dict[str, Any]] = {}
        self.closed = False

    def get_microsoft_accounts(self) -> dict[str, dict[str, Any]]:
        return self.accounts.copy()

    def add_microsoft_account(self) -> str:
        self.on_device_code(
            {
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://microsoft.com/link",
                "message": "Use the device code",
                "interval": 1,
            }
        )
        account_id = "microsoft-account"
        self.accounts[account_id] = {
            "AccountId": account_id,
            "Email": "player@example.com",
            "Profile": {
                "id": "0123456789abcdef0123456789abcdef",
                "name": "Player",
                "skins": [{"url": "https://textures.example.com/skin.png"}],
            },
            "Skin": {},
        }
        return account_id

    def del_microsoft_account(self, account_id: str) -> None:
        self.accounts.pop(account_id)

    def refresh_profile(self, account_id: str) -> dict[str, Any]:
        return self.accounts[account_id]

    def get_minecraft_token(self, account_id: str) -> str:
        assert account_id in self.accounts
        return "minecraft-access-token"

    def close(self) -> None:
        self.closed = True


class BlockingMicrosoftManager(FakeMicrosoftManager):
    def __init__(self):
        super().__init__()
        self.flow: dict[str, Any] | None = None

    def add_microsoft_account(self) -> str:
        self.flow = {
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://microsoft.com/link",
            "message": "Use the device code",
            "interval": 1,
            "expires_at": time.time() + 900,
        }
        self.on_device_code(self.flow)
        while self.flow["expires_at"] > time.time():
            time.sleep(0.01)
        raise RuntimeError("device flow cancelled")


class DuplicateMicrosoftManager(FakeMicrosoftManager):
    def __init__(self):
        super().__init__()
        self.login_count = 0

    def add_microsoft_account(self) -> str:
        self.login_count += 1
        self.on_device_code(
            {
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://microsoft.com/link",
                "message": "Use the device code",
                "interval": 1,
            }
        )
        account_id = f"microsoft-account-{self.login_count}"
        self.accounts[account_id] = {
            "AccountId": account_id,
            "Email": "player@example.com",
            "Profile": {
                "id": "0123456789abcdef0123456789abcdef",
                "name": "Player",
                "skins": [],
            },
            "Skin": {},
        }
        return account_id


def _reset_event_bus() -> None:
    EventBus._instance = None
    EventBus._initialized = False


def test_offline_accounts_persist_and_emit_changes(tmp_path) -> None:
    _reset_event_bus()
    events = []
    EventBus().subscribe("accounts:changed", events.append)
    manager = AccountManager(tmp_path, microsoft_manager=FakeMicrosoftManager())

    account = manager.add_offline("Steve")

    assert account["type"] == "offline"
    assert account["alias"] == "Steve"
    assert manager.current_account()["id"] == account["id"]
    assert events[-1]["current"]["id"] == account["id"]

    restored = AccountManager(tmp_path, microsoft_manager=FakeMicrosoftManager())
    assert restored.current_account()["alias"] == "Steve"


def test_offline_account_accepts_custom_uuid(tmp_path) -> None:
    manager = AccountManager(tmp_path, microsoft_manager=FakeMicrosoftManager())

    account = manager.add_offline("CustomPlayer", "0123456789abcdef0123456789abcdef")

    assert account["uuid"] == "01234567-89ab-cdef-0123-456789abcdef"
    assert account["id"] == "offline:01234567-89ab-cdef-0123-456789abcdef"


def test_offline_account_exposes_launch_credentials(tmp_path) -> None:
    manager = AccountManager(tmp_path, microsoft_manager=FakeMicrosoftManager())
    manager.add_offline("Steve", "0123456789abcdef0123456789abcdef")

    assert manager.get_launch_credentials() == {
        "player_name": "Steve",
        "uuid": "0123456789abcdef0123456789abcdef",
        "user_type": "legacy",
        "access_token": "None",
    }


def test_offline_account_rejects_invalid_custom_uuid(tmp_path) -> None:
    manager = AccountManager(tmp_path, microsoft_manager=FakeMicrosoftManager())

    with pytest.raises(accounts_service.AccountError) as error:
        manager.add_offline("CustomPlayer", "not-a-uuid")

    assert error.value.error_code == "INVALID_OFFLINE_UUID"


def test_account_manager_uses_runtime_microsoft_client_id(tmp_path, monkeypatch) -> None:
    captured_options = {}

    class CapturingMicrosoftManager(FakeMicrosoftManager):
        def __init__(self, **options):
            super().__init__()
            captured_options.update(options)

    monkeypatch.setattr(accounts_service, "MicrosoftAuthManager", CapturingMicrosoftManager)

    manager = AccountManager(tmp_path, microsoft_client_id="runtime-client-id")

    assert captured_options["client_id"] == "runtime-client-id"
    assert manager.microsoft_login_config() == {"available": True, "needs_client_id": False}
    manager.close()


def test_microsoft_login_requires_configured_client_id(tmp_path, monkeypatch) -> None:
    class CapturingMicrosoftManager(FakeMicrosoftManager):
        def __init__(self, **options):
            super().__init__()

    monkeypatch.setattr(accounts_service, "MICROSOFT_CLIENT_ID", "")
    monkeypatch.setattr(accounts_service, "MicrosoftAuthManager", CapturingMicrosoftManager)
    manager = AccountManager(tmp_path)

    assert manager.microsoft_login_config() == {"available": False, "needs_client_id": True}
    with pytest.raises(accounts_service.AccountError) as error:
        manager.start_microsoft_login()

    assert error.value.error_code == "MICROSOFT_CLIENT_ID_REQUIRED"
    assert manager._login_thread is None
    manager.close()


def test_microsoft_device_login_flow(tmp_path) -> None:
    _reset_event_bus()
    login_events = []
    EventBus().subscribe("accounts:microsoft_login_status", login_events.append)
    microsoft_manager = FakeMicrosoftManager()
    manager = AccountManager(tmp_path, microsoft_manager=microsoft_manager)

    started = manager.start_microsoft_login()
    if manager._login_thread is not None:
        manager._login_thread.join(timeout=1)

    assert started["status"] in {"pending", "completed"}
    if started["status"] == "pending":
        assert started["userCode"] == "ABCD-EFGH"
        assert started["verificationUri"] == "https://microsoft.com/link"
        assert manager.poll_microsoft_login()["status"] == "ready"
        completed = manager.complete_microsoft_login()
        assert completed["status"] == "completed"
        assert completed["account"]["alias"] == "Player"

    account_list = manager.list_accounts()
    assert account_list["current"]["type"] == "microsoft"
    assert account_list["current"]["skinUrl"] == "https://textures.example.com/skin.png"
    assert login_events[-1] == {"status": "ready"}


def test_repeated_microsoft_login_replaces_existing_account(tmp_path) -> None:
    _reset_event_bus()
    microsoft_manager = DuplicateMicrosoftManager()
    manager = AccountManager(tmp_path, microsoft_manager=microsoft_manager)

    for _ in range(2):
        manager.start_microsoft_login()
        manager._login_thread.join(timeout=1)
        manager.complete_microsoft_login()

    account_list = manager.list_accounts()

    assert [account["id"] for account in account_list["accounts"]] == ["microsoft-account-2"]
    assert account_list["current"]["id"] == "microsoft-account-2"
    assert list(microsoft_manager.accounts) == ["microsoft-account-2"]


def test_existing_microsoft_duplicates_are_merged_on_startup(tmp_path) -> None:
    _reset_event_bus()
    microsoft_manager = DuplicateMicrosoftManager()
    microsoft_manager.login_count = 2
    for account_id in ("microsoft-account-1", "microsoft-account-2"):
        microsoft_manager.accounts[account_id] = {
            "AccountId": account_id,
            "Email": "player@example.com",
            "Profile": {
                "id": "0123456789abcdef0123456789abcdef",
                "name": "Player",
                "skins": [],
            },
            "Skin": {},
        }

    manager = AccountManager(tmp_path, microsoft_manager=microsoft_manager)

    assert [account["id"] for account in manager.list_accounts()["accounts"]] == ["microsoft-account-2"]
    assert list(microsoft_manager.accounts) == ["microsoft-account-2"]


def test_remove_and_switch_accounts(tmp_path) -> None:
    _reset_event_bus()
    manager = AccountManager(tmp_path, microsoft_manager=FakeMicrosoftManager())
    first = manager.add_offline("Steve")
    second = manager.add_offline("Alex")

    manager.switch_account(first["id"])
    assert manager.current_account()["id"] == first["id"]

    manager.remove_account(first["id"])
    assert manager.current_account()["id"] == second["id"]


def test_complete_microsoft_login_keeps_pending_state(tmp_path) -> None:
    _reset_event_bus()
    manager = AccountManager(tmp_path, microsoft_manager=FakeMicrosoftManager())
    manager._login_state = {"status": "pending", "interval": 3}

    result = manager.complete_microsoft_login()

    assert result == {"status": "pending", "retry_after": 3}
    assert manager.poll_microsoft_login() == {"status": "pending", "retry_after": 3}


def test_cancel_microsoft_login_stops_device_flow(tmp_path) -> None:
    _reset_event_bus()
    login_events = []
    EventBus().subscribe("accounts:microsoft_login_status", login_events.append)
    microsoft_manager = BlockingMicrosoftManager()
    manager = AccountManager(tmp_path, microsoft_manager=microsoft_manager)

    started = manager.start_microsoft_login()
    assert started["status"] == "pending"
    assert manager.cancel_microsoft_login() is True

    manager._login_thread.join(timeout=1)

    assert not manager._login_thread.is_alive()
    assert microsoft_manager.flow["expires_at"] == 0
    assert microsoft_manager.flow["interval"] == 2
    assert manager.poll_microsoft_login() == {"status": "error", "message": "Microsoft 登录已取消"}
    assert login_events[-1] == {"status": "cancelled"}


def test_close_cancels_login_and_releases_manager(tmp_path) -> None:
    _reset_event_bus()
    microsoft_manager = BlockingMicrosoftManager()
    manager = AccountManager(tmp_path, microsoft_manager=microsoft_manager)

    manager.start_microsoft_login()
    manager.close()
    manager._login_thread.join(timeout=1)

    assert not manager._login_thread.is_alive()
    assert microsoft_manager.closed is True
