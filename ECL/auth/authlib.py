from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

import requests

from ..common.logger import get_logger

logger = get_logger("auth.authlib")

# Authlib-Injector 下载地址
AUTHLIB_INJECTOR_META_URL = "https://authlib-injector.yushi.moe/artifact/latest.json"


class AuthlibInjectorAccount:
    """外置登录（Authlib-Injector）账户。"""

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
        self._client_token: str = str(uuid.uuid4())
        self._token_expires_at: float = 0.0

    def login(self) -> bool:
        """通过 Yggdrasil API 进行登录认证。"""
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
            elif data.get("availableProfiles"):
                self.profile = data["availableProfiles"][0]
            self._token_expires_at = time.time() + 36000  # 10 小时
            logger.info(f"Authlib 账户 '{self.email}' 登录成功")
            return True
        except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
            logger.error(f"Authlib 账户登录失败: {e}")
            return False

    def refresh(self) -> bool:
        """刷新 access token。"""
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
        except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
            logger.error(f"Authlib 令牌刷新失败: {e}")
            return False

    def validate(self) -> bool:
        """验证当前 access token 是否有效。"""
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
        """获取当前有效的 access token，必要时自动刷新。"""
        if not self._access_token:
            self.login()
        elif time.time() > self._token_expires_at or not self.validate():
            self.refresh()
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
        acc._client_token = data.get("client_token", str(uuid.uuid4()))
        acc._token_expires_at = data.get("token_expires_at", 0.0)
        return acc


class AuthlibInjectorManager:
    """管理 authlib-injector.jar 的下载与路径。"""

    def __init__(self, data_dir: Path | None = None):
        self._data_dir = data_dir or Path("~/.ECLAuth/authlib").expanduser()
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._jar_path = self._data_dir / "authlib-injector.jar"

    def download(self) -> bool:
        """下载最新的 authlib-injector.jar。"""
        try:
            # 获取最新版本信息
            meta_resp = requests.get(AUTHLIB_INJECTOR_META_URL, timeout=30)
            meta_resp.raise_for_status()
            meta = meta_resp.json()
            download_url = meta.get("download_url", "")
            if not download_url:
                # 尝试其他可能的字段名
                download_url = meta.get("downloadUrl", "")
                if not download_url and "assets" in meta:
                    download_url = meta["assets"][0].get("browser_download_url", "")
            if not download_url:
                logger.error("无法从元数据中获取下载地址")
                return False
            # 下载 JAR
            jar_resp = requests.get(download_url, timeout=120)
            jar_resp.raise_for_status()
            self._jar_path.write_bytes(jar_resp.content)
            logger.info(f"Authlib-Injector 下载成功: {self._jar_path}")
            return True
        except (requests.RequestException, json.JSONDecodeError, KeyError, OSError) as e:
            logger.error(f"Authlib-Injector 下载失败: {e}")
            return False

    def get_path(self) -> Path:
        """获取 authlib-injector.jar 路径，如果不存在则自动下载。"""
        if not self._jar_path.is_file():
            self.download()
        return self._jar_path

    def get_launch_args(self, auth_server: str) -> list[str]:
        """获取 JVM 启动参数（-javaagent 和 -D 参数）。"""
        jar_path = self.get_path()
        return [
            f"-javaagent:{jar_path}={auth_server}",
            "-Dauthlibinjector.noLogFile=true",
        ]
