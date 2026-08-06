from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import NamedTuple
from urllib.parse import quote, urljoin
from uuid import uuid4

import httpx

from ECL.Game.Core.YggdrasilAuth import YggdrasilClient


class AuthlibError(RuntimeError):
    pass


class AuthlibAvatar(NamedTuple):
    data: bytes
    is_skin: bool


class AuthlibInjector:
    METADATA_URL = "https://authlib-injector.yushi.moe/artifact/latest.json"

    def __init__(self, data_path: Path | str, http_client: httpx.Client | None = None) -> None:
        self.path = Path(data_path) / "dependencies" / "authlib-injector"
        self.path.mkdir(parents=True, exist_ok=True)
        self.jar_path = self.path / "authlib-injector.jar"
        self.checksum_path = self.path / "authlib-injector.sha256"
        self.http = http_client or httpx.Client(
            timeout=httpx.Timeout(60, connect=10),
            follow_redirects=True,
            headers={"User-Agent": "EuoraCraft-Launcher"},
        )

    @staticmethod
    def _checksum(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def ensure(self) -> Path:
        """返回可用的 authlib-injector；本地缺失时下载最新版。"""
        if self.jar_path.is_file() and self.checksum_path.is_file():
            expected = self.checksum_path.read_text(encoding="ascii").strip()
            if self._checksum(self.jar_path.read_bytes()) == expected:
                return self.jar_path

        metadata = self.http.get(self.METADATA_URL)
        metadata.raise_for_status()
        artifact = metadata.json()
        download_url = artifact["download_url"]
        expected = artifact["checksums"]["sha256"]
        response = self.http.get(download_url)
        response.raise_for_status()
        if self._checksum(response.content) != expected:
            raise AuthlibError("authlib-injector 文件校验失败")

        temporary_path = self.jar_path.with_suffix(".jar.tmp")
        temporary_path.write_bytes(response.content)
        temporary_path.replace(self.jar_path)
        self.checksum_path.write_text(expected, encoding="ascii")
        return self.jar_path

    def close(self) -> None:
        """关闭下载客户端。"""
        self.http.close()


class AuthlibAccountManager:
    def __init__(
        self,
        data_path: Path | str,
        client: YggdrasilClient | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.account_path = Path(data_path) / "accounts"
        self.account_path.mkdir(parents=True, exist_ok=True)
        self.account_file = self.account_path / "yggdrasil_accounts_list.json"
        self.token_path = self.account_path / "yggdrasil_accounts"
        self.token_path.mkdir(parents=True, exist_ok=True)
        self.client = client or YggdrasilClient()
        self.http = http_client or httpx.Client(
            timeout=httpx.Timeout(15, connect=10),
            follow_redirects=True,
            headers={"User-Agent": "EuoraCraft-Launcher"},
        )
        self.accounts: dict[str, dict] = {}
        self.tokens: dict[str, dict[str, str]] = {}
        self._lock = RLock()
        self._load()

    def _load(self) -> None:
        if not self.account_file.is_file():
            return
        accounts = json.loads(self.account_file.read_text(encoding="utf-8"))
        if not isinstance(accounts, dict):
            raise AuthlibError("外置登录账户文件格式无效")
        for account_id, account in accounts.items():
            token_file = self.token_path / f"{account_id}.json"
            if not token_file.is_file():
                continue
            token = json.loads(token_file.read_text(encoding="utf-8"))
            self.accounts[account_id] = account
            self.tokens[account_id] = token

    def _save_accounts(self) -> None:
        self.account_file.write_text(
            json.dumps(self.accounts, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _save_token(self, account_id: str) -> None:
        (self.token_path / f"{account_id}.json").write_text(
            json.dumps(self.tokens[account_id], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _resolve_server(self, server_url: str) -> str:
        url = server_url.strip()
        if "://" not in url:
            url = f"https://{url}"
        response = self.http.head(url)
        response.raise_for_status()
        api_location = response.headers.get("X-Authlib-Injector-API-Location")
        if api_location:
            url = urljoin(str(response.url), api_location)
        return url.rstrip("/")

    def _store_response(
        self,
        account_id: str,
        server_url: str,
        response: dict,
        username: str | None = None,
    ) -> dict:
        self.tokens[account_id] = {
            "AccessToken": response["accessToken"],
            "ClientToken": response["clientToken"],
        }
        profiles = dict(response)
        profiles.pop("accessToken")
        profiles.pop("clientToken")
        account = {
            "AccountId": account_id,
            "YggdrasilAPI": server_url,
            "Profiles": profiles,
        }
        saved_username = username or (self.accounts.get(account_id) or {}).get("Username")
        if saved_username:
            account["Username"] = saved_username
        self.accounts[account_id] = account
        self._save_token(account_id)
        self._save_accounts()
        return deepcopy(account)

    def list_accounts(self) -> dict[str, dict]:
        """返回全部外置登录账户。"""
        with self._lock:
            return deepcopy(self.accounts)

    def add_account(self, server_url: str, username: str, password: str) -> tuple[str, dict]:
        """登录外置账户并保存令牌与角色资料。"""
        with self._lock:
            root_url = self._resolve_server(server_url)
            account_id = uuid4().hex
            response = self.client.auth(
                root_url,
                username,
                password,
                follow_ali=False,
                client_token=account_id,
            )
            return account_id, self._store_response(account_id, root_url, response, username)

    def select_profile(self, account_id: str, profile_id: str) -> dict:
        """为尚未绑定角色的外置账户选择角色。"""
        with self._lock:
            account = self.accounts.get(account_id)
            token = self.tokens.get(account_id)
            if account is None or token is None:
                raise KeyError(f"账户 '{account_id}' 不存在")
            profiles = (account.get("Profiles") or {}).get("availableProfiles") or []
            profile = next((item for item in profiles if item.get("id") == profile_id), None)
            if profile is None:
                raise KeyError(f"角色 '{profile_id}' 不存在")
            response = self.http.post(
                f"{account['YggdrasilAPI'].rstrip('/')}/authserver/refresh",
                json={
                    "accessToken": token["AccessToken"],
                    "clientToken": token["ClientToken"],
                    "selectedProfile": profile,
                    "requestUser": True,
                },
            )
            response.raise_for_status()
            return self._store_response(account_id, account["YggdrasilAPI"], response.json())

    def delete_account(self, account_id: str) -> None:
        """删除本地外置账户。"""
        with self._lock:
            if account_id not in self.accounts:
                raise KeyError(f"账户 '{account_id}' 不存在")
            self.accounts.pop(account_id)
            self.tokens.pop(account_id)
            (self.token_path / f"{account_id}.json").unlink(missing_ok=True)
            self._save_accounts()

    def refresh_account(self, account_id: str) -> dict:
        """刷新外置账户的令牌与角色资料。"""
        with self._lock:
            account = self.accounts.get(account_id)
            token = self.tokens.get(account_id)
            if account is None or token is None:
                raise KeyError(f"账户 '{account_id}' 不存在")
            if not (account.get("Profiles") or {}).get("selectedProfile"):
                return deepcopy(account)
            response = self.client.refresh(
                account["YggdrasilAPI"],
                token["AccessToken"],
                token["ClientToken"],
                follow_ali=False,
            )
            return self._store_response(account_id, account["YggdrasilAPI"], response)

    def get_token(self, account_id: str) -> dict[str, str]:
        """返回可启动游戏的有效外置登录令牌。"""
        with self._lock:
            account = self.accounts.get(account_id)
            token = self.tokens.get(account_id)
            if account is None or token is None:
                raise KeyError(f"账户 '{account_id}' 不存在")
            if not (account.get("Profiles") or {}).get("selectedProfile"):
                raise AuthlibError("外置登录账户尚未选择角色")
            if not self.client.validate(
                account["YggdrasilAPI"],
                token["AccessToken"],
                token["ClientToken"],
                follow_ali=False,
            ):
                account = self.refresh_account(account_id)
                token = self.tokens[account_id]
            return {
                "AccessToken": token["AccessToken"],
                "ClientToken": token["ClientToken"],
                "YggdrasilAPI": account["YggdrasilAPI"],
            }

    def get_avatar(self, account_id: str, size: int) -> AuthlibAvatar | None:
        """返回所选角色的头像或皮肤数据。"""
        with self._lock:
            account = self.accounts.get(account_id)
            if account is None:
                raise KeyError(f"账户 '{account_id}' 不存在")
            profile = (account.get("Profiles") or {}).get("selectedProfile") or {}
            if not profile:
                return None
            server_url = account["YggdrasilAPI"].rstrip("/")
            username = profile.get("name") or ""
            profile_id = profile.get("id") or ""

        if username and server_url.endswith("/api/yggdrasil"):
            response = self.http.get(
                f"{server_url.removesuffix('/api/yggdrasil')}/avatar/player/{quote(username, safe='')}",
                params={"size": size, "png": "true"},
            )
            if response.status_code != 404:
                response.raise_for_status()
                return AuthlibAvatar(response.content, False)

        response = self.http.get(
            f"{server_url}/sessionserver/session/minecraft/profile/{profile_id}",
            params={"unsigned": "true"},
        )
        if response.status_code == 204:
            return None
        response.raise_for_status()
        texture = next(
            (
                item.get("value")
                for item in response.json().get("properties", [])
                if item.get("name") == "textures" and isinstance(item.get("value"), str)
            ),
            None,
        )
        if texture is None:
            return None
        texture_data = json.loads(base64.b64decode(texture))
        skin_url = (texture_data.get("textures", {}).get("SKIN") or {}).get("url")
        if not skin_url:
            return None
        response = self.http.get(skin_url)
        response.raise_for_status()
        return AuthlibAvatar(response.content, True)

    def close(self) -> None:
        """关闭认证客户端。"""
        self.http.close()
        self.client.close()
