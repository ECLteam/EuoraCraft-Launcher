import json
from hashlib import sha256

import httpx

from ECL.Services.authlib import AuthlibAccountManager, AuthlibInjector


class OfflineClient:
    def validate(self, *args, **kwargs):
        raise AssertionError("加载账户时不应验证令牌")

    def close(self):
        pass


class LoginClient:
    def __init__(self):
        self.request = None

    def auth(self, url, username, password, follow_ali, client_token):
        self.request = (url, username, password, follow_ali, client_token)
        return {
            "accessToken": "access-token",
            "clientToken": client_token,
            "selectedProfile": {"id": "profile-id", "name": "Player"},
        }

    def close(self):
        pass


def test_authlib_login_resolves_and_saves_full_server_url_and_email(tmp_path) -> None:
    def resolve_server(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            headers={"X-Authlib-Injector-API-Location": "/api/yggdrasil"},
        )

    client = LoginClient()
    manager = AuthlibAccountManager(
        tmp_path,
        client,
        httpx.Client(transport=httpx.MockTransport(resolve_server)),
    )

    account_id, account = manager.add_account("skin.example.com", "player@example.com", "secret")

    assert account["YggdrasilAPI"] == "https://skin.example.com/api/yggdrasil"
    assert account["Username"] == "player@example.com"
    assert client.request[:4] == (
        "https://skin.example.com/api/yggdrasil",
        "player@example.com",
        "secret",
        False,
    )
    saved = json.loads((tmp_path / "accounts" / "yggdrasil_accounts_list.json").read_text(encoding="utf-8"))
    assert saved[account_id]["YggdrasilAPI"] == "https://skin.example.com/api/yggdrasil"
    assert saved[account_id]["Username"] == "player@example.com"
    manager.close()


def test_authlib_injector_downloads_verified_artifact_once(tmp_path) -> None:
    jar_data = b"authlib-injector"
    checksum = sha256(jar_data).hexdigest()
    requests = []

    def download(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if str(request.url) == AuthlibInjector.METADATA_URL:
            return httpx.Response(
                200,
                request=request,
                json={
                    "download_url": "https://download.example.com/authlib-injector.jar",
                    "checksums": {"sha256": checksum},
                },
            )
        return httpx.Response(200, request=request, content=jar_data)

    injector = AuthlibInjector(
        tmp_path,
        httpx.Client(transport=httpx.MockTransport(download)),
    )

    first_path = injector.ensure()
    second_path = injector.ensure()

    assert first_path == second_path
    assert first_path.read_bytes() == jar_data
    assert requests == [
        AuthlibInjector.METADATA_URL,
        "https://download.example.com/authlib-injector.jar",
    ]
    injector.close()


def test_saved_authlib_account_loads_without_network_request(tmp_path) -> None:
    account_id = "saved-account"
    account_dir = tmp_path / "accounts"
    token_dir = account_dir / "yggdrasil_accounts"
    token_dir.mkdir(parents=True)
    account_info = {
        account_id: {
            "AccountId": account_id,
            "YggdrasilAPI": "https://skin.example.com/api/yggdrasil",
            "Profiles": {
                "selectedProfile": {
                    "id": "1cb5a9d2f3454fe5bf576e33138a2992",
                    "name": "Player",
                }
            },
        }
    }
    token_info = {"AccessToken": "access-token", "ClientToken": account_id}
    account_list_path = account_dir / "yggdrasil_accounts_list.json"
    account_list_path.write_text(json.dumps(account_info), encoding="utf-8")
    (token_dir / f"{account_id}.json").write_text(json.dumps(token_info), encoding="utf-8")
    http_client = httpx.Client(transport=httpx.MockTransport(lambda request: None))

    manager = AuthlibAccountManager(tmp_path, OfflineClient(), http_client)

    assert manager.list_accounts() == account_info
    assert json.loads(account_list_path.read_text(encoding="utf-8")) == account_info
    manager.close()


def test_selecting_authlib_profile_refreshes_and_saves_account(tmp_path) -> None:
    selected_profiles = []

    def select_profile(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        selected_profiles.append(body["selectedProfile"])
        return httpx.Response(
            200,
            request=request,
            json={
                "accessToken": "selected-access-token",
                "clientToken": "saved-account",
                "selectedProfile": body["selectedProfile"],
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(select_profile))
    manager = AuthlibAccountManager(tmp_path, OfflineClient(), http_client)
    manager.accounts["saved-account"] = {
        "AccountId": "saved-account",
        "YggdrasilAPI": "https://skin.example.com/api/yggdrasil",
        "Profiles": {
            "availableProfiles": [
                {"id": "profile-one", "name": "PlayerOne"},
                {"id": "profile-two", "name": "PlayerTwo"},
            ]
        },
    }
    manager.tokens["saved-account"] = {
        "AccessToken": "access-token",
        "ClientToken": "saved-account",
    }

    account = manager.select_profile("saved-account", "profile-two")

    assert selected_profiles == [{"id": "profile-two", "name": "PlayerTwo"}]
    assert account["Profiles"]["selectedProfile"]["name"] == "PlayerTwo"
    saved_accounts = json.loads((tmp_path / "accounts" / "yggdrasil_accounts_list.json").read_text(encoding="utf-8"))
    assert saved_accounts["saved-account"]["Profiles"]["selectedProfile"]["id"] == "profile-two"
    manager.close()
