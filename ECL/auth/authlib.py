from __future__ import annotations

import contextlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

import requests

from ..common.env import get_runtime_dir
from ..common.logger import get_logger

logger = get_logger("auth.authlib")


def _get_shared_launcher_uuid() -> str:
    config_path = get_runtime_dir() / "ECL_Libs" / "user_agreement.json"
    if config_path.is_file():
        with contextlib.suppress(OSError, ValueError, KeyError):
            data = json.loads(config_path.read_text("utf-8"))
            uuid_val = data.get("uuid", "")
            if uuid_val:
                return uuid_val
    return str(uuid.uuid4())


class AuthlibInjectorAccount:

    def __init__(
        self,
        account_id: str | None = None,
        auth_server: str = "",
        email: str = "",
        password: str = "",
        profile: dict[str, Any] | None = None,
    ):
        self.account_id = account_id or f"authlib_{uuid.uuid4().hex[:8]}"
        self.auth_server = auth_server.rstrip("/")
        self.email = email
        self.password = password
        self.profile = profile or {}
        self._access_token: str = ""
        self._client_token: str = _get_shared_launcher_uuid()
        self._token_expires_at: float = 0.0


    def login(self) -> bool:
        try:
            payload = {
                "agent": {"name": "Minecraft", "version": 1},
                "username": self.email,
                "password": self.password,
                "clientToken": self._client_token,
                "requestUser": True,
            }
            resp = requests.post(
                f"{self.auth_server}/authserver/authenticate",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data.get("accessToken", "")
            self._client_token = data.get("clientToken", self._client_token)
            if "selectedProfile" in data:
                self.profile = data["selectedProfile"]
            else:
                self.profile = next(iter(data.get("availableProfiles", [])), {})
            self._token_expires_at = time.time() + 36000  # 10 小时
            logger.info(f"Authlib 账户 '{self.email}' 登录成功")
            return True
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.error(f"Authlib 账户登录失败: {e}")
            return False

    def refresh(self) -> bool:
        try:
            if not self._access_token:
                return self.login()
            payload = {
                "accessToken": self._access_token,
                "clientToken": self._client_token,
                "requestUser": True,
            }
            resp = requests.post(
                f"{self.auth_server}/authserver/refresh",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data.get("accessToken", self._access_token)
            self._client_token = data.get("clientToken", self._client_token)
            self._token_expires_at = time.time() + 36000
            if "selectedProfile" in data:
                self.profile = data["selectedProfile"]
            logger.info(f"Authlib 账户 '{self.email}' 令牌刷新成功")
            return True
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.error(f"Authlib accessToken 刷新失败: {e}")
            return False

    def validate(self) -> bool:
        try:
            if not self._access_token:
                return False
            payload = {"accessToken": self._access_token, "clientToken": self._client_token}
            resp = requests.post(
                f"{self.auth_server}/authserver/validate",
                json=payload,
                timeout=10,
            )
            return resp.status_code == 204
        except requests.RequestException:
            return False

    def get_token(self) -> str:
        if not self._access_token:
            self.login()
        elif (time.time() > self._token_expires_at or not self.validate()) and not self.refresh():
            # 刷新失败回退到完整登录
            logger.info(f"令牌刷新失败，回退到完整登录: {self.email}")
            self.login()
        return self._access_token

    def get_uuid(self) -> str:
        return self.profile.get("id", "")

    def get_display_name(self) -> str:
        return self.profile.get("name", self.email)

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "auth_server": self.auth_server,
            "email": self.email,
            "password": self.password,
            "profile": self.profile,
            "access_token": self._access_token,
            "client_token": self._client_token,
            "token_expires_at": self._token_expires_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthlibInjectorAccount:
        acc = cls(
            account_id=data.get("account_id"),
            auth_server=data.get("auth_server", ""),
            email=data.get("email", ""),
            password=data.get("password", ""),
            profile=data.get("profile", {}),
        )
        acc._access_token = data.get("access_token", "")
        acc._client_token = data.get("client_token", _get_shared_launcher_uuid())
        acc._token_expires_at = data.get("token_expires_at", 0.0)
        return acc


class AuthlibInjectorManager:
    """管理 authlib-injector.jar 的下载与路径。"""

    def __init__(self, data_dir: Path | None = None):
        self._data_dir = data_dir or Path("~/.ECLAuth/authlib").expanduser()
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._jar_path = self._data_dir / "authlib-injector.jar"
        self.authlib_injector_url = "https://authlib-injector.yushi.moe/artifact/latest.json"

    def download(self) -> bool:
        try:
            # 获取最新版本信息
            meta_resp = requests.get(self.authlib_injector_url, timeout=30)
            meta_resp.raise_for_status()
            meta = meta_resp.json()
            download_url = meta.get("download_url", "")
            if not download_url:
                # 尝试其他可能的字段名
                download_url = meta.get("downloadUrl", "")
                if not download_url:
                    assets = meta.get("assets", [])
                    if assets and isinstance(assets[0], dict):
                        download_url = assets[0].get("browser_download_url", "")
            if not download_url:
                logger.error("无法从元数据中获取下载地址")
                return False
            # 下载 JAR
            jar_resp = requests.get(download_url, timeout=120)
            jar_resp.raise_for_status()
            self._jar_path.write_bytes(jar_resp.content)
            logger.info(f"Authlib-Injector 下载成功: {self._jar_path}")
            return True
        except (requests.RequestException, ValueError, KeyError, OSError, AttributeError) as e:
            logger.error(f"Authlib-Injector 下载失败: {e}")
            return False

    def get_path(self) -> Path:
        if not self._jar_path.is_file():
            self.download()
        return self._jar_path

    def get_launch_args(self, auth_server: str) -> list[str]:
        jar_path = self.get_path()
        return [
            f"-javaagent:{jar_path}={auth_server}",
            "-Dauthlibinjector.noLogFile=true",
        ]
